import subprocess
from pathlib import Path

import pytest

from app.services import clip_service


class TestBuildClipTimeline:
    def test_single_video_clip_with_offset_start_end(self) -> None:
        ops = clip_service.build_clip_timeline("video.mp4", [], start=10, end=20)
        assert ops == {"tracks": [{"type": "video", "clips": [{"source": "video.mp4", "start": 10, "end": 20}]}]}

    def test_includes_crop_when_given(self) -> None:
        crop = {"x": 0, "y": 0, "width": 720, "height": 1280}
        ops = clip_service.build_clip_timeline("video.mp4", [], start=0, end=5, crop=crop)
        assert ops["tracks"][0]["clips"][0]["crop"] == crop

    def test_raises_when_end_not_after_start(self) -> None:
        with pytest.raises(ValueError):
            clip_service.build_clip_timeline("video.mp4", [], start=10, end=5)

    def test_caption_timestamps_rebased_to_clip_start(self) -> None:
        segments = [{"start": 12, "end": 15, "translated_text": "xin chào"}]
        ops = clip_service.build_clip_timeline("video.mp4", segments, start=10, end=20)
        overlay_track = next(t for t in ops["tracks"] if t["type"] == "overlay")
        assert overlay_track["clips"][0] == {
            "text": "xin chào",
            "start": 2.0,
            "end": 5.0,
            "x": 0.5,
            "y": 0.85,
        }

    def test_excludes_captions_outside_clip_range(self) -> None:
        segments = [
            {"start": 0, "end": 5, "translated_text": "trước clip"},
            {"start": 12, "end": 15, "translated_text": "trong clip"},
            {"start": 25, "end": 30, "translated_text": "sau clip"},
        ]
        ops = clip_service.build_clip_timeline("video.mp4", segments, start=10, end=20)
        overlay_track = next(t for t in ops["tracks"] if t["type"] == "overlay")
        assert len(overlay_track["clips"]) == 1
        assert overlay_track["clips"][0]["text"] == "trong clip"

    def test_clamps_caption_partially_overlapping_clip_boundary(self) -> None:
        segments = [{"start": 8, "end": 22, "translated_text": "trải dài qua biên"}]
        ops = clip_service.build_clip_timeline("video.mp4", segments, start=10, end=20)
        overlay_track = next(t for t in ops["tracks"] if t["type"] == "overlay")
        clip = overlay_track["clips"][0]
        assert clip["start"] == 0.0  # 8-10 âm, clamp về 0
        assert clip["end"] == 10.0  # 22-10=12 vượt quá 20-10=10, clamp về 10

    def test_skips_captions_with_empty_text(self) -> None:
        segments = [{"start": 12, "end": 15, "translated_text": "", "text": ""}]
        ops = clip_service.build_clip_timeline("video.mp4", segments, start=10, end=20)
        assert not any(t["type"] == "overlay" for t in ops["tracks"])

    def test_adds_cta_overlay_spanning_whole_clip(self) -> None:
        ops = clip_service.build_clip_timeline(
            "video.mp4", [], start=10, end=20, cta_text="Xem full tại YouTube"
        )
        overlay_track = next(t for t in ops["tracks"] if t["type"] == "overlay")
        cta = overlay_track["clips"][-1]
        assert cta["text"] == "Xem full tại YouTube"
        assert cta["start"] == 0
        assert cta["end"] == 10  # end - start = 20 - 10

    def test_no_overlay_track_when_no_captions_or_cta(self) -> None:
        ops = clip_service.build_clip_timeline("video.mp4", [], start=0, end=5)
        assert len(ops["tracks"]) == 1
        assert ops["tracks"][0]["type"] == "video"


class TestRenderClip:
    def test_renders_a_real_cropped_captioned_clip(self, tmp_path: Path) -> None:
        source = tmp_path / "source.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=6:size=640x480:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                "-c:v", "libx264", "-c:a", "aac",
                str(source),
            ],
            check=True,
            capture_output=True,
        )
        output = tmp_path / "clip.mp4"
        segments = [{"start": 1.0, "end": 3.0, "translated_text": "đoạn giữa clip"}]

        clip_service.render_clip(
            str(source),
            segments,
            output,
            start=0,
            end=4,
            crop={"x": 80, "y": 0, "width": 270, "height": 480},
            cta_text="Xem full tại YouTube",
        )

        assert output.exists()
        from app.adapters import ffmpeg

        width, height = ffmpeg.get_video_dimensions(output)
        assert (width, height) == (270, 480)
