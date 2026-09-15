"""Test `app.adapters.douyin.search` (Phase 3, nghiên cứu 2026-09-15).

`_sign`/`_gen_fake_ms_token` đã verify bằng request thật lúc viết code (xem
docstring module) — test ở đây chỉ khoá lại hành vi (không gọi mạng, không cần
cookie thật): tạo URL đã ký đúng dạng, và phân loại response theo `status_code`
đúng như Douyin trả về thật (2483 = cần đăng nhập).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.douyin.search import (
    DouyinLoginRequiredError,
    DouyinSearchError,
    _gen_fake_ms_token,
    _sign,
    probe_search,
)


class TestGenFakeMsToken:
    def test_returns_url_safe_string_without_padding(self) -> None:
        token = _gen_fake_ms_token()
        assert "=" not in token
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_different_each_call(self) -> None:
        """msToken giả phải khác nhau mỗi lần — trùng lặp là dấu hiệu chống bot
        của Douyin có thể nhận diện request đến từ cùng 1 script."""
        assert _gen_fake_ms_token() != _gen_fake_ms_token()


class TestSign:
    def test_appends_a_bogus_param(self) -> None:
        url = _sign({"keyword": "test", "offset": 0})
        assert "a_bogus=" in url
        assert url.startswith("https://www.douyin.com/aweme/v1/web/general/search/single/?")


class TestProbeSearch:
    @pytest.mark.asyncio
    async def test_login_required_maps_to_specific_error(self) -> None:
        """status_code 2483 là mã thật Douyin trả khi thiếu cookie đăng nhập —
        verify bằng request thật (2026-09-15), không phải đoán."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status_code": 2483,
            "status_msg": "请先登录，再继续搜索吧",
        }
        with patch("app.adapters.douyin.search.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=mock_response)

            with pytest.raises(DouyinLoginRequiredError):
                await probe_search("test", cookie="")

    @pytest.mark.asyncio
    async def test_success_returns_raw_json(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status_code": 0, "data": []}
        with patch("app.adapters.douyin.search.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=mock_response)

            result = await probe_search("test", cookie="sessionid=abc")

        assert result == {"status_code": 0, "data": []}

    @pytest.mark.asyncio
    async def test_unknown_nonzero_status_raises_generic_search_error(self) -> None:
        """Lỗi khác "cần đăng nhập" không nên bị gộp nhầm — UI cần biết đây là
        tình huống mới chưa từng gặp, không phải cứ bảo đi đăng nhập lại."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status_code": 8, "status_msg": "rate limited"}
        with patch("app.adapters.douyin.search.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=mock_response)

            with pytest.raises(DouyinSearchError):
                await probe_search("test", cookie="sessionid=abc")

    @pytest.mark.asyncio
    async def test_sends_cookie_header_when_provided(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status_code": 0}
        with patch("app.adapters.douyin.search.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=mock_response)

            await probe_search("test", cookie="sessionid=real-login-cookie")

        _, kwargs = client.get.call_args
        assert kwargs["headers"]["Cookie"] == "sessionid=real-login-cookie"

    @pytest.mark.asyncio
    async def test_no_cookie_header_when_not_provided(self) -> None:
        """Không gửi header Cookie rỗng — tránh Douyin xử lý khác với 'không gửi
        gì' (đã thấy tình huống tương tự với DOUYIN_COOKIE ở douyin_service)."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status_code": 2483, "status_msg": "x"}
        with patch("app.adapters.douyin.search.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=mock_response)

            with pytest.raises(DouyinLoginRequiredError):
                await probe_search("test", cookie="")

        _, kwargs = client.get.call_args
        assert "Cookie" not in kwargs["headers"]
