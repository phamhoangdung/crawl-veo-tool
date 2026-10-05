import logging
import time

from sqlalchemy.orm import Session

from app.adapters.bilibili.client import BilibiliClient
from app.models.job import Job, JobStatus, Platform
from app.models.video import Video, VideoStatus
from app.schemas.job import SelectedVideo
from app.services import translate_service

logger = logging.getLogger(__name__)

# In-process temporary cache (lost on server restart) for recently translated search
# keywords — users often click again/retype the same keyword, the cache avoids calling the
# translation API each time (saving quota and avoiding the rate limit of free Google Translate).
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
    """Already Chinese means no translation needed — avoids a spare API call and avoids translating wrongly in reverse."""
    return any("一" <= ch <= "鿿" for ch in text)


def _parse_duration_to_seconds(raw: str | int | None) -> int | None:
    """Bilibili returns duration as 'mm:ss' (search) or plain seconds (ranking)."""
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
    """The search API returns the image as '//i2.hdslb.com/...' (missing the scheme) — add https."""
    if not raw:
        return None
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.startswith("http://"):
        return f"https://{raw[len('http://') :]}"
    return raw


async def translate_keyword_to_chinese(
    db: Session, user_id: int, keyword: str
) -> tuple[str, bool]:
    """Translate the keyword to Simplified Chinese to search on Bilibili.

    Returns the original keyword if translation fails — better a verbatim search than blocking the whole job.
    The second bool flag says whether translation succeeded, so the calling layer can warn the
    user instead of silently searching verbatim Vietnamese (almost certainly 0 results).
    """
    if _looks_chinese(keyword):
        return keyword, True

    # In-RAM cache for consecutive calls within the same session.
    cached = _get_cached_translation(keyword)
    if cached is not None:
        return cached, True

    try:
        # `translate_cached` stores the translation in the translation_cache table so keywords
        # already translated survive a restart — the RAM cache above is lost on restart.
        translated, _ = await translate_service.translate_cached(
            db, user_id, keyword, source_lang="vi", target_lang="zh-CN"
        )
    except Exception as exc:  # noqa: BLE001 — a failed translation must not kill the job
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
        search_keyword, translated_ok = await translate_keyword_to_chinese(
            db, user_id, keyword
        )
        translation_failed = not translated_ok

    job = Job(
        user_id=user_id,
        platform=Platform.BILIBILI,
        # Store the keyword actually used for the search so we later know what the job searched with.
        keyword=search_keyword,
        status=JobStatus.RUNNING,
    )
    db.add(job)
    db.flush()

    async with BilibiliClient() as client:
        results = await client.search_videos(search_keyword)

    # Show the FULL Bilibili results, including videos already in the library —
    # users want to see exactly what Bilibili found. Existing videos are only
    # marked (`already_in_library`) so they are not downloaded again, not hidden.
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

    # Only INSERT videos that do not exist: the table has UniqueConstraint(platform,
    # platform_video_id) so re-inserting an old bvid would violate the constraint.
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
                channel_id=str(item["mid"]) if item.get("mid") else None,
                duration_seconds=_parse_duration_to_seconds(item.get("duration")),
                cover_url=_normalize_cover_url(item.get("pic")),
                source_url=f"https://www.bilibili.com/video/{bvid}",
                status=VideoStatus.QUEUED,
            )
        )

    job.status = JobStatus.COMPLETED
    db.commit()
    db.refresh(job)

    # Return ALL that Bilibili found, in the exact order — including videos already
    # in the library (belonging to an old job so not in `job.videos`).
    #
    # Do NOT assign to `job.videos`: it is a SQLAlchemy relationship, assigning would move the
    # old video's `job_id` to this job and lose the link with the original job (tried
    # and confirmed). Use a separate temporary attribute for the schema to read.
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
    # Mark each video: a temporary flag on the ORM object, read out by the schema. State
    # is not enough to infer it — a downloaded but unprocessed video is still `queued`.
    for video in ordered:
        video.already_in_library = video.platform_video_id in existing_bvids
    job.result_videos = ordered

    # Temporary flag, not stored in the DB — only so the router returns it to the frontend to warn this time.
    job.translation_failed = translation_failed
    # Number of videos already in the library — still shown in the list, only so the UI marks them.
    job.already_in_library = len(existing_bvids)
    job.total_found = len(results)
    return job


