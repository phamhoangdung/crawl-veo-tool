import logging
import platform
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Font mặc định cho drawtext (Phase 13 overlay) — chỉ định trực tiếp `fontfile`
# thay vì để filter tự dò qua fontconfig. Trên nhiều bản ffmpeg đóng gói sẵn
# (portable build, hoặc app đóng gói desktop ở Phase 12) fontconfig không có
# config file khả dụng ("Fontconfig error: Cannot load default config file") —
# lỗi này khiến drawtext CRASH (access violation) thay vì báo lỗi rõ ràng, thay vì
# chỉ đơn giản là không hiện chữ. Tự chỉ định fontfile tránh phụ thuộc fontconfig.
_DEFAULT_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


class FfmpegNotFoundError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("ffmpeg không có trong PATH — cài ffmpeg trước khi tải/merge video.")


class FontNotFoundError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Không tìm thấy font nào để overlay text (drawtext) — hệ điều hành: "
            f"{platform.system()}. Cần cài font hệ thống hoặc chỉ định fontfile thủ công."
        )


def _resolve_default_fontfile() -> str:
    for candidate in _DEFAULT_FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise FontNotFoundError()


def _escape_filter_path(path: str) -> str:
    """Escape đường dẫn để nhét an toàn vào filter ffmpeg (dấu `:` là delimiter
    của filter, dấu `\\` của Windows path cũng cần escape) — cùng cách đã dùng ở
    `burn_subtitles` cho đường dẫn file .srt."""
    return path.replace("\\", "/").replace(":", "\\:")


def ensure_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None:
        raise FfmpegNotFoundError()


def merge_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> None:
    """Ghép video-only + audio-only stream (DASH) thành 1 file mp4, copy codec (không re-encode)."""
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c", "copy",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def extract_audio(video_path: Path, output_path: Path) -> None:
    """Tách audio track thành file wav riêng (đầu vào cho Demucs)."""
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le", str(output_path)],
        check=True,
        capture_output=True,
    )


def time_stretch(input_path: Path, output_path: Path, factor: float) -> None:
    """Co giãn thời lượng audio theo `factor` (giữ cao độ) bằng filter `atempo` của ffmpeg.

    `atempo` chỉ nhận factor trong [0.5, 2.0] mỗi lần — factor ngoài khoảng này cần chain
    nhiều lần `atempo`, ít gặp với 1 câu thoại nên clamp về biên thay vì chain cho đơn giản.
    """
    ensure_ffmpeg_available()
    clamped = max(0.5, min(2.0, factor))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path), "-filter:a", f"atempo={clamped}", str(output_path)],
        check=True,
        capture_output=True,
    )


def mix_audio_tracks(track_a: Path, track_b: Path, output_path: Path) -> None:
    """Trộn 2 track audio (vd giọng đọc mới + nhạc nền đã tách) thành 1 track."""
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(track_a),
            "-i", str(track_b),
            "-filter_complex", "amix=inputs=2:duration=longest",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def get_video_dimensions(video_path: Path) -> tuple[int, int]:
    ensure_ffmpeg_available()
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    width_str, height_str = result.stdout.strip().split("x")
    return int(width_str), int(height_str)


