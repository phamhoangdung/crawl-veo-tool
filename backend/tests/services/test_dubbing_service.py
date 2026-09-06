from unittest.mock import AsyncMock, patch

import pytest
from pydub import AudioSegment

from app.services import dubbing_service


def _make_mp3(path, duration_ms: int) -> None:
    AudioSegment.silent(duration=duration_ms).export(path, format="mp3")


@pytest.mark.asyncio
async def test_matched_duration_skips_stretch_when_close_enough(tmp_path, dummy_session):
    raw_path = tmp_path / "segment_0_raw.mp3"

    async def fake_synthesize(_db, _user_id, _text, output_path):
        _make_mp3(output_path, duration_ms=2000)

    with patch("app.services.tts_service.synthesize_speech", new=AsyncMock(side_effect=fake_synthesize)):
        with patch("app.adapters.ffmpeg.time_stretch") as mock_stretch:
            clip = await dubbing_service._synthesize_segment_matched_duration(
                dummy_session, 1, "xin chào", target_duration_s=2.03, tmp_dir=tmp_path, index=0
            )

    mock_stretch.assert_not_called()
    assert clip is not None
    assert raw_path.exists()


@pytest.mark.asyncio
async def test_matched_duration_stretches_when_duration_mismatched(tmp_path, dummy_session):
    async def fake_synthesize(_db, _user_id, _text, output_path):
        _make_mp3(output_path, duration_ms=4000)

    stretched_path = tmp_path / "segment_0_stretched.mp3"

    def fake_stretch(_input_path, output_path, _factor):
        _make_mp3(output_path, duration_ms=2000)

    with patch("app.services.tts_service.synthesize_speech", new=AsyncMock(side_effect=fake_synthesize)):
        with patch("app.adapters.ffmpeg.time_stretch", side_effect=fake_stretch) as mock_stretch:
            clip = await dubbing_service._synthesize_segment_matched_duration(
                dummy_session, 1, "xin chào", target_duration_s=2.0, tmp_dir=tmp_path, index=0
            )

    mock_stretch.assert_called_once()
    called_factor = mock_stretch.call_args[0][2]
    assert called_factor == pytest.approx(2.0, abs=0.01)
    assert clip is not None
    assert stretched_path.exists()


@pytest.mark.asyncio
async def test_matched_duration_returns_none_when_tts_fails(tmp_path, dummy_session):
    from app.services.tts_service import TtsFailedError

    with patch(
        "app.services.tts_service.synthesize_speech",
        new=AsyncMock(side_effect=TtsFailedError("boom")),
    ):
        clip = await dubbing_service._synthesize_segment_matched_duration(
            dummy_session, 1, "xin chào", target_duration_s=2.0, tmp_dir=tmp_path, index=0
        )

    assert clip is None