async def create_job_from_selection(
    db: Session, user_id: int, items: list[SelectedVideo]
) -> Job:
    """Create a job from the videos the user picked on the Discovery screen (Phase 20).

    Metadata is already available from the trending list so there is no need to call the Bilibili API again.

    Previously (Phase 1) a video already in the DB was skipped with `continue` —
    so the result could miss videos the user just ticked, and
    there was no way to know which videos were "already there" to show the right state. Now it
    returns the FULL selected list in the exact order (like `create_bilibili_crawl_job`),
    marking `already_in_library` for old videos — the router uses this list to
    decide which videos need a background download.
    """
    job = Job(
        user_id=user_id,
        platform=Platform.BILIBILI,
        keyword=f"[Trending] {len(items)} video đã chọn",
        status=JobStatus.RUNNING,
    )
    db.add(job)
    db.flush()

    bvids = [item.bvid for item in items]
    # 1 query for the whole list instead of querying each item in the loop (N+1) —
    # the same pattern used in `create_bilibili_crawl_job`.
    existing_bvids = {
        row[0]
        for row in db.query(Video.platform_video_id)
        .filter(Video.platform == Platform.BILIBILI, Video.platform_video_id.in_(bvids))
        .all()
    }

    for item in items:
        if item.bvid in existing_bvids:
            continue
        db.add(
            Video(
                user_id=user_id,
                job_id=job.id,
                platform=Platform.BILIBILI,
                platform_video_id=item.bvid,
                title=item.title,
                author_name=item.author_name,
                channel_id=item.channel_id,
                duration_seconds=item.duration_seconds,
                cover_url=_normalize_cover_url(item.cover_url),
                source_url=f"https://www.bilibili.com/video/{item.bvid}",
                status=VideoStatus.QUEUED,
            )
        )

    job.status = JobStatus.COMPLETED
    db.commit()
    db.refresh(job)

    # Do NOT assign to `job.videos` — a SQLAlchemy relationship, assigning would move `job_id`
    # of the old video to this job (tried in `create_bilibili_crawl_job`, see the
    # note there). Use the temporary attribute `result_videos` like the search flow.
    all_rows = {
        v.platform_video_id: v
        for v in db.query(Video)
        .filter(Video.platform == Platform.BILIBILI, Video.platform_video_id.in_(bvids))
        .all()
    }
    ordered = [all_rows[bvid] for bvid in bvids if bvid in all_rows]
    for video in ordered:
        video.already_in_library = video.platform_video_id in existing_bvids
    job.result_videos = ordered
    return job


async def append_videos_to_job(
    db: Session, job_id: int, page: int
) -> tuple[list[Video], bool]:
    """Load one more page of search results into an existing job (infinite scroll on the Crawl page).

    Reuses `job.keyword` — which is already the keyword actually used for the search (translated
    if the user enabled it). Returns (newly added videos, whether there is a next page).
    """
    job = db.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} không tồn tại")

    async with BilibiliClient() as client:
        results = await client.search_videos(job.keyword, page=page)

    # 1 query for the whole result page instead of querying each item in the loop (N+1).
    bvids = [item["bvid"] for item in results if item.get("bvid")]
    existing_bvids = {
        row[0]
        for row in db.query(Video.platform_video_id)
        .filter(Video.platform == Platform.BILIBILI, Video.platform_video_id.in_(bvids))
        .all()
    }

    created: list[Video] = []
    for item in results:
        bvid = item.get("bvid")
        if not bvid or bvid in existing_bvids:
            continue
        video = Video(
            user_id=job.user_id,
            job_id=job.id,
            platform=Platform.BILIBILI,
            platform_video_id=bvid,
            title=item.get("title", ""),
            author_name=item.get("author"),
            channel_id=str(item["mid"]) if item.get("mid") else None,
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

    # Search returning empty means no more pages. A page of all-duplicate videos still has a next page.
    return created, bool(results)