def probe_duration_seconds(video_path: Path) -> float | None:
    """Thời lượng thật của video. Trả None khi không đọc được, để phía gọi tự
    quyết (khác `probe_video_width` có giá trị mặc định hợp lý — thời lượng thì
    không có con số nào đoán được mà vẫn đúng)."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(video_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return float(result.stdout.strip().splitlines()[0])
    except (subprocess.SubprocessError, ValueError, IndexError, OSError) as exc:
        logger.warning("Không đọc được thời lượng video %s (%s)", video_path, exc)
        return None


def extract_last_frame(
    video_path: Path, output_path: Path, *, offset_from_end: float = 0.05
) -> None:
    """Trích khung cuối clip thành ảnh — dùng làm keyframe mở đầu cảnh kế tiếp
    (nối frame, xem docs/phases/phase-15-node-canvas.md).

    Lùi `offset_from_end` giây so với điểm cuối: seek đúng vào mốc cuối cùng
    thường rơi qua frame cuối decode được và ra ảnh rỗng.
    """
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration = probe_duration_seconds(video_path)
    seek_args: list[str] = []
    if duration is not None:
        # -ss trước -i để seek nhanh (không decode từ đầu clip).
        seek_args = ["-ss", str(max(0.0, duration - offset_from_end))]

    subprocess.run(
        [
            "ffmpeg", "-y",
            *seek_args,
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path, *, font_size: int) -> None:
    """Burn phụ đề vào video. `font_size` nên chọn theo tỉ lệ khung hình (video dọc 9:16
    cần chữ to hơn tương đối vì khung hẹp) — xem `subtitle_service.pick_font_size_for`.

    Đường dẫn srt phải escape dấu `:` và `\\` cho cú pháp filter của ffmpeg trên Windows.
    """
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_srt = str(srt_path).replace("\\", "/").replace(":", "\\:")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"subtitles='{escaped_srt}':force_style='FontSize={font_size},Outline=1'",
            "-c:a", "copy",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def _escape_drawtext(text: str) -> str:
    """Escape ký tự đặc biệt cho filter `drawtext` — cùng kiểu escape đã dùng ở
    `burn_subtitles` cho filter `subtitles`, drawtext cần thêm escape dấu nháy đơn
    vì text được bọc trong `'...'`."""
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def probe_video_width(path: str | Path) -> int:
    """Bề rộng thật của video, để quy đổi khung phụ đề theo tỉ lệ thành số ký tự.

    Trả 1080 khi không đọc được (video dọc phổ biến nhất) — thà wrap hơi lệch
    còn hơn làm chết cả lần render.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width", "-of", "csv=p=0", str(path),
            ],
            capture_output=True, text=True, check=True, timeout=15,
        )
        return int(result.stdout.strip().splitlines()[0])
    except (subprocess.SubprocessError, ValueError, IndexError, OSError) as exc:
        logger.warning("Không đọc được bề rộng video %s (%s), dùng 1080", path, exc)
        return 1080


def _has_cjk(text: str) -> bool:
    """Chữ Hán rộng gần gấp đôi chữ Latin nên số ký tự vừa một dòng khác nhau."""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _wrap_text_to_box(text: str, max_chars: int) -> str:
    """Chia câu thành nhiều dòng cho vừa khung phụ đề.

    `drawtext` KHÔNG tự xuống dòng — câu dài sẽ tràn ra ngoài khung hình và bị
    cắt mất. Phải tự chèn '\n' ở đây.

    Cắt theo từ, nhưng từ nào dài hơn cả dòng thì cắt cứng giữa từ (thà xuống
    dòng giữa từ còn hơn tràn ra ngoài). Tiếng Trung không có dấu cách giữa chữ
    nên gần như luôn đi vào nhánh cắt cứng — đó là hành vi đúng cho tiếng Trung.
    """
    if max_chars <= 0:
        return text

    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split(" "):
            while len(word) > max_chars:
                if current:
                    lines.append(current)
                    current = ""
                lines.append(word[:max_chars])
                word = word[max_chars:]
            candidate = f"{current} {word}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        lines.append(current)
    return "\n".join(lines)


