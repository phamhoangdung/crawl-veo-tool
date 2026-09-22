import asyncio
import logging
from pathlib import Path

import httpx

from app.adapters import ffmpeg
from app.adapters.bilibili.client import BilibiliClient
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.video import Video, VideoStatus
from app.services import progress_service, settings_service

logger = logging.getLogger(__name__)

_STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "storage"
_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.bilibili.com",
}

_RANGE_RETRY_ATTEMPTS = 3
_RANGE_RETRY_BASE_DELAY_SECONDS = 0.5

# Phase 20: giới hạn SỐ VIDEO tải song song (khác Phase 21 — giới hạn số kết
# nối MỖI video). Semaphore module-level (không phải theo request) vì các
# lượt tải chạy trong background task riêng biệt, không chia sẻ context của
# request đã tạo ra chúng.
#
# Tạo lười (không tạo ở import-time): `asyncio.Semaphore()` tự bind vào event
# loop đang chạy lúc khởi tạo ở Python < 3.10 — tạo ở top-level module (trước
# khi uvicorn có event loop) từng là nguồn lỗi "attached to a different loop"
# kinh điển. Tạo trong hàm async đầu tiên dùng tới thì luôn đúng loop.
_download_slots: asyncio.Semaphore | None = None

# Phase 21: giới hạn TỔNG SỐ KẾT NỐI HTTP Range đang mở CHO CẢ APP, không
# phải cho từng video. Cố định ở mức trần tuyệt đối (không đổi theo cài đặt
# người dùng) — người dùng tự chọn "số luồng" (1-8) chỉ quyết định 1 video
# CHIA THÀNH BAO NHIÊU PHẦN, còn semaphore này là hàng rào vật lý cuối cùng:
# 1 video xin 8 phần thì dùng cả 8 slot; 3 video cùng xin 8 phần thì tự chia
# nhau 8 slot đó (không phải 24) — không cần công thức chia, semaphore tự lo.
# Xem "Ràng buộc với phase-20" trong docs/phases/phase-21-parallel-download.md.
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
    """Thư mục gốc chứa toàn bộ file tải về — hiển thị cho người dùng biết file ở đâu."""
    return _STORAGE_ROOT


class _RangeNotHonoredError(Exception):
    """CDN trả 200 (cả file) thay vì 206 dù có header Range — không phải lỗi
    mạng, không nên retry, người gọi phải rơi về tải 1 luồng ngay."""


