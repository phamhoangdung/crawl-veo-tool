"""Periodically check whether the Bilibili API still behaves as the adapter assumes —
detect early when Bilibili changes its API instead of finding out only after a real crawl job fails."""

from app.adapters.bilibili.client import BilibiliApiError, BilibiliClient


async def check_bilibili_downloader() -> dict:
    checks: dict[str, dict] = {}

    async with BilibiliClient() as client:
        for name, coro in [
            ("popular", client.get_popular(page=1, page_size=1)),
            ("ranking", client.get_ranking(rid=1, day=3)),
            ("search", client.search_videos("test", page=1)),
        ]:
            try:
                result = await coro
                checks[name] = {"ok": True, "detail": f"{len(result)} kết quả"}
            except BilibiliApiError as exc:
                checks[name] = {"ok": False, "detail": f"Bilibili API error {exc.code}: {exc}"}
            except Exception as exc:  # noqa: BLE001 — the health check must catch every error to report it, not crash
                checks[name] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    all_ok = all(c["ok"] for c in checks.values())
    return {"healthy": all_ok, "checks": checks}
