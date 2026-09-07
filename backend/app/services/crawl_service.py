import logging

from sqlalchemy.orm import Session

from app.adapters.bilibili.client import BilibiliClient
from app.models.job import Job, JobStatus, Platform
from app.models.video import Video, VideoStatus
from app.schemas.job import SelectedVideo
from app.services import translate_service

logger = logging.getLogger(__name__)


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


async def translate_keyword_to_chinese(db: Session, user_id: int, keyword: str) -> str:
    """Dịch từ khoá sang tiếng Trung giản thể để search trên Bilibili.

    Trả lại từ khoá gốc nếu dịch lỗi — thà search nguyên văn còn hơn chặn cả job.
    """
    if _looks_chinese(keyword):
        return keyword
    try:
        translated = await translate_service.translate_text(
            db, user_id, keyword, source_lang="vi", target_lang="zh-CN"
        )
    except Exception as exc:  # noqa: BLE001 — dịch hỏng không được làm chết job
        logger.warning("Dịch từ khoá '%s' thất bại (%s), dùng nguyên văn", keyword, exc)
        return keyword
    return translated.strip() or keyword


async def create_bilibili_crawl_job(
    db: Session, user_id: int, keyword: str, translate_keyword: bool = False
) -> Job:
    search_keyword = keyword
    if translate_keyword:
        search_keyword = await translate_keyword_to_chinese(db, user_id, keyword)

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

    for item in results:
        bvid = item.get("bvid")
        if not bvid:
            continue
        already_downloaded = (
            db.query(Video)
            .filter(Video.platform == Platform.BILIBILI, Video.platform_video_id == bvid)
            .first()
        )
        if already_downloaded:
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
