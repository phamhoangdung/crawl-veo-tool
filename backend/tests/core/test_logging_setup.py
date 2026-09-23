import logging

from app.core.logging_setup import _AccessNoiseFilter


def _record(name: str, msg: str) -> logging.LogRecord:
    return logging.LogRecord(name, logging.INFO, "f", 1, msg, None, None)


def test_drops_polling_access_lines() -> None:
    f = _AccessNoiseFilter()
    for msg in (
        '127.0.0.1:1 - "GET /health HTTP/1.1" 200',
        '127.0.0.1:1 - "GET /api/downloads/progress HTTP/1.1" 200',
        '127.0.0.1:1 - "GET /api/system/logs?lines=500 HTTP/1.1" 200',
    ):
        assert f.filter(_record("uvicorn.access", msg)) is False


def test_keeps_real_requests_and_non_access_logs() -> None:
    f = _AccessNoiseFilter()
    assert f.filter(_record("uvicorn.access", '127.0.0.1:1 - "POST /api/jobs HTTP/1.1" 200'))
    assert f.filter(_record("uvicorn.access", '"GET /health/downloader HTTP/1.1" 200'))
    assert f.filter(_record("app.services.x", "GET /api/downloads/progress lỗi thật"))
