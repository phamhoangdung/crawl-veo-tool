from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.adapters.youtube.client import (
    YouTubeApiError,
    YouTubeInvalidKeyError,
    YouTubeNotConfiguredError,
    YouTubeQuotaExceededError,
)
from app.core.db import get_db
from app.models.topic import Topic
from app.schemas.youtube import TopicCreateRequest, TopicRead
from app.services import topic_service

router = APIRouter(prefix="/api/topics", tags=["topics"])

# MVP: 1 user cố định — xem app/api/crawl.py.
_DEFAULT_USER_ID = 1


def _to_read(topic: Topic) -> TopicRead:
    return TopicRead(
        id=topic.id,
        name=topic.name,
        query=topic.query,
        note=topic.note,
        created_at=topic.created_at,
        score=topic.score,
        sample_video_count=topic.sample_video_count,
        competition_count=topic.competition_count,
        top_video_title=topic.top_video_title,
        top_video_url=topic.top_video_url,
        scored_at=topic.scored_at,
    )


@router.get("", response_model=list[TopicRead])
def list_topics(db: Session = Depends(get_db)) -> list[TopicRead]:
    return [_to_read(t) for t in topic_service.list_topics(db, _DEFAULT_USER_ID)]


@router.post("", response_model=TopicRead)
def create_topic(payload: TopicCreateRequest, db: Session = Depends(get_db)) -> TopicRead:
    return _to_read(topic_service.create_topic(db, _DEFAULT_USER_ID, payload))


@router.delete("/{topic_id}")
def delete_topic(topic_id: int, db: Session = Depends(get_db)) -> dict:
    deleted = topic_service.delete_topic(db, _DEFAULT_USER_ID, topic_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"deleted": True}


@router.post("/{topic_id}/score", response_model=TopicRead)
async def compute_score(topic_id: int, db: Session = Depends(get_db)) -> TopicRead:
    try:
        return _to_read(await topic_service.compute_score(db, _DEFAULT_USER_ID, topic_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except topic_service.TopicScoreCooldownError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except YouTubeNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except YouTubeQuotaExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail=f"YouTube Data API hết quota trong ngày: {exc}",
        ) from exc
    except YouTubeInvalidKeyError as exc:
        raise HTTPException(status_code=401, detail=f"API key YouTube không hợp lệ: {exc}") from exc
    except YouTubeApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
