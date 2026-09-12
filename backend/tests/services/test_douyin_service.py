"""Test phần Douyin KIỂM CHỨNG ĐƯỢC: phân loại trạng thái cấu hình và lỗi.

Không test phần bóc tách link không watermark — phần đó cố ý chưa viết, vì hình
dạng JSON của Douyin chỉ biết được khi gọi thật bằng cookie hợp lệ (xem docstring
của `app/services/douyin_service.py`).
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.douyin.client import DouyinCookieExpiredError
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
