import pytest

from app.services import tts_service


class TestHasSpeakableContent:
    """Edge-TTS báo "No audio was received" khi văn bản không có gì để đọc —
    lỗi input chứ không phải lỗi mạng, nên phải lọc trước khi gọi."""

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
        """Không được retry 3 lần với văn bản vốn không đọc được."""
        with pytest.raises(tts_service.TtsFailedError, match="không có nội dung đọc được"):
            await tts_service._synthesize_with_edge_retry("...", tmp_path / "out.mp3")

    @pytest.mark.anyio
    async def test_retries_on_transient_failure(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lỗi tạm thời phía dịch vụ thì retry mới có tác dụng."""
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
