import logging
import platform
import re
import subprocess
from pathlib import Path

from app.core.ffmpeg_locator import ensure_ffmpeg_on_path
from app.services import font_service

logger = logging.getLogger(__name__)

# Default font for drawtext (Phase 13 overlay) — `fontfile` is specified directly
# instead of letting the filter probe via fontconfig. On many prebuilt ffmpeg builds
# (portable build, or the Phase 12 desktop package) fontconfig has no usable
# config file ("Fontconfig error: Cannot load default config file") —
# this error makes drawtext CRASH (access violation) instead of reporting a clear error, instead of
# merely not showing the text. Specifying fontfile ourselves avoids depending on fontconfig.
_DEFAULT_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


class FfmpegNotFoundError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Không tìm thấy ffmpeg (đã tìm trong PATH, registry và các thư mục cài phổ biến). "
            "Cài bằng: winget install Gyan.FFmpeg — rồi thử lại, không cần mở lại app."
        )


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
    """Escape a path so it can be safely put into an ffmpeg filter (`:` is the filter
    delimiter, and the `\\` of Windows paths also needs escaping) — same approach already used in
    `burn_subtitles` for the .srt file path."""
    return path.replace("\\", "/").replace(":", "\\:")


def ensure_ffmpeg_available() -> None:
    # Look again in the registry/common install directories before reporting it missing — an app opened from
    # the installer may not inherit the user's PATH.
    if not ensure_ffmpeg_on_path():
        raise FfmpegNotFoundError()


def merge_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> None:
    """Merge a video-only + audio-only stream (DASH) into 1 mp4 file, copying codecs (no re-encode)."""
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
    """Extract the audio track into a separate wav file (input for Demucs)."""
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le", str(output_path)],
        check=True,
        capture_output=True,
    )


