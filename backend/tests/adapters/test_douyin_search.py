"""Test `app.adapters.douyin.search` (Phase 3, research 2026-09-15).

`_sign`/`_gen_fake_ms_token` were verified with a real request when the code was written (see the
module docstring) — the tests here only lock down the behavior (no network calls, no real
cookie needed): build a correctly shaped signed URL, and classify the response by `status_code`
exactly as Douyin really returns it (2483 = login required).
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
        """The fake msToken must differ every time — duplicates are a sign that Douyin's anti-bot
        could recognize requests coming from the same script."""
        assert _gen_fake_ms_token() != _gen_fake_ms_token()


class TestSign:
    def test_appends_a_bogus_param(self) -> None:
        url = _sign({"keyword": "test", "offset": 0})
        assert "a_bogus=" in url
        assert url.startswith("https://www.douyin.com/aweme/v1/web/general/search/single/?")


class TestProbeSearch:
    @pytest.mark.asyncio
    async def test_login_required_maps_to_specific_error(self) -> None:
        """status_code 2483 is the real code Douyin returns when the login cookie is missing —
        verified with a real request (2026-09-15), not guessed."""
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
        """Errors other than "login required" must not be wrongly lumped in — the UI needs to know this is
        a new situation never seen before, not just keep telling the user to log in again."""
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
        """Do not send an empty Cookie header — avoids Douyin treating it differently from 'sending
        nothing' (a similar situation was seen with DOUYIN_COOKIE in douyin_service)."""
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
