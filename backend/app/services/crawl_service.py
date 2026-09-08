import logging
import time

from sqlalchemy.orm import Session

from app.adapters.bilibili.client import BilibiliClient
from app.models.job import Job, JobStatus, Platform
from app.models.video import Video, VideoStatus
from app.schemas.job import SelectedVideo
from app.services import translate_service

logger = logging.getLogger(__name__)

# Cache tạm trong process (mất khi restart server) cho từ khoá search vừa dịch
# gần đây — người dùng hay bấm lại/gõ lại cùng 1 từ khoá, cache tránh gọi lại
# API dịch mỗi lần (đỡ tốn quota và đỡ dính rate limit của Google Translate free).
_KEYWORD_TRANSLATION_CACHE_TTL_SECONDS = 3600
_keyword_translation_cache: dict[str, tuple[str, float]] = {}


def _get_cached_translation(keyword: str) -> str | None:
    cached = _keyword_translation_cache.get(keyword)
    if cached is None:
        return None
    translated, expires_at = cached
    if time.monotonic() > expires_at:
        del _keyword_translation_cache[keyword]
        return None
    return translated


def _cache_translation(keyword: str, translated: str) -> None:
    _keyword_translation_cache[keyword] = (
        translated,
        time.monotonic() + _KEYWORD_TRANSLATION_CACHE_TTL_SECONDS,
    )


def _looks_chinese(text: str) -> bool:
    """Đã là tiếng Trung thì khỏi dịch — tránh gọi API thừa và tránh dịch sai ngược."""
    return any("一" <= ch <= "鿿" for ch in text)


