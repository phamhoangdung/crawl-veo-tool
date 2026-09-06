from sqlalchemy.orm import Session

from app.adapters.bilibili.client import BilibiliClient
from app.models.job import Job, JobStatus, Platform
from app.models.video import Video, VideoStatus


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


async def create_bilibili_crawl_job(db: Session, user_id: int, keyword: str) -> Job:
    job = Job(user_id=user_id, platform=Platform.BILIBILI, keyword=keyword, status=JobStatus.RUNNING)
    db.add(job)
    db.flush()

    async with BilibiliClient() as client:
        results = await client.search_videos(keyword)

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
                source_url=f"https://www.bilibili.com/video/{bvid}",
                status=VideoStatus.QUEUED,
            )
        )

    job.status = JobStatus.COMPLETED
    db.commit()
    db.refresh(job)
    return job
