from fastapi.testclient import TestClient

from app.main import app
from app.services import log_service

client = TestClient(app)


def test_logs_endpoint_returns_tail(tmp_path, monkeypatch) -> None:
    f = tmp_path / "backend.log"
    f.write_text("a\nb\nc\n", encoding="utf-8")
    monkeypatch.setattr(log_service, "log_file_path", lambda: f)

    res = client.get("/api/system/logs", params={"lines": 2})

    assert res.status_code == 200
    body = res.json()
    assert body["exists"] is True
    assert body["lines"] == ["b", "c"]
    assert body["path"] == str(f)


def test_logs_endpoint_rejects_absurd_line_count() -> None:
    assert client.get("/api/system/logs", params={"lines": 999999}).status_code == 422
