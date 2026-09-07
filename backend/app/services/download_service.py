from pathlib import Path

import httpx

from app.adapters import ffmpeg
from app.adapters.bilibili.client import BilibiliClient
from app.services import progress_service

_STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "storage"
_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.bilibili.com",
}


def get_storage_root() -> Path:
    """Thư mục gốc chứa toàn bộ file tải về — hiển thị cho người dùng biết file ở đâu."""
    return _STORAGE_ROOT


async def _stream_to_file(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    *,
    video_id: int | None = None,
    stage: str | None = None,
) -> None:
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        if video_id is not None and stage is not None:
            raw_length = response.headers.get("content-length")
            progress_service.set_stage(
                video_id, stage, int(raw_length) if raw_length else None, kind="download"
            )
        with open(dest, "wb") as f:
            async for chunk in response.aiter_bytes():
                f.write(chunk)
                if video_id is not None:
                    progress_service.advance(video_id, len(chunk), kind="download")


async def download_bilibili_video(job_id: int, video_id: int, bvid: str, cid: int) -> Path:
    """Tải video-only + audio-only stream (DASH) rồi ghép bằng ffmpeg.

    Raises FfmpegNotFoundError sớm (trước khi tải) nếu chưa cài ffmpeg, tránh tải
    xong hàng chục MB rồi mới báo lỗi ở bước merge.
    """
    ffmpeg.ensure_ffmpeg_available()

    video_dir = _STORAGE_ROOT / str(job_id) / str(video_id)
    video_dir.mkdir(parents=True, exist_ok=True)
    video_tmp = video_dir / "video.m4s"
    audio_tmp = video_dir / "audio.m4s"
    output_path = video_dir / "original.mp4"

    async with BilibiliClient() as bilibili:
        dash = await bilibili.get_play_streams(bvid, cid)
    video_url = dash["video"][0]["baseUrl"]
    audio_url = dash["audio"][0]["baseUrl"]

    async with httpx.AsyncClient(headers=_DOWNLOAD_HEADERS, timeout=60) as http:
        await _stream_to_file(http, video_url, video_tmp, video_id=video_id, stage="video")
        await _stream_to_file(http, audio_url, audio_tmp, video_id=video_id, stage="audio")

    progress_service.set_stage(video_id, "merging", kind="download")
    ffmpeg.merge_video_audio(video_tmp, audio_tmp, output_path)
    video_tmp.unlink(missing_ok=True)
    audio_tmp.unlink(missing_ok=True)
    return output_path
