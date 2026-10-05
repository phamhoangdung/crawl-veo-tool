import asyncio
import logging
from pathlib import Path

import httpx

from app.adapters import ffmpeg
from app.adapters.bilibili.client import BilibiliClient
from app.core.config import get_settings, storage_dir
from app.core.db import SessionLocal
from app.models.video import Video, VideoStatus
from app.services import progress_service, settings_service

logger = logging.getLogger(__name__)

_STORAGE_ROOT = storage_dir()
_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.bilibili.com",
}

_RANGE_RETRY_ATTEMPTS = 6
_RANGE_RETRY_BASE_DELAY_SECONDS = 0.5

# Phase 20: limits the NUMBER OF VIDEOS downloading in parallel (unlike Phase 21 — which limits
# connections PER video). A module-level semaphore (not per request) because
# downloads run in separate background tasks, which do not share the context of the
# request that created them.
#
# Created lazily (not at import time): before Python 3.10 `asyncio.Semaphore()` binds itself to the event
# loop running at construction — creating it at module top level (before
# uvicorn has an event loop) was the classic source of "attached to a different loop"
# errors. Creating it in the first async function that uses it is always the right loop.
_download_slots: asyncio.Semaphore | None = None

# Phase 21: limits the TOTAL NUMBER OF OPEN HTTP Range CONNECTIONS FOR THE WHOLE APP, not
# per video. Fixed at an absolute ceiling (does not change with user
# settings) — the "thread count" (1-8) the user picks only decides HOW MANY PARTS
# 1 video is SPLIT INTO, while this semaphore is the final physical barrier:
# 1 video asking for 8 parts uses all 8 slots; 3 videos each asking for 8 parts share
# those 8 slots (not 24) — no sharing formula needed, the semaphore takes care of it.
# See "Ràng buộc với phase-20" in docs/phases/phase-21-parallel-download.md.
_connection_slots: asyncio.Semaphore | None = None


def _get_download_slots() -> asyncio.Semaphore:
    global _download_slots
    if _download_slots is None:
        _download_slots = asyncio.Semaphore(get_settings().download_max_videos)
    return _download_slots


def _get_connection_slots() -> asyncio.Semaphore:
    global _connection_slots
    if _connection_slots is None:
        _connection_slots = asyncio.Semaphore(settings_service.DOWNLOAD_CONNECTIONS_MAX)
    return _connection_slots


def get_storage_root() -> Path:
    """Root directory holding every downloaded file — shown to the user so they know where files are."""
    return _STORAGE_ROOT


class _RangeNotHonoredError(Exception):
    """The CDN returned 200 (the whole file) instead of 206 despite the Range header — not a
    network error, should not be retried, the caller must fall back to a single-stream download right away."""


async def _probe(client: httpx.AsyncClient, url: str) -> tuple[int | None, bool]:
    """One HEAD: returns `(content_length, range_supported)`. `content_length=None`
    when the server returns no header or the request fails — the caller must treat it as
    "unknown", not "0 bytes"."""
    try:
        response = await client.head(url)
    except httpx.HTTPError:
        return None, False
    if response.status_code != 200:
        return None, False
    supports_range = response.headers.get("accept-ranges", "").strip().lower() == "bytes"
    raw_length = response.headers.get("content-length")
    if not raw_length:
        return None, supports_range
    try:
        return int(raw_length), supports_range
    except ValueError:
        return None, supports_range


def _split_ranges(size: int, parts: int) -> list[tuple[int, int]]:
    """Split `[0, size)` into `parts` nearly equal ranges — the last range takes the remainder
    (size is not necessarily divisible by parts)."""
    chunk = size // parts
    ranges: list[tuple[int, int]] = []
    for i in range(parts):
        start = i * chunk
        end = (start + chunk - 1) if i < parts - 1 else size - 1
        ranges.append((start, end))
    return ranges


async def _download_whole(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    *,
    video_id: int | None,
    slots: asyncio.Semaphore,
) -> None:
    """Download the whole file with 1 connection — the old path from before Phase 21, kept as
    the fallback when the CDN does not support Range or the file is too small to split.
    Still takes 1 slot from `slots` (the app-wide connection barrier) for consistency."""
    for attempt in range(_RANGE_RETRY_ATTEMPTS):
        written = 0
        try:
            async with slots:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with open(dest, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
                            written += len(chunk)
                            if video_id is not None:
                                progress_service.advance(video_id, len(chunk), kind="download")
            return
        except (httpx.TransportError, httpx.HTTPStatusError):
            # Connection dropped midway: download again from the start, giving back the bytes already counted.
            if video_id is not None and written:
                progress_service.advance(video_id, -written, kind="download")
            if attempt < _RANGE_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_RANGE_RETRY_BASE_DELAY_SECONDS * (attempt + 1))
                continue
            raise


