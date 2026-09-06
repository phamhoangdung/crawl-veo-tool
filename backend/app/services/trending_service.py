from app.adapters.bilibili.client import BilibiliClient
from app.schemas.trending import TrendingVideoRead


def _parse_duration_to_seconds(raw: str | int | None) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if raw.isdigit():
        return int(raw)
    parts = raw.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + int(seconds)
    return None


async def get_bilibili_popular(page: int = 1, page_size: int = 20) -> list[TrendingVideoRead]:
    async with BilibiliClient() as client:
        items = await client.get_popular(page=page, page_size=page_size)
    return [
        TrendingVideoRead(
            bvid=item["bvid"],
            title=item.get("title", ""),
            author_name=(item.get("owner") or {}).get("name"),
            duration_seconds=_parse_duration_to_seconds(item.get("duration")),
            cover_url=item.get("pic"),
        )
        for item in items
    ]


async def get_bilibili_ranking(rid: int, day: int = 3) -> list[TrendingVideoRead]:
    async with BilibiliClient() as client:
        items = await client.get_ranking(rid=rid, day=day)
    return [
        TrendingVideoRead(
            bvid=item["bvid"],
            title=item.get("title", ""),
            author_name=item.get("author"),
            play_count=item.get("play"),
            duration_seconds=_parse_duration_to_seconds(item.get("duration")),
            cover_url=item.get("pic"),
        )
        for item in items
    ]
