from __future__ import annotations

import re

import httpx

from app.adapters.bilibili import wbi

_BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.bilibili.com",
}
_EM_TAG_RE = re.compile(r"</?em[^>]*>")


class BilibiliApiError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"Bilibili API error {code}: {message}")
        self.code = code


class BilibiliRiskControlError(BilibiliApiError):
    """Phase 22: `x/space/wbi/arc/search` (a channel's videos) is hit by Bilibili's
    risk control even harder than `x/web-interface/view` — it returns HTTP 412 or error code
    -352 (documented by community write-ups, see
    docs/phases/phase-22-channel-follow.md, Survey #3). It is NOT the
    "this channel has no videos" case — the caller must be able to tell them apart to show the right
    "currently rate limited" message instead of "empty channel", and must NOT treat this as a
    500 error that breaks the whole preview popup."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(code, message)


def _strip_highlight_tags(title: str) -> str:
    """The search API sometimes wraps matched keywords in <em class="keyword">...</em>."""
    return _EM_TAG_RE.sub("", title)


class BilibiliClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client or httpx.AsyncClient(headers=_BASE_HEADERS, timeout=15)
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "BilibiliClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _get_json(self, url: str, params: dict) -> dict:
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if payload["code"] != 0:
            raise BilibiliApiError(payload["code"], payload.get("message", ""))
        return payload

    async def search_videos(self, keyword: str, page: int = 1) -> list[dict]:
        params = await wbi.sign_params(
            self._client, {"search_type": "video", "keyword": keyword, "page": page}
        )
        payload = await self._get_json(
            "https://api.bilibili.com/x/web-interface/wbi/search/all/v2", params
        )
        for group in payload["data"].get("result", []):
            if group.get("result_type") == "video":
                for item in group.get("data", []):
                    item["title"] = _strip_highlight_tags(item.get("title", ""))
                return group["data"]
        return []

    async def get_popular(self, page: int = 1, page_size: int = 20) -> list[dict]:
        payload = await self._get_json(
            "https://api.bilibili.com/x/web-interface/popular",
            {"pn": page, "ps": page_size},
        )
        return payload["data"]["list"]

    async def get_online_list(self) -> list[dict]:
        """Currently popular videos — each item carries tid/tname, used to discover categories."""
        payload = await self._get_json(
            "https://api.bilibili.com/x/web-interface/online/list", {}
        )
        return payload["data"]

    async def get_ranking(self, rid: int, day: int = 3) -> list[dict]:
        payload = await self._get_json(
            "https://api.bilibili.com/x/web-interface/ranking/region",
            {"rid": rid, "day": day},
        )
        return payload["data"]

    async def get_video_cid(self, bvid: str) -> int:
        """`x/web-interface/view` is often blocked with 412 (risk control) — use `pagelist` instead,
        which gives the same cid but is blocked less. Takes the cid of the first part (single-part video)."""
        payload = await self._get_json(
            "https://api.bilibili.com/x/player/pagelist", {"bvid": bvid}
        )
        return payload["data"][0]["cid"]

    async def get_play_streams(self, bvid: str, cid: int) -> dict:
        params = await wbi.sign_params(
            self._client, {"bvid": bvid, "cid": cid, "fnval": 16}
        )
        payload = await self._get_json(
            "https://api.bilibili.com/x/player/wbi/playurl", params
        )
        return payload["data"]["dash"]

    async def get_related(self, bvid: str) -> list[dict]:
        """Related videos (Phase 22) — a public endpoint, NO WBI signature needed,
        low risk-control exposure (the same API used for the "related videos" sidebar
        on Bilibili's own watch page, with very large public traffic)."""
        payload = await self._get_json(
            "https://api.bilibili.com/x/web-interface/archive/related", {"bvid": bvid}
        )
        return payload["data"]

    async def get_space_videos(
        self, mid: str, page: int = 1, page_size: int = 25
    ) -> list[dict]:
        """Other videos of a channel (Phase 22) — needs a WBI signature, and Bilibili applies heavy
        risk control (see the `BilibiliRiskControlError` docstring). Wraps both
        HTTP 412 and error code -352 into `BilibiliRiskControlError` so the caller can
        tell it apart from "the channel truly has no videos"."""
        params = await wbi.sign_params(
            self._client, {"mid": mid, "pn": page, "ps": page_size, "order": "pubdate"}
        )
        try:
            payload = await self._get_json(
                "https://api.bilibili.com/x/space/wbi/arc/search", params
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 412:
                raise BilibiliRiskControlError(412, "HTTP 412 — Bilibili risk control") from exc
            raise
        except BilibiliApiError as exc:
            if exc.code in (-352, -412):
                raise BilibiliRiskControlError(exc.code, str(exc)) from exc
            raise
        return payload["data"]["list"]["vlist"]