def render_timeline(operations: dict, output_path: Path) -> None:
    """Render 1 timeline (Phase 13) thành video hoàn chỉnh — dựng `-filter_complex`
    động từ "edit operations" JSON thay vì các hàm đơn lẻ cố định ở trên.

    Cấu trúc `operations` mong đợi:
    {
      "tracks": [
        {"type": "video", "clips": [
            {"source": "path.mp4", "start": 0, "end": 10,
             "transition_in": "cut"|"fade", "transition_duration": 1.0,
             "crop": {"x": 0, "y": 0, "width": 720, "height": 1280}}, ...  # tuỳ chọn, Phase 11
        ]},
        {"type": "audio", "role": "voice"|"music", "clips": [
            {"source": "path.mp3", "start": 0, "end": 10,
             "track_start": 0, "volume": 1.0}, ...
        ]},
        {"type": "overlay", "clips": [
            {"text": "...", "start": 0, "end": 5, "x": 0.5, "y": 0.9, "font_size": 32}, ...
        ]}
      ]
    }

    Đúng 1 track "video" (nhiều clip nối tiếp nhau, transition giữa 2 clip liên
    tiếp), 0+ track "audio" (trộn với nhau bằng amix, mỗi track có volume riêng —
    dùng cho ducking cơ bản: đặt volume nhạc nền thấp hơn giọng đọc), 0-1 track
    "overlay" (drawtext, hiện/ẩn theo mốc thời gian qua `enable`).

    Giới hạn đã biết (MVP): xfade giả định các clip video cùng resolution/fps —
    input lệch định dạng cần chuẩn hoá trước (chưa tự động hoá ở bản này).
    """
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tracks = operations.get("tracks", [])
    video_track = next((t for t in tracks if t.get("type") == "video"), None)
    audio_tracks = [t for t in tracks if t.get("type") == "audio"]
    overlay_track = next((t for t in tracks if t.get("type") == "overlay"), None)
    image_track = next((t for t in tracks if t.get("type") == "image"), None)
    blur_track = next((t for t in tracks if t.get("type") == "blur"), None)

    if not video_track or not video_track.get("clips"):
        raise ValueError("Timeline cần ít nhất 1 track video có clip")

    inputs: list[str] = []

    def add_input(source: str) -> int:
        inputs.append(source)
        return len(inputs) - 1

    filter_parts: list[str] = []

    # --- track video: trim (+ crop tuỳ chọn, Phase 11) từng clip rồi nối/chuyển cảnh ---
    video_labels: list[tuple[str, dict]] = []
    for i, clip in enumerate(video_track["clips"]):
        idx = add_input(clip["source"])
        label = f"v{i}"
        crop = clip.get("crop")
        crop_filter = (
            f",crop={crop['width']}:{crop['height']}:{crop['x']}:{crop['y']}" if crop else ""
        )
        # `fps` + `settb` là bắt buộc, không phải tối ưu: `concat` xuất timebase
        # 1/1000000 và framerate "1/0" (không xác định), còn clip chưa qua concat
        # giữ timebase gốc (vd 1/15360). Khi có `transition_in="fade"` ở clip nào
        # đó sau một chuỗi cut, `xfade` sẽ fail với "timebase do not match" /
        # "needs to be a constant frame rate". Chuẩn hoá từng clip trước khi nối
        # để mọi tổ hợp cut/fade đều dựng được.
        filter_parts.append(
            f"[{idx}:v]trim=start={clip['start']}:end={clip['end']},"
            f"setpts=PTS-STARTPTS{crop_filter},fps={_TIMELINE_FPS},settb=AVTB[{label}]"
        )
        video_labels.append((label, clip))

    final_video_label, prev_clip = video_labels[0][0], video_labels[0][1]
    cumulative_duration = prev_clip["end"] - prev_clip["start"]
    for i in range(1, len(video_labels)):
        label, clip = video_labels[i]
        transition = clip.get("transition_in", "cut")
        out_label = f"vjoin{i}"
        clip_duration = clip["end"] - clip["start"]
        if transition == "fade":
            transition_duration = clip.get("transition_duration", 1.0)
            offset = max(0.0, cumulative_duration - transition_duration)
            filter_parts.append(
                f"[{final_video_label}][{label}]xfade=transition=fade:"
                f"duration={transition_duration}:offset={offset}[{out_label}]"
            )
            cumulative_duration = offset + clip_duration
        else:
            filter_parts.append(
                f"[{final_video_label}][{label}]concat=n=2:v=1:a=0[{out_label}]"
            )
            cumulative_duration += clip_duration
        final_video_label = out_label

    # --- blur: che logo / phụ đề gốc bằng vùng mờ ---
    # Đặt TRƯỚC overlay text và ảnh: mục đích là che thứ có sẵn trong video gốc,
    # nếu làm sau thì mờ luôn chữ và logo mà mình vừa thêm vào.
    if blur_track and blur_track.get("clips"):
        for i, region in enumerate(blur_track["clips"]):
            # Phải `split` trước: ffmpeg KHÔNG cho dùng lại cùng một nhãn cho 2
            # nhánh filter (một nhánh cắt vùng để làm mờ, một nhánh làm nền).
            base = f"blurbase{i}"
            copy = f"blurcopy{i}"
            blurred = f"blurb{i}"
            out_label = f"blur{i}"
            filter_parts.append(f"[{final_video_label}]split=2[{base}][{copy}]")

            # x/y/w/h theo TỈ LỆ khung hình [0,1] để vùng che đúng chỗ dù video
            # đổi độ phân giải — khớp cách đặt của overlay text và ảnh.
            x = region.get("x", 0.0)
            y = region.get("y", 0.0)
            w = region.get("width", 0.2)
            h = region.get("height", 0.1)

            # Cắt riêng vùng cần che, làm mờ, rồi chồng lại đúng vị trí. Làm mờ cả
            # khung rồi mới cắt thì mép vùng che bị lẫn màu từ ngoài vào.
            strength = region.get("strength", 20)
            mode = region.get("mode", "blur")
            crop_expr = f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}"

            if mode == "pixelate":
                # Làm nhoè kiểu ô vuông: thu nhỏ rồi phóng to lại bằng nội suy
                # điểm gần nhất. Che chữ Trung tốt hơn blur vì không còn đọc được
                # nét chữ, trong khi blur mạnh vẫn để lại hình dáng.
                block = max(2, int(strength))
                filter_parts.append(
                    f"[{copy}]{crop_expr},"
                    f"scale=iw/{block}:ih/{block},scale=iw*{block}:ih*{block}"
                    f":flags=neighbor[{blurred}]"
                )
            else:
                # gblur chứ không boxblur: boxblur giới hạn radius theo kích
                # thước vùng cắt (vùng 80x36px chỉ cho radius < 18) nên vùng che
                # nhỏ sẽ lỗi hẳn. gblur nhận sigma tuỳ ý.
                filter_parts.append(
                    f"[{copy}]{crop_expr},gblur=sigma={strength}[{blurred}]"
                )

            enable = ""
            if region.get("start") is not None and region.get("end") is not None:
                enable = f":enable='between(t,{region['start']},{region['end']})'"

            filter_parts.append(
                f"[{base}][{blurred}]"
                f"overlay=x=main_w*{x}:y=main_h*{y}{enable}[{out_label}]"
            )
            final_video_label = out_label

    # --- overlay: chồng drawtext lên track video đã ghép ---
    source_video_width: int | None = None
    if overlay_track and overlay_track.get("clips"):
        fontfile = _escape_filter_path(_resolve_default_fontfile())
        for i, ov in enumerate(overlay_track["clips"]):
            out_label = f"ov{i}"
            font_size = ov.get("font_size", 32)

            raw_text = ov["text"]
            # Khung giới hạn phụ đề (`box_width` theo tỉ lệ bề rộng khung hình):
            # tự chia dòng cho vừa, vì drawtext không tự wrap. Ước lượng số ký tự
            # mỗi dòng từ font_size — chữ Hán rộng ~1 font_size, chữ Latin ~0.5.
            box_width = ov.get("box_width")
            if box_width:
                # Đọc từ video nguồn 1 lần, không phải mỗi clip.
                if source_video_width is None:
                    source_video_width = probe_video_width(video_track["clips"][0]["source"])
                video_width = source_video_width
                usable_px = video_width * float(box_width)
                char_px = font_size if _has_cjk(raw_text) else font_size * 0.55
                raw_text = _wrap_text_to_box(raw_text, int(usable_px / char_px))

            text = _escape_drawtext(raw_text)
            # x/y là toạ độ TÂM chữ theo tỉ lệ khung hình [0,1] (0.5/0.5 = giữa
            # khung hình) — khớp đúng cách frontend kéo-thả overlay đặt điểm giữa,
            # không phải mép hộp chữ, để preview và bản render khớp nhau.
            x_expr = f"w*{ov.get('x', 0.5)}-text_w/2"
            y_expr = f"h*{ov.get('y', 0.9)}-text_h/2"
            filter_parts.append(
                f"[{final_video_label}]drawtext=fontfile='{fontfile}':text='{text}':"
                f"x={x_expr}:y={y_expr}:"
                f"fontsize={font_size}:fontcolor=white:box=1:boxcolor=black@0.5:"
                f"enable='between(t,{ov['start']},{ov['end']})'[{out_label}]"
            )
            final_video_label = out_label

    # --- ảnh/logo/watermark: chồng lên trên cùng, sau chữ ---
    if image_track and image_track.get("clips"):
        for i, img in enumerate(image_track["clips"]):
            idx = add_input(img["source"])
            scaled = f"imgs{i}"
            out_label = f"img{i}"

            # Bề rộng theo TỈ LỆ khung hình [0,1] để logo co giãn đúng dù video
            # đổi độ phân giải. Dùng `scale2ref` để biết kích thước video nền;
            # -1 giữ nguyên tỉ lệ ảnh gốc.
            width_ratio = img.get("width", 0.15)
            filter_parts.append(
                f"[{idx}:v][{final_video_label}]scale2ref=w=iw*{width_ratio}:h=-1[{scaled}][vref{i}]"
            )
            # scale2ref trả lại luôn nhánh video nền — phải dùng nhãn mới của nó.
            final_video_label = f"vref{i}"

            # x/y là toạ độ TÂM ảnh theo tỉ lệ khung hình, khớp cách đặt của
            # overlay text để 2 loại dùng chung logic kéo-thả ở frontend.
            x_expr = f"main_w*{img.get('x', 0.9)}-overlay_w/2"
            y_expr = f"main_h*{img.get('y', 0.1)}-overlay_h/2"

            enable = ""
            if img.get("start") is not None and img.get("end") is not None:
                enable = f":enable='between(t,{img['start']},{img['end']})'"

            opacity = img.get("opacity", 1.0)
            if opacity < 1.0:
                faded = f"imgf{i}"
                filter_parts.append(
                    f"[{scaled}]format=rgba,colorchannelmixer=aa={opacity}[{faded}]"
                )
                source_label = faded
            else:
                source_label = scaled

            filter_parts.append(
                f"[{final_video_label}][{source_label}]"
                f"overlay=x={x_expr}:y={y_expr}{enable}[{out_label}]"
            )
            final_video_label = out_label

    # --- track audio: trim + volume + dịch tới track_start rồi trộn (amix) ---
    audio_labels: list[str] = []
    for t_i, track in enumerate(audio_tracks):
        for c_i, clip in enumerate(track.get("clips", [])):
            idx = add_input(clip["source"])
            label = f"a{t_i}_{c_i}"
            volume = clip.get("volume", 1.0)
            delay_ms = int(clip.get("track_start", 0) * 1000)
            filter_parts.append(
                f"[{idx}:a]atrim=start={clip['start']}:end={clip['end']},"
                f"asetpts=PTS-STARTPTS,volume={volume},"
                f"adelay={delay_ms}:all=1[{label}]"
            )
            audio_labels.append(label)

    final_audio_label: str | None = None
    if len(audio_labels) == 1:
        final_audio_label = audio_labels[0]
    elif len(audio_labels) > 1:
        joined = "".join(f"[{label}]" for label in audio_labels)
        filter_parts.append(
            f"{joined}amix=inputs={len(audio_labels)}:duration=longest[amixed]"
        )
        final_audio_label = "amixed"

    cmd = ["ffmpeg", "-y"]
    for source in inputs:
        cmd += ["-i", source]
    cmd += ["-filter_complex", ";".join(filter_parts)]
    cmd += ["-map", f"[{final_video_label}]"]
    if final_audio_label:
        cmd += ["-map", f"[{final_audio_label}]"]
    cmd += ["-c:v", "libx264", "-c:a", "aac", str(output_path)]

    subprocess.run(cmd, check=True, capture_output=True)


