"""render_timeline dựng filter_complex ffmpeg động — test bằng ffmpeg thật (không
mock subprocess), vì mock sẽ không phát hiện được lỗi cú pháp filter_complex, đúng
loại lỗi dễ gặp nhất khi dựng chuỗi filter bằng tay."""

import json
import subprocess
from pathlib import Path

import pytest

from app.adapters import ffmpeg


def _probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _make_test_clip(path: Path, *, duration: float, color: str, with_audio: bool = True, freq: int = 440) -> None:
    args = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=25:decimals=2",
    ]
    filter_args: list[str] = []
    if with_audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}"]
        filter_args = ["-c:a", "aac"]
    else:
        filter_args = ["-an"]
    args += ["-vf", f"drawbox=color={color}@1.0:t=fill", "-c:v", "libx264", *filter_args, str(path)]
    subprocess.run(args, check=True, capture_output=True)


@pytest.fixture
def clip_a(tmp_path: Path) -> Path:
    path = tmp_path / "clip_a.mp4"
    _make_test_clip(path, duration=2.0, color="red")
    return path


@pytest.fixture
def clip_b(tmp_path: Path) -> Path:
    path = tmp_path / "clip_b.mp4"
    _make_test_clip(path, duration=2.0, color="blue", freq=880)
    return path


@pytest.fixture
def music_clip(tmp_path: Path) -> Path:
    path = tmp_path / "music.mp3"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=4",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


class TestRenderTimelineSingleClip:
    def test_single_video_clip_no_audio_tracks(self, tmp_path: Path, clip_a: Path) -> None:
        output = tmp_path / "out.mp4"
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": str(clip_a), "start": 0, "end": 2}]},
            ]
        }

        ffmpeg.render_timeline(operations, output)

        assert output.exists()
        info = _probe(output)
        video_streams = [s for s in info["streams"] if s["codec_type"] == "video"]
        assert len(video_streams) == 1
        assert float(info["format"]["duration"]) == pytest.approx(2.0, abs=0.3)

    def test_raises_when_no_video_track(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="video"):
            ffmpeg.render_timeline({"tracks": []}, tmp_path / "out.mp4")


class TestRenderTimelineMultiClip:
    def test_hard_cut_concatenates_clips(self, tmp_path: Path, clip_a: Path, clip_b: Path) -> None:
        output = tmp_path / "out.mp4"
        operations = {
            "tracks": [
                {
                    "type": "video",
                    "clips": [
                        {"source": str(clip_a), "start": 0, "end": 2},
                        {"source": str(clip_b), "start": 0, "end": 2, "transition_in": "cut"},
                    ],
                },
            ]
        }

        ffmpeg.render_timeline(operations, output)

        info = _probe(output)
        assert float(info["format"]["duration"]) == pytest.approx(4.0, abs=0.4)

    def test_fade_transition_shortens_total_duration(
        self, tmp_path: Path, clip_a: Path, clip_b: Path
    ) -> None:
        """xfade chồng lấn `transition_duration` giây giữa 2 clip — tổng thời lượng
        phải NGẮN HƠN cộng đơn giản 2 clip (2+2=4s), không phải bằng nó."""
        output = tmp_path / "out.mp4"
        operations = {
            "tracks": [
                {
                    "type": "video",
                    "clips": [
                        {"source": str(clip_a), "start": 0, "end": 2},
                        {
                            "source": str(clip_b),
                            "start": 0,
                            "end": 2,
                            "transition_in": "fade",
                            "transition_duration": 0.5,
                        },
                    ],
                },
            ]
        }

        ffmpeg.render_timeline(operations, output)

        info = _probe(output)
        duration = float(info["format"]["duration"])
        assert duration == pytest.approx(3.5, abs=0.4)
        assert duration < 3.9


class TestRenderTimelineAudioTracks:
    def test_mixes_multiple_audio_tracks(
        self, tmp_path: Path, clip_a: Path, music_clip: Path
    ) -> None:
        output = tmp_path / "out.mp4"
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": str(clip_a), "start": 0, "end": 2}]},
                {
                    "type": "audio",
                    "role": "voice",
                    "clips": [{"source": str(clip_a), "start": 0, "end": 2, "track_start": 0, "volume": 1.0}],
                },
                {
                    "type": "audio",
                    "role": "music",
                    "clips": [{"source": str(music_clip), "start": 0, "end": 2, "track_start": 0, "volume": 0.3}],
                },
            ]
        }

        ffmpeg.render_timeline(operations, output)

        info = _probe(output)
        audio_streams = [s for s in info["streams"] if s["codec_type"] == "audio"]
        assert len(audio_streams) == 1  # đã amix thành 1 track duy nhất


class TestRenderTimelineCrop:
    def test_crop_field_on_video_clip_produces_cropped_output(
        self, tmp_path: Path, clip_a: Path
    ) -> None:
        output = tmp_path / "out.mp4"
        operations = {
            "tracks": [
                {
                    "type": "video",
                    "clips": [
                        {
                            "source": str(clip_a),
                            "start": 0,
                            "end": 2,
                            "crop": {"x": 60, "y": 0, "width": 200, "height": 240},
                        }
                    ],
                },
            ]
        }

        ffmpeg.render_timeline(operations, output)

        width, height = ffmpeg.get_video_dimensions(output)
        assert (width, height) == (200, 240)


class TestRenderTimelineOverlay:
    def test_overlay_text_does_not_break_render(self, tmp_path: Path, clip_a: Path) -> None:
        """Không verify được nội dung chữ bằng ffprobe (không OCR) — chỉ verify
        drawtext không làm hỏng lệnh ffmpeg (lỗi cú pháp filter dễ gặp nhất khi
        dựng chuỗi bằng tay, escape sai dấu ':' hoặc dấu nháy là ví dụ điển hình)."""
        output = tmp_path / "out.mp4"
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": str(clip_a), "start": 0, "end": 2}]},
                {
                    "type": "overlay",
                    "clips": [
                        {
                            "text": "Xem full: youtube.com/@test (link ở bio)",
                            "start": 0,
                            "end": 2,
                            "x": 0.5,
                            "y": 0.9,
                        }
                    ],
                },
            ]
        }

        ffmpeg.render_timeline(operations, output)

        assert output.exists()
        info = _probe(output)
        assert float(info["format"]["duration"]) == pytest.approx(2.0, abs=0.3)


class TestCropVertical:
    def test_crops_to_requested_dimensions(self, tmp_path: Path, clip_a: Path) -> None:
        output = tmp_path / "cropped.mp4"

        ffmpeg.crop_vertical(clip_a, output, x=60, y=0, width=200, height=240)

        width, height = ffmpeg.get_video_dimensions(output)
        assert (width, height) == (200, 240)
