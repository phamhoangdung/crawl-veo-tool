from unittest.mock import AsyncMock

import pytest
from app.services import tts_service


class TestHasSpeakableContent:
    """Edge-TTS reports "No audio was received" when the text has nothing to read —
    an input error, not a network error, so it must be filtered before calling."""

    @pytest.mark.parametrize(
        "text",
        ["Xin chào", "Ừ!", "123", "a.", "Cơm ngon quá"],
    )
    def test_accepts_real_text(self, text: str) -> None:
        assert tts_service._has_speakable_content(text) is True

    @pytest.mark.parametrize("text", ["", "   ", "...", "!!!", "—", "?!"])
    def test_rejects_punctuation_only(self, text: str) -> None:
        assert tts_service._has_speakable_content(text) is False


class TestEdgeRetry:
    @pytest.mark.anyio
    async def test_fails_fast_on_unspeakable_text(self, tmp_path) -> None:
        """Must not retry 3 times with text that is inherently unreadable."""
        with pytest.raises(
            tts_service.TtsFailedError, match="không có nội dung đọc được"
        ):
            await tts_service._synthesize_with_edge_retry("...", tmp_path / "out.mp3")

    @pytest.mark.anyio
    async def test_retries_on_transient_failure(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A transient error on the service side is where retrying actually helps."""
        import edge_tts

        calls = {"count": 0}

        async def flaky(text: str, output_path, voice: str = "") -> None:
            calls["count"] += 1
            if calls["count"] < 2:
                raise edge_tts.exceptions.NoAudioReceived("tạm thời")

        monkeypatch.setattr(tts_service.edge_tts_adapter, "synthesize", flaky)
        monkeypatch.setattr(tts_service.asyncio, "sleep", lambda _: _noop())

        await tts_service._synthesize_with_edge_retry("Xin chào", tmp_path / "out.mp3")
        assert calls["count"] == 2


async def _noop() -> None:
    return None


class TestSynthesizeSpeechVoiceRouting:
    """Phase 19: `voice` says which voice is assigned to 1 speaker —
    None must keep the old default behavior (ElevenLabs pool then Edge fallback)."""

    @pytest.mark.anyio
    async def test_edge_voice_skips_elevenlabs_entirely(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, dummy_session
    ) -> None:
        pick_key = AsyncMock()
        monkeypatch.setattr(tts_service.api_key_service, "pick_decrypted_key", pick_key)
        edge_call = AsyncMock()
        monkeypatch.setattr(tts_service.edge_tts_adapter, "synthesize", edge_call)

        await tts_service.synthesize_speech(
            dummy_session,
            1,
            "Xin chào",
            tmp_path / "out.mp3",
            voice={"provider": "edge", "voice_id": "vi-VN-NamMinhNeural"},
        )

        pick_key.assert_not_called()
        edge_call.assert_awaited_once()
        assert edge_call.await_args.kwargs["voice"] == "vi-VN-NamMinhNeural"

    @pytest.mark.anyio
    async def test_elevenlabs_voice_passed_to_adapter(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, dummy_session
    ) -> None:
        monkeypatch.setattr(
            tts_service.api_key_service,
            "pick_decrypted_key",
            lambda _db, _user_id, _provider: (1, "fake-api-key"),
        )
        mark_result = lambda *a, **k: None
        monkeypatch.setattr(tts_service.api_key_service, "mark_key_result", mark_result)
        elevenlabs_call = AsyncMock()
        monkeypatch.setattr(
            tts_service.elevenlabs_adapter, "synthesize", elevenlabs_call
        )

        await tts_service.synthesize_speech(
            dummy_session,
            1,
            "Xin chào",
            tmp_path / "out.mp3",
            voice={"provider": "elevenlabs", "voice_id": "custom-voice-id"},
        )

        elevenlabs_call.assert_awaited_once()
        assert elevenlabs_call.await_args.kwargs["voice_id"] == "custom-voice-id"