async def _probe(client: httpx.AsyncClient, url: str) -> tuple[int | None, bool]:
    """HEAD 1 lần: trả `(content_length, hỗ_trợ_range)`. `content_length=None`
    khi server không trả header hoặc request lỗi — người gọi phải coi như
    "không biết", không phải "0 byte"."""
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
    """Chia `[0, size)` thành `parts` khoảng gần đều — khoảng cuối nhận phần dư
    (size không chắc chia hết cho parts)."""
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
    """Tải cả file bằng 1 kết nối — đường cũ trước Phase 21, vẫn giữ nguyên
    làm fallback khi CDN không hỗ trợ Range hoặc file quá nhỏ để chia phần.
    Vẫn xin 1 slot từ `slots` (hàng rào kết nối chung toàn app) để nhất quán."""
    async with slots:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)
                    if video_id is not None:
                        progress_service.advance(video_id, len(chunk), kind="download")


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
    """Tải đúng 1 khoảng byte, ghi vào đúng offset của `dest` (đã pre-allocate
    đủ kích thước từ trước — mỗi worker chỉ đụng vào phần của mình, không cần
    khoá). Lỗi thì retry lại ĐÚNG khoảng này tối đa `_RANGE_RETRY_ATTEMPTS`
    lần, không phải tải lại cả file."""
    for attempt in range(_RANGE_RETRY_ATTEMPTS):
        part_bytes = 0
        try:
            async with slots:
                async with client.stream(
                    "GET", url, headers={"Range": f"bytes={start}-{end}"}
                ) as response:
                    if response.status_code != 206:
                        # Một số CDN lờ header Range và trả cả file (200) —
                        # không phải lỗi mạng, retry vô ích, phải báo ngay để
                        # người gọi rơi về tải 1 luồng thay vì ghi đè lung tung.
                        raise _RangeNotHonoredError(
                            f"Server trả status {response.status_code} thay vì 206 cho Range request"
                        )
                    with open(dest, "r+b") as f:
                        f.seek(start)
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
                            part_bytes += len(chunk)
                            if video_id is not None:
                                progress_service.advance(video_id, len(chunk), kind="download")
            return
        except _RangeNotHonoredError:
            if video_id is not None and part_bytes:
                progress_service.advance(video_id, -part_bytes)
            raise
        except Exception:
            # Thử lại đã đọc dở dang: trả lại đúng số byte đã cộng nhầm trước
            # khi thử lại từ đầu khoảng này — nếu không, % sẽ vượt quá 100%
            # (cộng 2 lần cho cùng 1 khoảng byte).
            if video_id is not None and part_bytes:
                progress_service.advance(video_id, -part_bytes)
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
    """Tải 1 stream (video-only hoặc audio-only) — chia `connections` phần
    qua HTTP Range nếu đủ điều kiện, không thì rơi về 1 kết nối.

    Điều kiện chia phần (Phase 21, đo thật 2026-09-22): `connections > 1`,
    server xác nhận hỗ trợ Range, và biết trước kích thước đủ lớn hơn
    `download_part_min_bytes` (chia file bé chỉ tốn thêm bắt tay TLS, không
    bù lại được gì — xem docs/phases/phase-21-parallel-download.md).
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

    # Pre-allocate đúng kích thước cuối cùng ngay từ đầu — mỗi worker `seek()`
    # tới offset của mình rồi ghi, không cần N file part rồi nối lại (tốn gấp
    # đôi dung lượng đĩa + thêm 1 lượt đọc/ghi toàn bộ file).
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
        # CDN nói có hỗ trợ Range (accept-ranges: bytes ở HEAD) nhưng GET thật
        # lại không tôn trọng — hiếm nhưng đã thấy trên các CDN "lười". Xoá
        # phần đã tải dở (có thể lẫn dữ liệu từ nhiều offset khác nhau, không
        # dùng lại được) rồi tải lại bằng 1 kết nối cho chắc.
        #
        # Giới hạn đã biết: các phần đã tải xong TRƯỚC khi phần lỗi xảy ra vẫn
        # giữ nguyên số byte đã cộng vào progress (không rollback được chính
        # xác vì `asyncio.gather` huỷ các phần còn dở dang, không phải phần đã
        # xong) — `_download_whole` cộng thêm từ đầu có thể khiến % vượt 100%
        # tạm thời. `TaskProgress.percent` đã tự kẹp về tối đa 100%
        # (`min(100.0, ...)`) nên không hiện số vô lý, chỉ có thể chạy tới
        # 100% sớm hơn thực tế trong đúng trường hợp hiếm này — chấp nhận được,
        # không đáng để thêm cơ chế theo dõi byte phức tạp cho 1 edge case hiếm.
        logger.warning(
            "CDN không tôn trọng Range request dù báo có hỗ trợ, rơi về 1 kết nối: %s", url
        )
        await _download_whole(client, url, dest, video_id=video_id, slots=slots)


async def download_bilibili_video(
    job_id: int, video_id: int, bvid: str, cid: int, *, connections: int = 1
) -> Path:
    """Tải video-only + audio-only stream (DASH) rồi ghép bằng ffmpeg.

    Raises FfmpegNotFoundError sớm (trước khi tải) nếu chưa cài ffmpeg, tránh tải
    xong hàng chục MB rồi mới báo lỗi ở bước merge.

    Xếp hàng qua semaphore khi đã đủ `download_max_videos` lượt tải chạy song
    song (Phase 20 — tick chọn hàng loạt ở màn Khám phá) — báo stage "queued"
    trong lúc chờ để UI không hiện % đứng yên khó hiểu.

    `connections` (Phase 21, mặc định 1 = hành vi cũ): số phần chia HTTP Range
    cho MỖI stream (video/audio) — trần thật cho cả app là
    `settings_service.DOWNLOAD_CONNECTIONS_MAX`, xem `_get_connection_slots()`.
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
    """Thân việc tải thật — chạy sau khi đã giữ được 1 slot semaphore số video."""
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
        # Dò kích thước CẢ 2 trước để báo 1 chặng "đang tải" duy nhất với tổng
        # dung lượng thật — video+audio giờ tải SONG SONG (Phase 21) nên 2
        # chặng nối tiếp "video" rồi "audio" như trước sẽ làm % nhảy loạn.
        # Không biết được kích thước (proxy lạ, timeout) thì total=None —
        # progress vẫn chạy đúng, chỉ không hiện % (xem TaskProgress.percent).
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
    # to_thread: subprocess.run là lệnh chặn — gọi thẳng ở đây sẽ đứng cả event
    # loop (hàm này chạy trực tiếp trên loop chính khi được queue làm background
    # task, xem docs/performance-optimization/plan.md mục P0).
    await asyncio.to_thread(ffmpeg.merge_video_audio, video_tmp, audio_tmp, output_path)
    video_tmp.unlink(missing_ok=True)
    audio_tmp.unlink(missing_ok=True)
    return output_path


async def run_download_task(video_id: int) -> None:
    """Chạy nền: tải 1 video theo id, tự mở session riêng (session của request
    tạo ra task này đã đóng khi hàm này chạy).

    Dùng chung cho cả 2 lối vào: nút "Tải video" đơn lẻ (`POST
    /api/videos/{id}/download`, trang Video của tôi) và tải hàng loạt từ màn
    Khám phá (`POST /api/jobs/from-selection`, Phase 20) — trước đây logic này
    nằm riêng trong `api/pipeline.py`, chuyển sang đây để không phải chép lại
    y hệt cho lối vào thứ 2.
    """
    with SessionLocal() as db:
        video = db.get(Video, video_id)
        if video is None:
            progress_service.finish(video_id, error="Video không còn tồn tại")
            return
        try:
            # Đọc LÚC BẮT ĐẦU lượt tải này (không cache ở import-time) — đổi
            # cài đặt phải có tác dụng ngay với video tải tiếp theo, không bắt
            # khởi động lại backend (Phase 21, xem Definition of Done).
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