def crop_vertical(input_path: Path, output_path: Path, *, x: int, y: int, width: int, height: int) -> None:
    """Crop tĩnh theo khung cố định (Phase 11) — dùng cho crop dọc 9:16 bán tự động."""
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", f"crop={width}:{height}:{x}:{y}",
            "-c:a", "copy",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def make_placeholder_image(output_path: Path, *, label: str, width: int, height: int) -> None:
    """Ảnh test có chữ chèn sẵn — dùng cho adapter giả ở chế độ phát triển
    (app/adapters/falai/fake.py). Để ở đây vì chi tiết escape của filter
    `drawtext` thuộc về adapter ffmpeg, không nên rò ra ngoài."""
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"testsrc=size={width}x{height}:duration=1",
            "-vf", _drawtext_filter(label),
            "-frames:v", "1",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def make_placeholder_video(
    output_path: Path, *, label: str, duration_seconds: float, width: int, height: int
) -> None:
    """Video test có chữ + tone audio — dùng cho adapter giả ở chế độ phát triển.
    Có cả video và audio stream để pipeline phía sau (ghép, render timeline) xử lý
    được y như file thật."""
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"testsrc=size={width}x{height}:duration={duration_seconds}",
            "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={duration_seconds}",
            "-vf", _drawtext_filter(label),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def _drawtext_filter(label: str) -> str:
    fontfile = _escape_filter_path(_resolve_default_fontfile())
    text = _escape_drawtext(label)
    return f"drawtext=fontfile='{fontfile}':text='{text}':fontsize=28:fontcolor=white:x=20:y=20"