async def _download_range_part(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    start: int,
    end: int,
    *,
    video_id: int | None,
    slots: asyncio.Semaphore,
) -> None:
    """Download exactly 1 byte range, writing at the right offset of `dest` (pre-allocated
    to full size beforehand — each worker only touches its own part, no
    lock needed). On error retry EXACTLY this range at most `_RANGE_RETRY_ATTEMPTS`
    times, not the whole file again."""
    # A cut-off midway ("peer closed connection without sending complete
    # message body") is a common CDN network error: retry CONTINUING from the byte
    # already received (not redownloading the whole range, no progress rollback).
    part_bytes = 0
    for attempt in range(_RANGE_RETRY_ATTEMPTS):
        try:
            async with slots:
                async with client.stream(
                    "GET", url, headers={"Range": f"bytes={start + part_bytes}-{end}"}
                ) as response:
                    if response.status_code != 206:
                        # Some CDNs ignore the Range header and return the whole file (200) —
                        # not a network error, retrying is useless, it must be reported right away so
                        # the caller falls back to a single-stream download instead of overwriting at random.
                        raise _RangeNotHonoredError(
                            f"Server trả status {response.status_code} thay vì 206 cho Range request"
                        )
                    with open(dest, "r+b") as f:
                        f.seek(start + part_bytes)
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
                            part_bytes += len(chunk)
                            if video_id is not None:
                                progress_service.advance(video_id, len(chunk), kind="download")
            if start + part_bytes <= end:
                raise httpx.ReadError("Kết nối đóng sớm, thiếu dữ liệu")
            return
        except _RangeNotHonoredError:
            raise
        except Exception:
            if attempt < _RANGE_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_RANGE_RETRY_BASE_DELAY_SECONDS * (attempt + 1))
                continue
            raise


async def _download_stream(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    *,
    connections: int,
    slots: asyncio.Semaphore,
    video_id: int | None,
    known_size: int | None,
    supports_range: bool,
) -> None:
    """Download 1 stream (video-only or audio-only) — split into `connections` parts
    via HTTP Range if eligible, otherwise fall back to 1 connection.

    Conditions for splitting (Phase 21, measured 2026-09-22): `connections > 1`,
    the server confirms Range support, and the size is known to be larger than
    `download_part_min_bytes` (splitting a small file only costs an extra TLS handshake and
    gains nothing — see docs/phases/phase-21-parallel-download.md).
    """
    part_min_bytes = get_settings().download_part_min_bytes
    if (
        connections <= 1
        or not supports_range
        or known_size is None
        or known_size < part_min_bytes
    ):
        await _download_whole(client, url, dest, video_id=video_id, slots=slots)
        return

    # Pre-allocate the exact final size right from the start — each worker `seek()`s
    # to its own offset then writes, no need for N part files and then joining them (which would cost twice
    # the disk space + an extra read/write pass over the whole file).
    with open(dest, "wb") as f:
        f.truncate(known_size)

    ranges = _split_ranges(known_size, connections)
    try:
        await asyncio.gather(
            *(
                _download_range_part(client, url, dest, start, end, video_id=video_id, slots=slots)
                for start, end in ranges
            )
        )
    except _RangeNotHonoredError:
        # The CDN says it supports Range (accept-ranges: bytes on HEAD) but the real GET
        # does not honor it — rare but seen on "lazy" CDNs. Delete the
        # partially downloaded data (it may mix data from several different offsets and is not
        # reusable) then download again with 1 connection to be safe.
        #
        # Known limitation: parts that finished BEFORE the failing part occurred keep
        # the bytes already added to progress (it cannot be rolled back
        # exactly because `asyncio.gather` cancels the in-flight parts, not the finished
        # ones) — `_download_whole` adding from the start may make the % exceed 100%
        # temporarily. `TaskProgress.percent` already clamps to at most 100%
        # (`min(100.0, ...)`) so no absurd number is shown, it may only reach
        # 100% earlier than reality in exactly this rare case — acceptable,
        # not worth adding a complex byte-tracking mechanism for one rare edge case.
        logger.warning(
            "CDN không tôn trọng Range request dù báo có hỗ trợ, rơi về 1 kết nối: %s", url
        )
        await _download_whole(client, url, dest, video_id=video_id, slots=slots)


