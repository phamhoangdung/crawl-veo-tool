from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_category_page_rejects_ranking_days_bilibili_does_not_support() -> None:
    for day in (1, 30, 365):
        res = client.get("/api/trending/bilibili/category-page", params={"rid": 21, "day": day})
        assert res.status_code == 422


def test_ranking_rejects_unsupported_days() -> None:
    res = client.get("/api/trending/bilibili/ranking", params={"rid": 21, "day": 30})
    assert res.status_code == 422
