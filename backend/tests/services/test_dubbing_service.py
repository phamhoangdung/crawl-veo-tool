from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services import dubbing_service
from pydub import AudioSegment


def _make_mp3(path, duration_ms: int) -> None:
    AudioSegment.silent(duration=duration_ms).export(path, format="mp3")


@pytest.mark.asyncio
async def test_matched_duration_skips_stretch_when_close_enough(
    tmp_path, dummy_session
):
    raw_path = tmp_path / "segment_0_raw.mp3"

    async def fake_synthesize(_db, _user_id, _text, output_path, voice=None):
        _make_mp3(output_path, duration_ms=2000)

    with (
        patch(
            "app.services.tts_service.synthesize_speech",
            new=AsyncMock(side_effect=fake_synthesize),
        ),
        patch("app.adapters.ffmpeg.time_stretch") as mock_stretch,
    ):
        clip = await dubbing_service._synthesize_segment_matched_duration(
            dummy_session,
            1,
            "xin chào",
            target_duration_s=2.03,
            tmp_dir=tmp_path,
            index=0,
        )

    mock_stretch.assert_not_called()
    assert clip is not None
    # File tạm đã nạp vào bộ nhớ (`clip`) thì dọn ngay — xem
    # docs/performance-optimization/plan.md mục P1.
    assert not raw_path.exists()


@pytest.mark.asyncio
async def test_matched_duration_stretches_when_duration_mismatched(
    tmp_path, dummy_session
):
    async def fake_synthesize(_db, _user_id, _text, output_path, voice=None):
        _make_mp3(output_path, duration_ms=4000)

    stretched_path = tmp_path / "segment_0_stretched.mp3"

    def fake_stretch(_input_path, output_path, _factor):
        _make_mp3(output_path, duration_ms=2000)

    with (
        patch(
            "app.services.tts_service.synthesize_speech",
            new=AsyncMock(side_effect=fake_synthesize),
        ),
        patch(
            "app.adapters.ffmpeg.time_stretch", side_effect=fake_stretch
        ) as mock_stretch,
    ):
        clip = await dubbing_service._synthesize_segment_matched_duration(
            dummy_session,
            1,
            "xin chào",
            target_duration_s=2.0,
            tmp_dir=tmp_path,
            index=0,
        )

    mock_stretch.assert_called_once()
    called_factor = mock_stretch.call_args[0][2]
    assert called_factor == pytest.approx(2.0, abs=0.01)
    assert clip is not None
    # File tạm (raw lẫn stretched) đã nạp vào bộ nhớ thì dọn ngay.
    assert not stretched_path.exists()
    assert not (tmp_path / "segment_0_raw.mp3").exists()


@pytest.mark.asyncio
async def test_matched_duration_returns_none_when_tts_fails(tmp_path, dummy_session):
    from app.services.tts_service import TtsFailedError

    with patch(
        "app.services.tts_service.synthesize_speech",
        new=AsyncMock(side_effect=TtsFailedError("boom")),
    ):
        clip = await dubbing_service._synthesize_segment_matched_duration(
            dummy_session,
            1,
            "xin chào",
            target_duration_s=2.0,
            tmp_dir=tmp_path,
            index=0,
        )

    assert clip is None


@pytest.mark.asyncio
async def test_matched_duration_forwards_voice_to_tts(tmp_path, dummy_session):
    """Phase 19: giọng gán riêng cho 1 vai phải tới đúng `tts_service.synthesize_speech`."""
    captured: dict = {}

    async def fake_synthesize(_db, _user_id, _text, output_path, voice=None):
        captured["voice"] = voice
        _make_mp3(output_path, duration_ms=2000)

    voice_ref = {"provider": "edge", "voice_id": "vi-VN-NamMinhNeural"}
    with patch(
        "app.services.tts_service.synthesize_speech",
        new=AsyncMock(side_effect=fake_synthesize),
    ):
        await dubbing_service._synthesize_segment_matched_duration(
            dummy_session,
            1,
            "xin chào",
            target_duration_s=2.0,
            tmp_dir=tmp_path,
            index=0,
            voice=voice_ref,
        )

    assert captured["voice"] == voice_ref


class TestRunDiarize:
    def test_raises_when_no_transcript(self, dummy_session) -> None:
        video = SimpleNamespace(transcript_json=None, local_path="video.mp4")
        with pytest.raises(ValueError, match="Chưa có lời thoại"):
            dubbing_service.run_diarize(dummy_session, video)

    def test_assigns_speakers_and_commits(self, tmp_path, monkeypatch) -> None:
        video_dir = tmp_path / "video1"
        video_dir.mkdir()
        video = SimpleNamespace(
            transcript_json=[{"start": 0.0, "end": 1.0, "text": "a"}],
            local_path=str(video_dir / "source.mp4"),
        )
        db = MagicMock()

        extract_audio = MagicMock()
        monkeypatch.setattr(dubbing_service.ffmpeg, "extract_audio", extract_audio)
        labeled = [{"start": 0.0, "end": 1.0, "text": "a", "speaker": "SPEAKER_00"}]
        assign_speakers = MagicMock(return_value=labeled)
        monkeypatch.setattr(
            dubbing_service.diarization_adapter, "assign_speakers", assign_speakers
        )

        dubbing_service.run_diarize(db, video)

        extract_audio.assert_called_once()
        assign_speakers.assert_called_once()
        assert video.transcript_json == labeled
        db.commit.assert_called_once()

    def test_skips_extract_audio_when_already_exists(
        self, tmp_path, monkeypatch
    ) -> None:
        video_dir = tmp_path / "video1"
        video_dir.mkdir()
        (video_dir / "original_audio.wav").write_bytes(b"fake")
        video = SimpleNamespace(
            transcript_json=[{"start": 0.0, "end": 1.0, "text": "a"}],
            local_path=str(video_dir / "source.mp4"),
        )
        db = MagicMock()

        extract_audio = MagicMock()
        monkeypatch.setattr(dubbing_service.ffmpeg, "extract_audio", extract_audio)
        monkeypatch.setattr(
            dubbing_service.diarization_adapter,
            "assign_speakers",
            MagicMock(return_value=[]),
        )

        dubbing_service.run_diarize(db, video)

        extract_audio.assert_not_called()
