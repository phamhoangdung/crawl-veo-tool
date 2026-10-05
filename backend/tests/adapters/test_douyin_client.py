"""Test `DouyinClient.download_no_watermark` — the part delegated to yt-dlp (Phase 3,
research 2026-09-15, see docs/phases/phase-3-multiprovider-douyin.md).

Mocked at the `yt_dlp.YoutubeDL` level: no real network calls (a real cookie would be needed, which cannot run
in CI). This test only checks the part we wrote — options passed correctly, yt-dlp's
"fresh cookies" error mapped to `DouyinCookieExpiredError` so the UI handles it
consistently with the 401/403 error of `get_video_detail`.
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
        """An empty cookie must become `{}`, not `{"Cookie": ""}` — an empty header
        can still make Douyin return a confusing error different from "no cookie sent"."""
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
        """Other errors (network, deleted video...) should not be wrongly lumped into "cookie
        expired" — that would make the UI give the wrong instructions."""
        with patch("app.adapters.douyin.client.yt_dlp.YoutubeDL") as ydl_cls:
            ydl = ydl_cls.return_value.__enter__.return_value
            ydl.extract_info.side_effect = yt_dlp.utils.DownloadError("Video unavailable")

            with pytest.raises(yt_dlp.utils.DownloadError):
                _client().download_no_watermark("7123", tmp_path / "v.mp4", cookie="sessionid=ok")