def time_stretch(input_path: Path, output_path: Path, factor: float) -> None:
    """Stretch the audio duration by `factor` (keeping pitch) with ffmpeg's `atempo` filter.

    `atempo` only accepts a factor in [0.5, 2.0] per pass — a factor outside this range needs chaining
    several `atempo` passes; rare for a single line of dialogue, so we clamp to the bound instead of chaining, for simplicity.
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
    """Mix 2 audio tracks (e.g. the new narration + the separated background music) into 1 track."""
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
    """Real duration of the video. Returns None when it cannot be read, leaving the caller to
    decide (unlike `probe_video_width`, which has a sensible default — for duration
    there is no number one can guess that is still right)."""
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


def extract_thumbnail(
    video_path: Path, output_path: Path, *, at_seconds: float = 1.0
) -> None:
    """Extract 1 frame as the cover image for a video imported from disk (videos downloaded from a
    platform already have their own cover_url; self-owned videos do not).

    Seek before `-i` for speed; a clip shorter than `at_seconds` falls back to the middle of the clip so
    the image is not empty.
    """
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration = probe_duration_seconds(video_path)
    if duration is not None and duration <= at_seconds:
        at_seconds = duration / 2

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(at_seconds),
            "-i", str(video_path),
            "-frames:v", "1",
            "-vf", "scale=640:-2",
            "-q:v", "3",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def extract_last_frame(
    video_path: Path, output_path: Path, *, offset_from_end: float = 0.05
) -> None:
    """Extract the last frame of a clip as an image — used as the opening keyframe of the next scene
    (frame chaining, see docs/phases/phase-15-node-canvas.md).

    Step back `offset_from_end` seconds from the end: seeking exactly to the very end
    usually lands past the last decodable frame and yields an empty image.
    """
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration = probe_duration_seconds(video_path)
    seek_args: list[str] = []
    if duration is not None:
        # -ss before -i for fast seeking (no decoding from the start of the clip).
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


# Alignment in `force_style` follows SSA v4 numbering (2 = bottom-center, +4 = pushed
# to the top => 6 = top-center), NOT the numpad layout of ASS v4+ that everyone
# assumes. Measured with real ffmpeg: Alignment=8 puts the text in the MIDDLE of the frame, not
# the top — and it reports no error, just silently puts it in the wrong place.
_SUBTITLE_ALIGNMENT = {"bottom": 2, "top": 6}


_HEX_COLOR_RE = re.compile(r"^[0-9a-fA-F]{6}$")


def _validate_hex_color(hex_color: str) -> str:
    """`#RRGGBB`/`RRGGBB` → validated `RRGGBB`. Checking only the length is
    not enough — a 6-character string that is not hex (e.g. containing `:` or `'`) would still slip
    through and be pasted straight into the ffmpeg filter, possibly breaking the `-vf` syntax (`:` is the
    filter option delimiter) instead of reporting a clear error here."""
    h = hex_color.lstrip("#")
    if not _HEX_COLOR_RE.fullmatch(h):
        raise ValueError(
            f"Màu phải ở dạng hex 6 ký tự 0-9a-f (vd 'FFFFFF'), nhận: {hex_color!r}"
        )
    return h


def _hex_to_ass_color(hex_color: str) -> str:
    """`RRGGBB` (HTML color picker format) → `&H00BBGGRR&` (the `PrimaryColour` format
    of ASS/SSA — BGR order, the first byte is alpha with 00 = fully opaque). Swapping the byte
    order is an easy mistake and ffmpeg reports nothing, just silently outputs the wrong color — the same
    kind of trap as with `Alignment` (see the Phase 5 notes)."""
    h = _validate_hex_color(hex_color)
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}&"


def burn_subtitles(
    video_path: Path,
    srt_path: Path,
    output_path: Path,
    *,
    font_size: int,
    position: str = "bottom",
    font_family: str | None = None,
    font_color: str = "FFFFFF",
    bold: bool = False,
) -> None:
    """Burn subtitles into the video. `font_size` should be chosen by aspect ratio (a vertical 9:16 video
    needs relatively larger text because the frame is narrow) — see `subtitle_service.pick_font_size_for`.

    `position` = "bottom" (default, standard subtitle placement) or "top" — place
    on top when the source video already has burned-in subtitles at the bottom, otherwise the two text layers would
    overlap.

    `font_family` is an id in `font_service` (None = default font). Uses
    `fontsdir` pointing at the bundled font directory so libass finds the right font
    WITHOUT probing system fontconfig — same reason `drawtext` must specify
    `fontfile` directly (Phase 13 note): a machine lacking the fontconfig config file
    fails silently or crashes instead of reporting clearly.

    The srt path must escape `:` and `\\` for ffmpeg filter syntax on Windows.
    """
    ensure_ffmpeg_available()
    alignment = _SUBTITLE_ALIGNMENT.get(position)
    if alignment is None:
        raise ValueError(
            f"Vị trí phụ đề không hợp lệ: {position!r} (chỉ nhận {sorted(_SUBTITLE_ALIGNMENT)})"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_srt = str(srt_path).replace("\\", "/").replace(":", "\\:")
    escaped_fontsdir = _escape_filter_path(str(font_service.fonts_dir()))
    font = font_service.get_font_or_default(font_family)
    ass_color = _hex_to_ass_color(font_color)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf",
            f"subtitles='{escaped_srt}':fontsdir='{escaped_fontsdir}':"
            f"force_style='FontName={font.family_name},FontSize={font_size},"
            f"PrimaryColour={ass_color},Bold={1 if bold else 0},"
            f"Outline=1,Alignment={alignment}'",
            "-c:a", "copy",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def _escape_drawtext(text: str) -> str:
    """Escape special characters for the `drawtext` filter — same kind of escaping used in
    `burn_subtitles` for the `subtitles` filter; drawtext additionally needs the single quote escaped
    because the text is wrapped in `'...'`."""
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def probe_video_width(path: str | Path) -> int:
    """Real width of the video, used to convert the proportional subtitle box into a character count.

    Returns 1080 when it cannot be read (vertical video is the most common) — better a slightly off wrap
    than killing the whole render.
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
    """Han characters are almost twice as wide as Latin ones, so the characters that fit on one line differ."""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _wrap_text_to_box(text: str, max_chars: int) -> str:
    """Split a sentence into several lines to fit the subtitle box.

    `drawtext` does NOT wrap on its own — a long sentence would overflow the frame and be
    cut off. We must insert '\n' ourselves here.

    Break by word, but a word longer than a whole line is hard-cut mid-word (better to
    break mid-word than to overflow). Chinese has no spaces between characters,
    so it almost always takes the hard-cut branch — which is the correct behavior for Chinese.
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
    """Render 1 timeline (Phase 13) into a finished video — builds `-filter_complex`
    dynamically from the JSON "edit operations" instead of the fixed single-purpose functions above.

    Expected structure of `operations`:
    {
      "tracks": [
        {"type": "video", "clips": [
            {"source": "path.mp4", "start": 0, "end": 10,
             "transition_in": "cut"|"fade", "transition_duration": 1.0,
             "crop": {"x": 0, "y": 0, "width": 720, "height": 1280}}, ...  # optional, Phase 11
        ]},
        {"type": "audio", "role": "voice"|"music", "clips": [
            {"source": "path.mp3", "start": 0, "end": 10,
             "track_start": 0, "volume": 1.0}, ...
        ]},
        {"type": "overlay", "clips": [
            {"text": "...", "start": 0, "end": 5, "x": 0.5, "y": 0.9, "font_size": 32,
             "font_family": "be-vietnam-pro", "font_color": "FFFFFF", "bold": False}, ...  # font_* optional
        ]}
      ]
    }

    Exactly 1 "video" track (several clips in sequence, with a transition between 2 consecutive
    clips), 0+ "audio" tracks (mixed with amix, each track with its own volume —
    used for basic ducking: set the background music volume lower than the narration), 0-1
    "overlay" track (drawtext, shown/hidden by time ranges via `enable`).

    Known limitation (MVP): xfade assumes the video clips share resolution/fps —
    inputs with mismatched formats need normalizing beforehand (not automated in this version).
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

    # --- video track: trim (+ optional crop, Phase 11) each clip, then join/transition ---
    video_labels: list[tuple[str, dict]] = []
    for i, clip in enumerate(video_track["clips"]):
        idx = add_input(clip["source"])
        label = f"v{i}"
        crop = clip.get("crop")
        crop_filter = (
            f",crop={crop['width']}:{crop['height']}:{crop['x']}:{crop['y']}" if crop else ""
        )
        # `fps` + `settb` are required, not an optimization: `concat` outputs timebase
        # 1/1000000 and framerate "1/0" (undefined), while clips that have not been through concat
        # keep their original timebase (e.g. 1/15360). When some clip has `transition_in="fade"`
        # after a run of cuts, `xfade` fails with "timebase do not match" /
        # "needs to be a constant frame rate". Normalizing each clip before joining
        # lets every cut/fade combination be built.
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

    # --- blur: hide the logo / original subtitles with a blurred region ---
    # Placed BEFORE the text and image overlays: the purpose is to hide what is already in the source video,
    # doing it afterwards would also blur the text and logo we just added.
    if blur_track and blur_track.get("clips"):
        for i, region in enumerate(blur_track["clips"]):
            # Must `split` first: ffmpeg does NOT allow reusing the same label for 2
            # filter branches (one branch crops the region to blur, the other is the background).
            base = f"blurbase{i}"
            copy = f"blurcopy{i}"
            blurred = f"blurb{i}"
            out_label = f"blur{i}"
            filter_parts.append(f"[{final_video_label}]split=2[{base}][{copy}]")

            # x/y/w/h in frame RATIOS [0,1] so the covered region stays in the right place even if the video
            # changes resolution — matches how text and image overlays are placed.
            x = region.get("x", 0.0)
            y = region.get("y", 0.0)
            w = region.get("width", 0.2)
            h = region.get("height", 0.1)

            # Crop just the region to hide, blur it, then overlay it back in place. Blurring the whole
            # frame and then cropping would let colors from outside bleed into the region edges.
            strength = region.get("strength", 20)
            mode = region.get("mode", "blur")
            crop_expr = f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}"

            if mode == "pixelate":
                # Mosaic-style blur: scale down then scale back up with
                # nearest-neighbor interpolation. Hides Chinese text better than blur because the
                # strokes are no longer readable, while a strong blur still leaves the shape.
                block = max(2, int(strength))
                filter_parts.append(
                    f"[{copy}]{crop_expr},"
                    f"scale=iw/{block}:ih/{block},scale=iw*{block}:ih*{block}"
                    f":flags=neighbor[{blurred}]"
                )
            else:
                # gblur rather than boxblur: boxblur limits the radius by the size of the
                # cropped region (an 80x36px region only allows radius < 18), so a small
                # region would fail outright. gblur accepts an arbitrary sigma.
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

    # --- overlay: draw drawtext over the concatenated video track ---
    source_video_width: int | None = None
    if overlay_track and overlay_track.get("clips"):
        for i, ov in enumerate(overlay_track["clips"]):
            out_label = f"ov{i}"
            font_size = ov.get("font_size", 32)
            fontfile = _escape_filter_path(
                str(font_service.resolve_fontfile(ov.get("font_family"), bold=bool(ov.get("bold"))))
            )
            font_color = _validate_hex_color(str(ov.get("font_color", "FFFFFF")))

            raw_text = ov["text"]
            # Subtitle bounding box (`box_width` as a ratio of the frame width):
            # wrap lines to fit, because drawtext does not wrap itself. Estimate the number of characters
            # per line from font_size — Han characters are ~1 font_size wide, Latin ~0.5.
            box_width = ov.get("box_width")
            if box_width:
                # Read from the source video once, not for every clip.
                if source_video_width is None:
                    source_video_width = probe_video_width(video_track["clips"][0]["source"])
                video_width = source_video_width
                usable_px = video_width * float(box_width)
                char_px = font_size if _has_cjk(raw_text) else font_size * 0.55
                raw_text = _wrap_text_to_box(raw_text, int(usable_px / char_px))

            text = _escape_drawtext(raw_text)
            # x/y are the CENTER coordinates of the text as frame ratios [0,1] (0.5/0.5 = middle
            # of the frame) — matches exactly how the frontend drag-and-drop places the overlay's center point,
            # not the edge of the text box, so preview and render match.
            x_expr = f"w*{ov.get('x', 0.5)}-text_w/2"
            y_expr = f"h*{ov.get('y', 0.9)}-text_h/2"
            filter_parts.append(
                f"[{final_video_label}]drawtext=fontfile='{fontfile}':text='{text}':"
                f"x={x_expr}:y={y_expr}:"
                f"fontsize={font_size}:fontcolor=0x{font_color}:box=1:boxcolor=black@0.5:"
                f"enable='between(t,{ov['start']},{ov['end']})'[{out_label}]"
            )
            final_video_label = out_label

    # --- image/logo/watermark: overlay on top, after the text ---
    if image_track and image_track.get("clips"):
        for i, img in enumerate(image_track["clips"]):
            idx = add_input(img["source"])
            scaled = f"imgs{i}"
            out_label = f"img{i}"

            # Width as a frame RATIO [0,1] so the logo scales correctly even if the video
            # changes resolution. Uses `scale2ref` to know the base video size;
            # -1 keeps the original image aspect ratio.
            width_ratio = img.get("width", 0.15)
            filter_parts.append(
                f"[{idx}:v][{final_video_label}]scale2ref=w=iw*{width_ratio}:h=-1[{scaled}][vref{i}]"
            )
            # scale2ref also returns the base video branch — the new label of that branch must be used.
            final_video_label = f"vref{i}"

            # x/y are the CENTER coordinates of the image as frame ratios, matching how
            # text overlays are placed so the 2 kinds share the same drag-and-drop logic in the frontend.
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

    # --- audio track: trim + volume + shift to track_start, then mix (amix) ---
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
    """Static crop to a fixed frame (Phase 11) — used for semi-automatic 9:16 vertical crop."""
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
    """Test image with text pre-drawn — used by the fake adapter in development mode
    (app/adapters/falai/fake.py). Kept here because the escaping details of the
    `drawtext` filter belong to the ffmpeg adapter and should not leak outside."""
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
    """Test video with text + an audio tone — used by the fake adapter in development mode.
    Has both video and audio streams so the downstream pipeline (concat, timeline render) handles
    it just like a real file."""
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

