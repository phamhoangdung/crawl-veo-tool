import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ],
)
def test_preflight_allowed_for_dev_and_tauri_origins(origin: str) -> None:
    response = client.options(
        "/api/jobs",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_preflight_rejected_for_foreign_origin() -> None:
    response = client.options(
        "/api/jobs",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400
