from unittest.mock import AsyncMock, call, patch

import httpx
import pytest

from app.adapters.provider_errors import AllProvidersExhaustedError, ProviderQuotaExceededError
from app.services import translate_service


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(translate_service.asyncio, "sleep", fast_sleep)


class TestCallWithRetry:
    """_call_with_retry chỉ retry khi 429 (rate limit) — lý do dịch từng đoạn phụ
    đề riêng lẻ dễ dồn dập gọi API và bị Google/OpenAI chặn tạm."""

    @pytest.mark.anyio
    async def test_retries_on_429_then_succeeds(self) -> None:
        attempts = 0

        async def flaky() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise _http_status_error(429)
            return "ok"

        result = await translate_service._call_with_retry("test", flaky)
        assert result == "ok"
        assert attempts == 3

    @pytest.mark.anyio
    async def test_gives_up_after_max_retries_raises_quota_exceeded(self) -> None:
        """Sau khi hết lượt retry vẫn 429 → chuyển thành ProviderQuotaExceededError
        (Phase 8), không phải httpx.HTTPStatusError thô — để translate_text biết đây
        là tín hiệu "key cần nghỉ" và xoay sang key khác trong pool."""

        async def always_429() -> str:
            raise _http_status_error(429)

        with pytest.raises(ProviderQuotaExceededError):
            await translate_service._call_with_retry("test", always_429)

    @pytest.mark.anyio
    async def test_non_429_error_raises_immediately(self) -> None:
        attempts = 0

        async def server_error() -> str:
            nonlocal attempts
            attempts += 1
            raise _http_status_error(500)

        with pytest.raises(httpx.HTTPStatusError):
            await translate_service._call_with_retry("test", server_error)
        assert attempts == 1


class TestTranslateText:
    """translate_text: xoay vòng key OpenAI trong pool khi hết quota, fallback Google
    free khi hết pool, và báo AllProvidersExhaustedError khi cả 2 đều lỗi (Phase 8)."""

    @pytest.mark.anyio
    async def test_uses_google_directly_when_no_openai_key_configured(self, dummy_session) -> None:
        with (
            patch(
                "app.services.translate_service.api_key_service.pick_decrypted_key",
                return_value=None,
            ),
            patch(
                "app.services.translate_service.google_translate.translate",
                new=AsyncMock(return_value="ok tiếng việt"),
            ) as mock_google,
        ):
            result = await translate_service.translate_text(dummy_session, 1, "hi", "en", "vi")

        assert result == "ok tiếng việt"
        mock_google.assert_awaited_once()

    @pytest.mark.anyio
    async def test_uses_openai_key_when_it_works(self, dummy_session) -> None:
        with (
            patch(
                "app.services.translate_service.api_key_service.pick_decrypted_key",
                return_value=(1, "key-a"),
            ),
            patch("app.services.translate_service.api_key_service.mark_key_result") as mock_mark,
            patch(
                "app.services.translate_service.openai_translate.translate",
                new=AsyncMock(return_value="dịch bởi openai"),
            ),
            patch(
                "app.services.translate_service.google_translate.translate",
                new=AsyncMock(),
            ) as mock_google,
        ):
            result = await translate_service.translate_text(dummy_session, 1, "hi", "en", "vi")

        assert result == "dịch bởi openai"
        mock_mark.assert_called_once_with(dummy_session, 1, success=True)
        mock_google.assert_not_awaited()

    @pytest.mark.anyio
    async def test_rotates_to_next_key_when_first_key_exhausted(self, dummy_session) -> None:
        """Key #1 bị 429 liên tục → đánh dấu thất bại, thử key #2 trong pool và
        thành công — không rơi xuống Google khi pool vẫn còn key active khác."""
        picks = iter([(1, "key-a"), (2, "key-b")])

        async def fake_translate(_client, api_key, *_args, **_kwargs):
            if api_key == "key-a":
                raise _http_status_error(429)
            return "dịch bởi key-b"

        with (
            patch(
                "app.services.translate_service.api_key_service.pick_decrypted_key",
                side_effect=lambda *_a, **_kw: next(picks, None),
            ),
            patch("app.services.translate_service.api_key_service.mark_key_result") as mock_mark,
            patch(
                "app.services.translate_service.openai_translate.translate",
                new=AsyncMock(side_effect=fake_translate),
            ),
        ):
            result = await translate_service.translate_text(dummy_session, 1, "hi", "en", "vi")

        assert result == "dịch bởi key-b"
        assert mock_mark.call_args_list == [
            call(dummy_session, 1, success=False),
            call(dummy_session, 2, success=True),
        ]

    @pytest.mark.anyio
    async def test_falls_back_to_google_when_openai_pool_exhausted(self, dummy_session) -> None:
        """Chỉ 1 key OpenAI, hết quota → không còn key nào khác trong pool → fallback
        Google free như hành vi gốc trước Phase 8."""
        picks = iter([(1, "key-a")])

        with (
            patch(
                "app.services.translate_service.api_key_service.pick_decrypted_key",
                side_effect=lambda *_a, **_kw: next(picks, None),
            ),
            patch("app.services.translate_service.api_key_service.mark_key_result"),
            patch(
                "app.services.translate_service.openai_translate.translate",
                new=AsyncMock(side_effect=lambda *_a, **_kw: (_ for _ in ()).throw(_http_status_error(429))),
            ),
            patch(
                "app.services.translate_service.google_translate.translate",
                new=AsyncMock(return_value="dịch bởi google"),
            ) as mock_google,
        ):
            result = await translate_service.translate_text(dummy_session, 1, "hi", "en", "vi")

        assert result == "dịch bởi google"
        mock_google.assert_awaited_once()

    @pytest.mark.anyio
    async def test_raises_all_providers_exhausted_when_openai_and_google_both_fail(
        self, dummy_session
    ) -> None:
        picks = iter([(1, "key-a")])

        with (
            patch(
                "app.services.translate_service.api_key_service.pick_decrypted_key",
                side_effect=lambda *_a, **_kw: next(picks, None),
            ),
            patch("app.services.translate_service.api_key_service.mark_key_result"),
            patch(
                "app.services.translate_service.openai_translate.translate",
                new=AsyncMock(side_effect=lambda *_a, **_kw: (_ for _ in ()).throw(_http_status_error(429))),
            ),
            patch(
                "app.services.translate_service.google_translate.translate",
                new=AsyncMock(side_effect=lambda *_a, **_kw: (_ for _ in ()).throw(_http_status_error(429))),
            ),
        ):
            with pytest.raises(AllProvidersExhaustedError):
                await translate_service.translate_text(dummy_session, 1, "hi", "en", "vi")
