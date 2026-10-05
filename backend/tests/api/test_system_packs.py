from fastapi.testclient import TestClient

from app.core import packs
from app.main import app

client = TestClient(app)


def test_list_packs_reports_both_packs(monkeypatch) -> None:
    monkeypatch.setattr(packs, "is_installed", lambda pack_id: pack_id == "ffmpeg")
    response = client.get("/api/system/packs")
    assert response.status_code == 200
    by_id = {p["id"]: p for p in response.json()}
    assert by_id["ffmpeg"]["installed"] is True
    assert by_id["ai"]["installed"] is False


def test_install_unknown_pack_is_404() -> None:
    assert client.post("/api/system/packs/nope/install").status_code == 404
