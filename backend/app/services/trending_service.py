import asyncio
import logging

from sqlalchemy.orm import Session

from app.adapters.bilibili.client import BilibiliClient
from app.models.category import Category
from app.schemas.trending import (
    CategoryStatsRead,
    TrendingPageRead,
    TrendingVideoRead,
)
from app.services import category_service

logger = logging.getLogger(__name__)

# ranking/region trả trọn 1 lần (~11 video, không phân trang). Muốn lướt tiếp thì
# chuyển sang search theo tên tiếng Trung của category — search mới có phân trang.
_RANKING_PAGE = 1


def _parse_duration_to_seconds(raw: str | int | None) -> int | None:
    """Bilibili trả duration dạng 'mm:ss' (search) hoặc số giây thuần (ranking)."""
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
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    return None


def _normalize_cover_url(raw: str | None) -> str | None:
    """Search trả ảnh dạng '//i2.hdslb.com/...' (thiếu scheme); ranking trả http."""
    if not raw:
        return None
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.startswith("http://"):
        return f"https://{raw[len('http://'):]}"
    return raw


def _from_ranking_item(item: dict) -> TrendingVideoRead:
    return TrendingVideoRead(
        bvid=item["bvid"],
        title=item.get("title", ""),
        author_name=item.get("author"),
        play_count=item.get("play"),
        # ranking/region không trả lượt thích; `favorites` (lưu video) là chỉ số
        # tương tác gần nhất có sẵn.
        like_count=item.get("favorites"),
        duration_seconds=_parse_duration_to_seconds(item.get("duration")),
        cover_url=_normalize_cover_url(item.get("pic")),
    )


def _from_search_item(item: dict) -> TrendingVideoRead:
    return TrendingVideoRead(
        bvid=item["bvid"],
        title=item.get("title", ""),
        author_name=item.get("author"),
        play_count=item.get("play"),
        like_count=item.get("favorites"),
        duration_seconds=_parse_duration_to_seconds(item.get("duration")),
        cover_url=_normalize_cover_url(item.get("pic")),
    )


async def get_bilibili_popular(page: int = 1, page_size: int = 20) -> list[TrendingVideoRead]:
    async with BilibiliClient() as client:
        items = await client.get_popular(page=page, page_size=page_size)
    return [
        TrendingVideoRead(
            bvid=item["bvid"],
            title=item.get("title", ""),
            author_name=(item.get("owner") or {}).get("name"),
            play_count=(item.get("stat") or {}).get("view"),
            like_count=(item.get("stat") or {}).get("like"),
            duration_seconds=_parse_duration_to_seconds(item.get("duration")),
            cover_url=_normalize_cover_url(item.get("pic")),
        )
        for item in items
    ]


async def get_bilibili_ranking(rid: int, day: int = 3) -> list[TrendingVideoRead]:
    async with BilibiliClient() as client:
        items = await client.get_ranking(rid=rid, day=day)
    return [_from_ranking_item(item) for item in items]


async def get_category_page(
    db: Session, rid: int, page: int = 1, day: int = 3
) -> TrendingPageRead:
    """Trang đầu lấy từ bảng xếp hạng (đúng nghĩa 'đang hot'), các trang sau
    lấy từ search theo tên tiếng Trung của category vì ranking không phân trang.
    """
    category = db.get(Category, rid)

    async with BilibiliClient() as client:
        if page <= _RANKING_PAGE:
            items = await client.get_ranking(rid=rid, day=day)
            videos = [_from_ranking_item(item) for item in items]
            # Chỉ hứa còn trang sau khi biết search bằng từ khoá nào.
            return TrendingPageRead(
                videos=videos, page=page, has_more=category is not None
            )

        if category is None or not category.name_zh:
            return TrendingPageRead(videos=[], page=page, has_more=False)

        # Search page 1 trùng nội dung với ranking nên bắt đầu từ page 2.
        results = await client.search_videos(category.name_zh, page=page)

    seen: set[str] = set()
    videos: list[TrendingVideoRead] = []
    for item in results:
        bvid = item.get("bvid")
        if not bvid or bvid in seen:
            continue
        seen.add(bvid)
        videos.append(_from_search_item(item))

    return TrendingPageRead(videos=videos, page=page, has_more=bool(videos))


async def get_categories_stats(
    db: Session, rids: list[int], day: int = 3, save_history: bool = True
) -> list[CategoryStatsRead]:
    """Thống kê từng chuyên mục để vẽ chart, đồng thời ghi 1 điểm vào lịch sử.

    Gọi song song vì mỗi chuyên mục là 1 request riêng; chuyên mục lỗi thì bỏ
    qua thay vì làm hỏng cả biểu đồ.
    """

    async def one(rid: int) -> tuple[CategoryStatsRead, float] | None:
        category = db.get(Category, rid)
        if category is None:
            return None
        try:
            videos = await get_bilibili_ranking(rid=rid, day=day)
        except Exception as exc:  # noqa: BLE001 — 1 chuyên mục lỗi không được chặn cả chart
            logger.warning("Lấy thống kê chuyên mục %s thất bại: %s", rid, exc)
            return None
        if not videos:
            return None

        plays = [v.play_count or 0 for v in videos]
        likes = [v.like_count or 0 for v in videos]
        top = max(videos, key=lambda v: v.play_count or 0)
        avg_plays = sum(plays) // len(plays)
        # Lượt xem trung bình trên mỗi ngày xếp hạng — cho phép so sánh giữa các
        # khung thời gian khác nhau (day=1 vs day=3).
        heat_score = avg_plays / max(day, 1)

        return (
            CategoryStatsRead(
                rid=rid,
                name=category.name_vi or category.name_zh,
                group=category.group_name,
                video_count=len(videos),
                total_plays=sum(plays),
                avg_plays=avg_plays,
                max_plays=max(plays),
                total_likes=sum(likes),
                top_video_title=top.title,
            ),
            heat_score,
        )

    results = await asyncio.gather(*(one(rid) for rid in rids))
    pairs = [r for r in results if r is not None]

    if save_history:
        for stats, heat_score in pairs:
            category_service.save_snapshot(
                db,
                stats.rid,
                video_count=stats.video_count,
                total_plays=stats.total_plays,
                avg_plays=stats.avg_plays,
                max_plays=stats.max_plays,
                total_likes=stats.total_likes,
                heat_score=heat_score,
            )

    return sorted((s for s, _ in pairs), key=lambda s: s.total_plays, reverse=True)
