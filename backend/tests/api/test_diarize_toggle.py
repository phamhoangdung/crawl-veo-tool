"""Phân vai người nói có công tắc trong Cài đặt (mặc định tắt)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.db import Base, get_db
from app.main import app
from app.models.job import Job
from app.models.user import User
from app.models.video import Platform, Video, VideoStatus


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add(User(id=1))
        db.commit()  # không có relationship nên SQLAlchemy không tự sắp thứ tự FK
        db.add(Job(id=1, user_id=1, platform=Platform.LOCAL, keyword="k"))
        db.commit()
        db.add(
            Video(
                id=1,
                user_id=1,
                job_id=1,
                platform=Platform.LOCAL,
                platform_video_id="x",
                title="t",
                source_url="local://x",
                status=VideoStatus.TRANSCRIBED,
                transcript_json=[{"start": 0, "end": 1, "text": "a"}],
            )
        )
        db.commit()

    def _get_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_settings_default_off(client) -> None:
    assert client.get("/api/settings").json()["speaker_diarization_enabled"] is False


def test_diarize_rejected_while_disabled(client) -> None:
    res = client.post("/api/videos/1/diarize")
    assert res.status_code == 409
    assert "Cài đặt" in res.json()["detail"]


def test_diarize_accepted_after_enabling(client, monkeypatch) -> None:
    from app.api import pipeline

    monkeypatch.setattr(pipeline, "_run_diarize", lambda video_id: None)
    res = client.put("/api/settings", json={"speaker_diarization_enabled": True})
    assert res.json()["speaker_diarization_enabled"] is True
    assert client.post("/api/videos/1/diarize").status_code == 200
