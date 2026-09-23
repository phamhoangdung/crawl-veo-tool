from fastapi.testclient import TestClient

from app.main import app
from app.services import import_service

client = TestClient(app)


def test_rejects_non_video_file() -> None:
    res = client.post(
        "/api/videos/import", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert res.status_code == 400
    assert "chưa hỗ trợ" in res.json()["detail"]


def test_cover_404_for_unknown_video() -> None:
    assert client.get("/api/videos/99999999/cover").status_code == 404


def test_extension_whitelist_covers_common_formats() -> None:
    for ext in (".mp4", ".mkv", ".mov", ".avi", ".webm"):
        assert ext in import_service.ALLOWED_EXTENSIONS
