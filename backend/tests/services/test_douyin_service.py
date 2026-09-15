"""Test phần Douyin KIỂM CHỨNG ĐƯỢC: phân loại trạng thái cấu hình và lỗi.

Không test phần bóc tách link không watermark — phần đó cố ý chưa viết, vì hình
dạng JSON của Douyin chỉ biết được khi gọi thật bằng cookie hợp lệ (xem docstring
của `app/services/douyin_service.py`).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.douyin.client import DouyinCookieExpiredError
from app.adapters.douyin.search import DouyinLoginRequiredError
from app.core.config import Settings
from app.services import douyin_service


def _settings(cookie: str) -> Settings:
    return Settings(master_key="x" * 32, douyin_cookie=cookie)


class TestIsConfigured:
    def test_empty_cookie_is_not_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings(""))
        assert douyin_service.is_configured() is False

    def test_whitespace_only_cookie_is_not_configured(self, monkeypatch) -> None:
        """Dán nhầm khoảng trắng vào .env vẫn phải coi là chưa cấu hình, không thì
        sẽ gửi header Cookie rỗng rồi nhận lỗi khó hiểu từ Douyin."""
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings("   \n "))
        assert douyin_service.is_configured() is False

    def test_real_cookie_is_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings("sessionid=abc"))
        assert douyin_service.is_configured() is True


class TestProbe:
    @pytest.mark.asyncio
    async def test_without_cookie_raises_with_actionable_hint(self, monkeypatch) -> None:
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings(""))
        with pytest.raises(douyin_service.DouyinNotConfiguredError) as exc:
            await douyin_service.probe_share_url("https://v.douyin.com/abc/")
        # Thông báo phải nói rõ làm gì tiếp, không chỉ "thiếu cookie".
        assert "DOUYIN_COOKIE" in str(exc.value)

    @pytest.mark.asyncio
    async def test_expired_cookie_propagates_distinctly(self, monkeypatch) -> None:
        """Cookie hết hạn KHÁC chưa có cookie: một bên phải đi lấy lại, bên kia
        là lần đầu cấu hình. Gộp chung thì UI không hướng dẫn đúng được."""
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings("sessionid=cu"))
        with patch.object(douyin_service, "DouyinClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.resolve_share_url = AsyncMock(return_value="123")
            client.get_video_detail = AsyncMock(
                side_effect=DouyinCookieExpiredError("HTTP 403")
            )
            with pytest.raises(DouyinCookieExpiredError):
                await douyin_service.probe_share_url("https://v.douyin.com/abc/")

    @pytest.mark.asyncio
    async def test_reports_json_shape_for_writing_the_parser_later(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings("sessionid=ok"))
        with patch.object(douyin_service, "DouyinClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.resolve_share_url = AsyncMock(return_value="7123")
            client.get_video_detail = AsyncMock(
                return_value={
                    "status_code": 0,
                    "aweme_detail": {"aweme_id": "7123", "video": {}, "desc": "x"},
                }
            )
            result = await douyin_service.probe_share_url("https://v.douyin.com/abc/")

        assert result["aweme_id"] == "7123"
        assert result["top_level_keys"] == ["aweme_detail", "status_code"]
        assert result["detail_keys"] == ["aweme_id", "desc", "video"]

    @pytest.mark.asyncio
    async def test_handles_alternative_aweme_list_shape(self, monkeypatch) -> None:
        """Douyin từng trả metadata ở `aweme_list[0]` thay vì `aweme_detail` —
        đoán một dạng rồi trả về rỗng sẽ khiến probe vô dụng đúng lúc cần nó nhất."""
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings("sessionid=ok"))
        with patch.object(douyin_service, "DouyinClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.resolve_share_url = AsyncMock(return_value="7123")
            client.get_video_detail = AsyncMock(
                return_value={"aweme_list": [{"aweme_id": "7123", "music": {}}]}
            )
            result = await douyin_service.probe_share_url("https://v.douyin.com/abc/")

        assert result["detail_keys"] == ["aweme_id", "music"]

    @pytest.mark.asyncio
    async def test_unknown_shape_gives_empty_detail_not_crash(self, monkeypatch) -> None:
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings("sessionid=ok"))
        with patch.object(douyin_service, "DouyinClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.resolve_share_url = AsyncMock(return_value="7123")
            client.get_video_detail = AsyncMock(return_value={"la_gi_the_nay": 1})
            result = await douyin_service.probe_share_url("https://v.douyin.com/abc/")

        assert result["detail_keys"] == []
        assert result["top_level_keys"] == ["la_gi_the_nay"]


class TestDownloadVideo:
    """`download_video` giao phần bóc tách/tải cho yt-dlp — test ở đây chỉ kiểm
    tra wiring (resolve trước, cookie truyền đúng), không test yt-dlp thật (xem
    tests/adapters/test_douyin_client.py cho phần đó)."""

    @pytest.mark.asyncio
    async def test_without_cookie_raises_with_actionable_hint(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings(""))
        with pytest.raises(douyin_service.DouyinNotConfiguredError):
            await douyin_service.download_video("https://v.douyin.com/abc/", tmp_path / "v.mp4")

    @pytest.mark.asyncio
    async def test_resolves_share_url_then_downloads_with_configured_cookie(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings("sessionid=ok"))
        dest = tmp_path / "original.mp4"
        with patch.object(douyin_service, "DouyinClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.resolve_share_url = AsyncMock(return_value="7123")
            client.download_no_watermark = MagicMock(return_value={"id": "7123"})

            result = await douyin_service.download_video("https://v.douyin.com/abc/", dest)

        client.resolve_share_url.assert_awaited_once_with("https://v.douyin.com/abc/")
        client.download_no_watermark.assert_called_once_with("7123", dest, cookie="sessionid=ok")
        assert result == {"id": "7123"}

    @pytest.mark.asyncio
    async def test_cookie_expired_during_resolve_propagates(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings("sessionid=cu"))
        with patch.object(douyin_service, "DouyinClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.resolve_share_url = AsyncMock(side_effect=DouyinCookieExpiredError("HTTP 403"))

            with pytest.raises(DouyinCookieExpiredError):
                await douyin_service.download_video("https://v.douyin.com/abc/", tmp_path / "v.mp4")

    @pytest.mark.asyncio
    async def test_ytdlp_fresh_cookies_error_propagates(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings("sessionid=cu"))
        with patch.object(douyin_service, "DouyinClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.resolve_share_url = AsyncMock(return_value="7123")
            client.download_no_watermark = MagicMock(
                side_effect=DouyinCookieExpiredError("Fresh cookies needed")
            )

            with pytest.raises(DouyinCookieExpiredError):
                await douyin_service.download_video("https://v.douyin.com/abc/", tmp_path / "v.mp4")


class TestSearchVideos:
    """`search_videos` cần cookie ĐĂNG NHẬP thật, khác `probe_share_url`/
    `download_video` — xem docstring `douyin_service`. Test wiring, không gọi
    mạng thật (xem tests/adapters/test_douyin_search.py cho phần đó)."""

    @pytest.mark.asyncio
    async def test_without_any_cookie_raises_not_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings(""))
        with pytest.raises(douyin_service.DouyinNotConfiguredError):
            await douyin_service.search_videos("review dien thoai")

    @pytest.mark.asyncio
    async def test_anonymous_cookie_configured_still_raises_login_required(
        self, monkeypatch
    ) -> None:
        """`is_configured()` chỉ kiểm tra cookie có giá trị, không phân biệt được
        ẩn danh hay đăng nhập — lỗi phải lộ ra ở tầng gọi API thật, không phải bị
        `is_configured()` nuốt mất."""
        monkeypatch.setattr(douyin_service, "get_settings", lambda: _settings("s_v_web_id=anon"))
        with patch.object(douyin_service, "probe_search", new_callable=AsyncMock) as mock_probe:
            mock_probe.side_effect = DouyinLoginRequiredError("请先登录，再继续搜索吧")

            with pytest.raises(DouyinLoginRequiredError):
                await douyin_service.search_videos("review dien thoai")

    @pytest.mark.asyncio
    async def test_success_passes_through_raw_result(self, monkeypatch) -> None:
        monkeypatch.setattr(
            douyin_service, "get_settings", lambda: _settings("sessionid=logged-in")
        )
        with patch.object(douyin_service, "probe_search", new_callable=AsyncMock) as mock_probe:
            mock_probe.return_value = {"status_code": 0, "data": [{"aweme_id": "1"}]}

            result = await douyin_service.search_videos("review", offset=15, count=10)

        mock_probe.assert_awaited_once_with("review", "sessionid=logged-in", offset=15, count=10)
        assert result == {"status_code": 0, "data": [{"aweme_id": "1"}]}