# Normalized framerate when building a timeline — see the comment in `render_timeline`.
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
    """Generate a clip from a still image with slow camera motion (Ken Burns).

    A free alternative to AI video generation for scenes that do not need real
    motion — image generation is ~50-100x cheaper than video generation, see "Chiến lược giảm chi phí"
    in docs/phases/phase-14-ai-video-generation.md.

    Scale the image up 4x before zoompan: the `zoompan` filter samples from the source image,
    and zooming directly on a small image gives a grainy result. Double `d` by fps because
    `zoompan` counts in frames, not seconds.
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
    """Replace the whole audio track of the video with a new audio file (Phase 2: does not keep the original background music).

    Re-encode audio to AAC because the new track usually has a different codec from the input (mp3 from TTS);
    keep the video stream as is (copy) to avoid re-encoding the video.
    `-shortest` cuts to the shorter track if audio/video durations differ.
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


_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detect_silences(
    audio_path: Path, *, noise_db: int = -30, min_silence_seconds: float = 0.4
) -> list[tuple[float, float]]:
    """Silent intervals in the audio, as [(start, end), ...].

    Uses the `silencedetect` filter — it writes the result to **stderr** as a log,
    not stdout, so stderr must be read rather than parsing an output file. Output goes
    to `-f null` because we only need the log, not any file.

    A start/end pair can be unbalanced if the file ends in the middle of a silence
    (`silence_start` without a matching `silence_end`) — in that case the last
    interval is skipped instead of guessing its length.
    """
    ensure_ffmpeg_available()
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats",
            "-i", str(audio_path),
            "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_seconds}",
            "-f", "null", "-",
        ],
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    )
    starts = [float(m) for m in _SILENCE_START_RE.findall(result.stderr)]
    ends = [float(m) for m in _SILENCE_END_RE.findall(result.stderr)]
    return list(zip(starts, ends))


def slice_audio(input_path: Path, output_path: Path, start: float, end: float) -> None:
    """Cut an audio segment [start, end) into its own file, keeping the wav format.

    `-ss`/`-to` are placed AFTER `-i` on purpose: placed before, ffmpeg seeks to the nearest
    keyframe, with an error of up to a whole second — for audio that is concatenated afterwards, a mismatch is fatal.
    """
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(input_path),
            "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-acodec", "pcm_s16le",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def concat_audio(parts: list[Path], output_path: Path) -> None:
    """Concatenate the cut audio files in the right order (concat demuxer).

    Requires the parts to share format/sample rate — true here
    because they all come from the same cut of one source file.
    """
    ensure_ffmpeg_available()
    if not parts:
        raise ValueError("Không có phần nào để nối")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.parent / f"{output_path.stem}_concat.txt"
    # Paths in the file list must escape single quotes; use forward slashes for
    # Windows because ffmpeg reads the file list with its own syntax, not shell syntax.
    list_file.write_text(
        "\n".join(f"file '{str(p).replace(chr(92), '/')}'" for p in parts),
        encoding="utf-8",
    )
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(list_file),
                "-acodec", "pcm_s16le",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        list_file.unlink(missing_ok=True)