async def download_bilibili_video(
    job_id: int, video_id: int, bvid: str, cid: int, *, connections: int = 1
) -> Path:
    """Download the video-only + audio-only streams (DASH) then merge with ffmpeg.

    Raises FfmpegNotFoundError early (before downloading) if ffmpeg is not installed, to avoid downloading
    tens of MB and only reporting the error at the merge step.

    Queues through the semaphore once `download_max_videos` downloads are already running in
    parallel (Phase 20 — bulk selection on the Discovery screen) — reports stage "queued"
    while waiting so the UI does not show a confusing frozen %.

    `connections` (Phase 21, default 1 = old behavior): number of HTTP Range parts
    for EACH stream (video/audio) — the real ceiling for the whole app is
    `settings_service.DOWNLOAD_CONNECTIONS_MAX`, see `_get_connection_slots()`.
    """
    ffmpeg.ensure_ffmpeg_available()

    progress_service.set_stage(video_id, "queued", kind="download")
    async with _get_download_slots():
        return await _download_bilibili_video_slot(
            job_id, video_id, bvid, cid, connections=connections
        )


async def _download_bilibili_video_slot(
    job_id: int, video_id: int, bvid: str, cid: int, *, connections: int
) -> Path:
    """The actual download body — runs after holding 1 video-count semaphore slot."""
    video_dir = _STORAGE_ROOT / str(job_id) / str(video_id)
    video_dir.mkdir(parents=True, exist_ok=True)
    video_tmp = video_dir / "video.m4s"
    audio_tmp = video_dir / "audio.m4s"
    output_path = video_dir / "original.mp4"

    async with BilibiliClient() as bilibili:
        dash = await bilibili.get_play_streams(bvid, cid)
    video_url = dash["video"][0]["baseUrl"]
    audio_url = dash["audio"][0]["baseUrl"]

    slots = _get_connection_slots()

    async with httpx.AsyncClient(headers=_DOWNLOAD_HEADERS, timeout=60) as http:
        # Probe the size of BOTH first to report a single "downloading" stage with the real total
        # size — video+audio now download IN PARALLEL (Phase 21), so 2
        # sequential stages "video" then "audio" as before would make the % jump around.
        # If the size cannot be known (odd proxy, timeout) total=None —
        # progress still works, only the % is not shown (see TaskProgress.percent).
        (video_size, video_range_ok), (audio_size, audio_range_ok) = await asyncio.gather(
            _probe(http, video_url), _probe(http, audio_url)
        )
        total = (
            video_size + audio_size
            if video_size is not None and audio_size is not None
            else None
        )
        progress_service.set_stage(video_id, "downloading", total, kind="download")

        await asyncio.gather(
            _download_stream(
                http, video_url, video_tmp,
                connections=connections, slots=slots, video_id=video_id,
                known_size=video_size, supports_range=video_range_ok,
            ),
            _download_stream(
                http, audio_url, audio_tmp,
                connections=connections, slots=slots, video_id=video_id,
                known_size=audio_size, supports_range=audio_range_ok,
            ),
        )

    progress_service.set_stage(video_id, "merging", kind="download")
    # to_thread: subprocess.run is blocking — calling it directly here would freeze the whole event
    # loop (this function runs directly on the main loop when queued as a background
    # task, see docs/performance-optimization/plan.md, section P0).
    await asyncio.to_thread(ffmpeg.merge_video_audio, video_tmp, audio_tmp, output_path)
    video_tmp.unlink(missing_ok=True)
    audio_tmp.unlink(missing_ok=True)
    return output_path


async def run_download_task(video_id: int) -> None:
    """Background run: download 1 video by id, opening its own session (the session of the request
    that created this task was already closed when this function runs).

    Shared by both entry points: the single "Download video" button (`POST
    /api/videos/{id}/download`, My videos page) and the bulk download from the Discovery
    screen (`POST /api/jobs/from-selection`, Phase 20) — previously this logic
    lived separately in `api/pipeline.py`, moved here so it need not be copied
    verbatim for the second entry point.
    """
    with SessionLocal() as db:
        video = db.get(Video, video_id)
        if video is None:
            progress_service.finish(video_id, error="Video không còn tồn tại")
            return
        try:
            # Read AT THE START of this download (not cached at import time) — changing
            # settings must take effect right away for the next video downloaded, without
            # restarting the backend (Phase 21, see Definition of Done).
            connections = settings_service.get_download_connections(db, video.user_id)
            async with BilibiliClient() as client:
                cid = await client.get_video_cid(video.platform_video_id)
            output_path = await download_bilibili_video(
                job_id=video.job_id,
                video_id=video.id,
                bvid=video.platform_video_id,
                cid=cid,
                connections=connections,
            )
            video.local_path = str(output_path)
            video.status = VideoStatus.DOWNLOADED
            video.error_message = None
            db.commit()
            progress_service.finish(video.id)
        except Exception as exc:
            logger.exception("Tải video %s thất bại", video_id)
            video.status = VideoStatus.FAILED_DOWNLOAD
            video.error_message = str(exc)
            db.commit()
            progress_service.finish(video.id, error=str(exc))