def _parse_duration_to_seconds(raw: str | int | None) -> int | None:
    """Bilibili trả duration dạng 'mm:ss' (search) hoặc số giây thuần (ranking)."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if raw.isdigit():
        return int(raw)
    parts = raw.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + int(seconds)
    return None


def _normalize_cover_url(raw: str | None) -> str | None:
    """Search API trả ảnh dạng '//i2.hdslb.com/...' (thiếu scheme) — thêm https."""
    if not raw:
        return None
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.startswith("http://"):
        return f"https://{raw[len('http://'):]}"
    return raw


async def translate_keyword_to_chinese(db: Session, user_id: int, keyword: str) -> tuple[str, bool]:
    """Dịch từ khoá sang tiếng Trung giản thể để search trên Bilibili.

    Trả lại từ khoá gốc nếu dịch lỗi — thà search nguyên văn còn hơn chặn cả job.
    Cờ bool thứ hai báo có dịch thành công không, để tầng gọi cảnh báo người
    dùng thay vì âm thầm search nguyên văn tiếng Việt (gần như chắc chắn 0 kết quả).
    """
    if _looks_chinese(keyword):
        return keyword, True

    # Cache trong RAM cho các lần gọi liên tiếp trong cùng phiên.
    cached = _get_cached_translation(keyword)
    if cached is not None:
        return cached, True

    try:
        # `translate_cached` lưu bản dịch vào bảng translation_cache nên từ khoá
        # đã dịch còn nguyên sau khi restart — cache RAM ở trên mất khi restart.
        translated, _ = await translate_service.translate_cached(
            db, user_id, keyword, source_lang="vi", target_lang="zh-CN"
        )
    except Exception as exc:  # noqa: BLE001 — dịch hỏng không được làm chết job
        logger.warning("Dịch từ khoá '%s' thất bại (%s), dùng nguyên văn", keyword, exc)
        return keyword, False
    translated = translated.strip()
    if not translated:
        return keyword, False
    _cache_translation(keyword, translated)
    return translated, True


async def create_bilibili_crawl_job(
    db: Session, user_id: int, keyword: str, translate_keyword: bool = False
) -> Job:
    search_keyword = keyword
    translation_failed = False
    if translate_keyword:
        search_keyword, translated_ok = await translate_keyword_to_chinese(db, user_id, keyword)
        translation_failed = not translated_ok

    job = Job(
        user_id=user_id,
        platform=Platform.BILIBILI,
        # Lưu từ khoá thực sự đem đi search để sau này biết job đã tìm bằng gì.
        keyword=search_keyword,
        status=JobStatus.RUNNING,
    )
    db.add(job)
    db.flush()

    async with BilibiliClient() as client:
        results = await client.search_videos(search_keyword)

    # Hiện ĐẦY ĐỦ kết quả Bilibili trả về, kể cả video đã có trong thư viện —
    # người dùng muốn thấy đúng những gì Bilibili tìm được. Video đã có chỉ được
    # đánh dấu (`already_in_library`) để không tải lại, chứ không bị ẩn đi.
    bvids = [item["bvid"] for item in results if item.get("bvid")]
    existing_bvids = {
        row[0]
        for row in db.query(Video.platform_video_id)
        .filter(
            Video.platform == Platform.BILIBILI,
            Video.platform_video_id.in_(bvids),
        )
        .all()
    }

    # Chỉ INSERT video chưa có: bảng có UniqueConstraint(platform,
    # platform_video_id) nên chèn lại bvid cũ sẽ vi phạm ràng buộc.
    for item in results:
        bvid = item.get("bvid")
        if not bvid or bvid in existing_bvids:
            continue
        db.add(
            Video(
                user_id=user_id,
                job_id=job.id,
                platform=Platform.BILIBILI,
                platform_video_id=bvid,
                title=item.get("title", ""),
                author_name=item.get("author"),
                duration_seconds=_parse_duration_to_seconds(item.get("duration")),
                cover_url=_normalize_cover_url(item.get("pic")),
                source_url=f"https://www.bilibili.com/video/{bvid}",
                status=VideoStatus.QUEUED,
            )
        )

    job.status = JobStatus.COMPLETED
    db.commit()
    db.refresh(job)

    # Trả về ĐỦ những gì Bilibili tìm được, theo đúng thứ tự — kể cả video đã có
    # trong thư viện (thuộc job cũ nên không nằm trong `job.videos`).
    #
    # KHÔNG gán vào `job.videos`: đó là quan hệ SQLAlchemy, gán vào sẽ dời
    # `job_id` của video cũ sang job này và làm mất liên kết với job gốc (đã thử
    # và xác nhận). Dùng thuộc tính tạm riêng để schema đọc.
    all_rows = {
        v.platform_video_id: v
        for v in db.query(Video)
        .filter(
            Video.platform == Platform.BILIBILI,
            Video.platform_video_id.in_(bvids),
        )
        .all()
    }
    ordered = [
        all_rows[item["bvid"]]
        for item in results
        if item.get("bvid") and item["bvid"] in all_rows
    ]
    # Đánh dấu từng video: cờ tạm trên ORM object, schema đọc ra. Trạng thái
    # không đủ để suy ra — video đã tải nhưng chưa xử lý vẫn là `queued`.
    for video in ordered:
        video.already_in_library = video.platform_video_id in existing_bvids
    job.result_videos = ordered

    # Cờ tạm, không lưu DB — chỉ để router trả về cho frontend cảnh báo ngay lần này.
    job.translation_failed = translation_failed
    # Số video đã có trong thư viện — vẫn hiện trong danh sách, chỉ để UI đánh dấu.
    job.already_in_library = len(existing_bvids)
    job.total_found = len(results)
    return job


async def create_job_from_selection(
    db: Session, user_id: int, items: list[SelectedVideo]
) -> Job:
    """Tạo job từ các video người dùng tự chọn ở trang Trending.

    Metadata đã có sẵn từ danh sách trending nên không cần gọi lại API Bilibili.
    Video đã tồn tại trong DB thì bỏ qua, giống luồng crawl theo từ khoá.
    """
    job = Job(
        user_id=user_id,
        platform=Platform.BILIBILI,
        keyword=f"[Trending] {len(items)} video đã chọn",
        status=JobStatus.RUNNING,
    )
    db.add(job)
    db.flush()

    for item in items:
        exists = (
            db.query(Video)
            .filter(Video.platform == Platform.BILIBILI, Video.platform_video_id == item.bvid)
            .first()
        )
        if exists:
            continue
        db.add(
            Video(
                user_id=user_id,
                job_id=job.id,
                platform=Platform.BILIBILI,
                platform_video_id=item.bvid,
                title=item.title,
                author_name=item.author_name,
                duration_seconds=item.duration_seconds,
                cover_url=_normalize_cover_url(item.cover_url),
                source_url=f"https://www.bilibili.com/video/{item.bvid}",
                status=VideoStatus.QUEUED,
            )
        )

    job.status = JobStatus.COMPLETED
    db.commit()
    db.refresh(job)
    return job


async def append_videos_to_job(db: Session, job_id: int, page: int) -> tuple[list[Video], bool]:
    """Tải thêm 1 trang kết quả search vào job đã có (infinite scroll trang Crawl).

    Dùng lại `job.keyword` — vốn đã là từ khoá thực sự đem đi search (đã dịch
    nếu người dùng bật). Trả về (video mới thêm, còn trang sau không).
    """
    job = db.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} không tồn tại")

    async with BilibiliClient() as client:
        results = await client.search_videos(job.keyword, page=page)

    created: list[Video] = []
    for item in results:
        bvid = item.get("bvid")
        if not bvid:
            continue
        exists = (
            db.query(Video)
            .filter(Video.platform == Platform.BILIBILI, Video.platform_video_id == bvid)
            .first()
        )
        if exists:
            continue
        video = Video(
            user_id=job.user_id,
            job_id=job.id,
            platform=Platform.BILIBILI,
            platform_video_id=bvid,
            title=item.get("title", ""),
            author_name=item.get("author"),
            duration_seconds=_parse_duration_to_seconds(item.get("duration")),
            cover_url=_normalize_cover_url(item.get("pic")),
            source_url=f"https://www.bilibili.com/video/{bvid}",
            status=VideoStatus.QUEUED,
        )
        db.add(video)
        created.append(video)

    db.commit()
    for video in created:
        db.refresh(video)

    # Search trả rỗng nghĩa là hết trang. Trang toàn video trùng vẫn còn trang sau.
    return created, bool(results)
