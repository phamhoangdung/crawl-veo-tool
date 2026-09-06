import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.video import Video


def list_processed_videos(db: Session, user_id: int) -> list[Video]:
    return (
        db.query(Video)
        .filter(Video.user_id == user_id, Video.local_path.isnot(None))
        .order_by(Video.created_at.desc())
        .all()
    )


def resolve_download_path(video: Video, variant: str) -> Path | None:
    path_by_variant = {
        "burned": video.burned_path,
        "dubbed": video.dubbed_path,
        "original": video.local_path,
    }
    raw_path = path_by_variant.get(variant)
    return Path(raw_path) if raw_path else None


def build_zip(videos: list[Video], variant: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for video in videos:
            path = resolve_download_path(video, variant)
            if path and path.exists():
                zf.write(path, arcname=f"{video.id}_{path.name}")
    return output_path
