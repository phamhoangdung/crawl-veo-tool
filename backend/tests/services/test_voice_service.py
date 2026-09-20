from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from app.services import voice_service


@pytest.mark.anyio
async def test_returns_only_edge_voices_when_no_elevenlabs_key(
    monkeypatch, dummy_session
):
    monkeypatch.setattr(
        voice_service.api_key_service,
        "get_decrypted_key",
        lambda _db, _uid, _provider: None,
    )

    voices = await voice_service.list_available_voices(dummy_session, 1)

    assert voices == voice_service._EDGE_VOICES
    assert all(v["provider"] == "edge" for v in voices)


@pytest.mark.anyio
async def test_merges_elevenlabs_voices_when_key_configured(monkeypatch, dummy_session):
    monkeypatch.setattr(
        voice_service.api_key_service,
        "get_decrypted_key",
        lambda _db, _uid, _provider: "fake-key",
    )

    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "voices": [
            {"voice_id": "abc123", "name": "Rachel", "labels": {"gender": "female"}},
        ]
    }
    monkeypatch.setattr(httpx.AsyncClient, "get", AsyncMock(return_value=fake_response))

    voices = await voice_service.list_available_voices(dummy_session, 1)

    assert len(voices) == len(voice_service._EDGE_VOICES) + 1
    added = voices[-1]
    assert added == {
        "provider": "elevenlabs",
        "voice_id": "abc123",
        "name": "Rachel",
        "gender": "female",
    }


@pytest.mark.anyio
async def test_falls_back_to_edge_voices_when_elevenlabs_request_fails(
    monkeypatch, dummy_session
):
    monkeypatch.setattr(
        voice_service.api_key_service,
        "get_decrypted_key",
        lambda _db, _uid, _provider: "fake-key",
    )
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(side_effect=httpx.ConnectError("boom")),
    )

    voices = await voice_service.list_available_voices(dummy_session, 1)

    assert voices == voice_service._EDGE_VOICES