_KEN_BURNS_FPS = 30
_KEN_BURNS_ZOOM_END = 1.15

# Framerate chuẩn hoá khi dựng timeline — xem chú thích ở `render_timeline`.
_TIMELINE_FPS = 30


def make_ken_burns_clip(
    image_path: Path,
    output_path: Path,
    *,
    duration_seconds: float,
    motion: str = "zoom_in",
    width: int = 1280,
    height: int = 720,
) -> None:
    """Sinh clip từ 1 ảnh tĩnh với chuyển động camera chậm (Ken Burns).

    Đường thay thế miễn phí cho sinh video AI ở những cảnh không cần chuyển động
    thật — sinh ảnh rẻ hơn sinh video ~50-100 lần, xem "Chiến lược giảm chi phí"
    trong docs/phases/phase-14-ai-video-generation.md.

    Phóng ảnh lên gấp 4 trước khi zoompan: filter `zoompan` lấy mẫu từ ảnh gốc,
    zoom trực tiếp trên ảnh nhỏ sẽ ra kết quả rỗ. Nhân đôi `d` theo fps vì
    `zoompan` đếm bằng frame chứ không phải giây.
    """
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_frames = max(1, int(duration_seconds * _KEN_BURNS_FPS))
    if motion == "zoom_out":
        zoom_expr = f"{_KEN_BURNS_ZOOM_END}-({_KEN_BURNS_ZOOM_END}-1)*on/{total_frames}"
    elif motion == "pan_right":
        zoom_expr = str(_KEN_BURNS_ZOOM_END)
    else:
        zoom_expr = f"1+({_KEN_BURNS_ZOOM_END}-1)*on/{total_frames}"

    if motion == "pan_right":
        x_expr = f"(iw-iw/zoom)*on/{total_frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    video_filter = (
        f"scale={width * 4}:{height * 4},"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}'"
        f":d={total_frames}:s={width}x{height}:fps={_KEN_BURNS_FPS},"
        f"format=yuv420p"
    )

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-vf", video_filter,
            "-t", str(duration_seconds),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def replace_audio_track(video_path: Path, new_audio_path: Path, output_path: Path) -> None:
    """Thay toàn bộ audio track của video bằng file audio mới (Phase 2: chưa giữ nhạc nền gốc).

    Re-encode audio sang AAC vì track mới thường khác codec input (mp3 từ TTS);
    giữ nguyên video stream (copy) để không tốn thời gian re-encode video.
    `-shortest` để cắt theo track ngắn hơn nếu audio/video lệch thời lượng.
    """
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(new_audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
