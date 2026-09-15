"""Test `DouyinClient.download_no_watermark` — phần giao cho yt-dlp (Phase 3,
nghiên cứu 2026-09-15, xem docs/phases/phase-3-multiprovider-douyin.md).

Mock ở mức `yt_dlp.YoutubeDL`: không gọi mạng thật (cần cookie thật, không chạy
được trong CI). Test này chỉ kiểm tra phần mình viết — options truyền đúng, lỗi
"fresh cookies" của yt-dlp được ánh xạ sang `DouyinCookieExpiredError` để UI xử
lý nhất quán với lỗi 401/403 của `get_video_detail`.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
import yt_dlp

from app.adapters.douyin.client import DouyinClient, DouyinCookieExpiredError


def _client() -> DouyinClient:
    return DouyinClient(cookie="sessionid=abc")


class TestDownloadNoWatermark:
    def test_passes_url_cookie_and_output_path_to_ytdlp(self, tmp_path: Path) -> None:
        dest = tmp_path / "original.mp4"
        with patch("app.adapters.douyin.client.yt_dlp.YoutubeDL") as ydl_cls:
            ydl = ydl_cls.return_value.__enter__.return_value
            ydl.extract_info.return_value = {"id": "7123", "ext": "mp4"}

            result = _client().download_no_watermark("7123", dest, cookie="sessionid=abc")

        opts = ydl_cls.call_args[0][0]
        assert opts["outtmpl"] == str(dest)
        assert opts["http_headers"] == {"Cookie": "sessionid=abc"}
        ydl.extract_info.assert_called_once_with(
            "https://www.douyin.com/video/7123", download=True
        )
        assert result == {"id": "7123", "ext": "mp4"}

    def test_no_cookie_sends_empty_headers_not_literal_cookie_string(self, tmp_path: Path) -> None:
        """Cookie rỗng phải thành `{}`, không phải `{"Cookie": ""}` — header rỗng
        vẫn có thể khiến Douyin trả lỗi khó hiểu khác với "chưa gửi cookie"."""
        with patch("app.adapters.douyin.client.yt_dlp.YoutubeDL") as ydl_cls:
            ydl = ydl_cls.return_value.__enter__.return_value
            ydl.extract_info.return_value = {}

            _client().download_no_watermark("7123", tmp_path / "v.mp4", cookie="")

        assert ydl_cls.call_args[0][0]["http_headers"] == {}

    def test_fresh_cookies_error_maps_to_cookie_expired(self, tmp_path: Path) -> None:
        with patch("app.adapters.douyin.client.yt_dlp.YoutubeDL") as ydl_cls:
            ydl = ydl_cls.return_value.__enter__.return_value
            ydl.extract_info.side_effect = yt_dlp.utils.DownloadError(
                "[Douyin] 7123: Fresh cookies (not necessarily logged in) are needed"
            )

            with pytest.raises(DouyinCookieExpiredError):
                _client().download_no_watermark("7123", tmp_path / "v.mp4", cookie="sessionid=cu")

    def test_unrelated_download_error_propagates_unchanged(self, tmp_path: Path) -> None:
        """Lỗi khác (mạng, video bị xoá...) không nên bị gộp nhầm thành "cookie
        hết hạn" — sẽ khiến UI hướng dẫn sai việc cần làm."""
        with patch("app.adapters.douyin.client.yt_dlp.YoutubeDL") as ydl_cls:
            ydl = ydl_cls.return_value.__enter__.return_value
            ydl.extract_info.side_effect = yt_dlp.utils.DownloadError("Video unavailable")

            with pytest.raises(yt_dlp.utils.DownloadError):
                _client().download_no_watermark("7123", tmp_path / "v.mp4", cookie="sessionid=ok")
