import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.adapters.bilibili.client import BilibiliClient
from app.models.category import Category
from app.models.channel import Channel
from app.models.job import Platform
from app.models.video import Video
from app.schemas.trending import (
    CategoryStatsRead,
    TrendingPageRead,
    TrendingVideoRead,
)
from app.services import category_service, channel_service, crawl_service

logger = logging.getLogger(__name__)

# ranking/region returns everything at once (~11 videos, no pagination). To keep scrolling,
# switch to search by the category's Chinese name — only search has pagination.
_RANKING_PAGE = 1


def _parse_duration_to_seconds(raw: str | int | None) -> int | None:
    """Bilibili returns duration as 'mm:ss' (search) or plain seconds (ranking)."""
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


def _parse_published_at(raw: str | int | None) -> str | None:
    """Normalize the publish date to ISO 8601 UTC — the 2 sources return 2 formats:
    ranking returns a Beijing time string 'YYYY-MM-DD HH:MM' (with no offset in the
    string, verified by comparing with the unix timestamp `pubdate` of the same video at the
    endpoint `x/web-interface/view` — exactly 8 hours apart), search returns a pure UTC unix
    timestamp (`pubdate`).
    """
    if raw is None:
        return None
    try:
        if isinstance(raw, int):
            return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M")  # noqa: DTZ007 — tz is assigned on the next line
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, OSError):
        return None


def _normalize_cover_url(raw: str | None) -> str | None:
    """Search returns the image as '//i2.hdslb.com/...' (missing the scheme); ranking returns http."""
    if not raw:
        return None
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.startswith("http://"):
        return f"https://{raw[len('http://'):]}"
    return raw


def _from_ranking_item(item: dict) -> TrendingVideoRead:
    mid = item.get("mid")
    return TrendingVideoRead(
        bvid=item["bvid"],
        title=item.get("title", ""),
        author_name=item.get("author"),
        play_count=item.get("play"),
        # ranking/region does not return likes; `favorites` (video saves) is the closest
        # engagement metric available.
        like_count=item.get("favorites"),
        duration_seconds=_parse_duration_to_seconds(item.get("duration")),
        cover_url=_normalize_cover_url(item.get("pic")),
        # Field mapping verified with a real request to x/web-interface/view
        # (2026-09-16): review=comments, video_review=danmaku, see the
        # TrendingVideoRead.
        comment_count=item.get("review"),
        danmaku_count=item.get("video_review"),
        coin_count=item.get("coins"),
        heat_score=item.get("pts"),
        published_at=_parse_published_at(item.get("create")),
        # Phase 22: `mid` is flat at the top level of the item (unlike `_from_popular_item`,
        # which must dig into `owner.mid`).
        channel_id=str(mid) if mid else None,
    )


def _from_search_item(item: dict) -> TrendingVideoRead:
    mid = item.get("mid")
    return TrendingVideoRead(
        bvid=item["bvid"],
        title=item.get("title", ""),
        author_name=item.get("author"),
        play_count=item.get("play"),
        like_count=item.get("favorites"),
        duration_seconds=_parse_duration_to_seconds(item.get("duration")),
        cover_url=_normalize_cover_url(item.get("pic")),
        comment_count=item.get("review"),
        danmaku_count=item.get("danmaku"),
        # search returns no `coins`/`pts` — None, not assumed to be 0 (0 would
        # look like "there is data but it is zero", wrong versus the reality of "there is none").
        coin_count=None,
        heat_score=None,
        published_at=_parse_published_at(item.get("pubdate")),
        channel_id=str(mid) if mid else None,
    )


def _from_popular_item(item: dict) -> TrendingVideoRead:
    # `popular` returns the full `stat` like the real video detail endpoint (view/like/
    # danmaku/reply/coin) — verified with a real request 2026-09-16, unlike
    # `ranking/region` where the ambiguous `review`/`video_review` fields must be inferred.
    stat = item.get("stat") or {}
    owner = item.get("owner") or {}
    mid = owner.get("mid")
    return TrendingVideoRead(
        bvid=item["bvid"],
        title=item.get("title", ""),
        author_name=owner.get("name"),
        play_count=stat.get("view"),
        like_count=stat.get("like"),
        duration_seconds=_parse_duration_to_seconds(item.get("duration")),
        cover_url=_normalize_cover_url(item.get("pic")),
        comment_count=stat.get("reply"),
        danmaku_count=stat.get("danmaku"),
        coin_count=stat.get("coin"),
        # No pts/score ranking — this is Bilibili's editorially curated popular list,
        # not an algorithmic ranking like ranking.
        heat_score=None,
        published_at=_parse_published_at(item.get("pubdate")),
        # Phase 22: `owner.mid` (unlike `_from_ranking_item`/`_from_search_item`
        # which have a flat `mid` at the top level).
        channel_id=str(mid) if mid else None,
    )


def _from_space_video_item(item: dict) -> TrendingVideoRead:
    """`x/space/wbi/arc/search` (`data.list.vlist[]`) — Phase 22.

    **Real fields NOT verified yet**: measured 2026-09-22 with 10 popular channels, all
    10/10 requests were blocked by risk control (412/-352) before a single
    real response could be obtained to compare against — see `channel_service.ChannelVideosResult`.
    The field mapping below follows community docs
    (SocialSisterYi/bilibili-API-collect) — `length` (not `duration`
    like other endpoints) is a field name the docs CONFIRM as different.
    Whoever can verify with a real response (with a cookie, or by luckily dodging risk control)
    please re-check this converter.
    """
    mid = item.get("mid")
    return TrendingVideoRead(
        bvid=item.get("bvid", ""),
        title=item.get("title", ""),
        author_name=item.get("author"),
        play_count=item.get("play"),
        like_count=None,  # vlist has no likes field according to community docs
        duration_seconds=_parse_duration_to_seconds(item.get("length")),
        cover_url=_normalize_cover_url(item.get("pic")),
        comment_count=item.get("comment"),
        danmaku_count=None,
        coin_count=None,
        heat_score=None,
        published_at=_parse_published_at(item.get("created")),
        channel_id=str(mid) if mid else None,
    )


def _attach_library_status(db: Session, videos: list[TrendingVideoRead]) -> None:
    """Attach `video_id`/`already_in_library` with a single query for the whole
    list (no N+1) — Phase 20: the Discovery screen needs to know which videos are downloaded to
    show the progress bar/badge right on the card, without guessing via bvid in the frontend.
    """
    if not videos:
        return
    bvids = [v.bvid for v in videos]
    rows = db.query(Video.platform_video_id, Video.id).filter(
        Video.platform == Platform.BILIBILI,
        Video.platform_video_id.in_(bvids),
    ).all()
    by_bvid = {row[0]: row[1] for row in rows}
    for v in videos:
        video_id = by_bvid.get(v.bvid)
        if video_id is not None:
            v.video_id = video_id
            v.already_in_library = True


def _attach_channel_info(db: Session, videos: list[TrendingVideoRead]) -> None:
    """Phase 22: record the channels just seen (`upsert_seen_batch`) + attach
    `channel_is_followed` — the same single query for the whole list, the same
    N+1-avoidance pattern as `_attach_library_status`.
    """
    channel_ids = [v.channel_id for v in videos if v.channel_id]
    if not channel_ids:
        return

    channel_service.upsert_seen_batch(
        db,
        Platform.BILIBILI,
        [(v.channel_id, v.author_name or "") for v in videos if v.channel_id],
    )

    followed_ids = {
        row[0]
        for row in db.query(Channel.channel_id)
        .filter(
            Channel.platform == Platform.BILIBILI,
            Channel.channel_id.in_(channel_ids),
            Channel.is_followed.is_(True),
        )
        .all()
    }
    for v in videos:
        if v.channel_id in followed_ids:
            v.channel_is_followed = True


async def get_bilibili_popular_page(
    db: Session, page: int = 1, page_size: int = 20
) -> TrendingPageRead:
    """SITE-WIDE popular list of Bilibili (not limited to 1 category) —
    used for the "All" tab. Has real pagination (unlike `ranking/region`), so
    no fallback to search is needed like `get_category_page`.
    """
    async with BilibiliClient() as client:
        items = await client.get_popular(page=page, page_size=page_size)
    videos = [_from_popular_item(item) for item in items]
    _attach_library_status(db, videos)
    _attach_channel_info(db, videos)
    return TrendingPageRead(videos=videos, page=page, has_more=bool(videos), source="popular")


async def search_bilibili(
    db: Session,
    user_id: int,
    keyword: str,
    *,
    page: int = 1,
    translate_keyword: bool = False,
) -> TrendingPageRead:
    """Free search by any keyword — not limited to 1 category.
    Shares `_from_search_item` with `get_category_page` (same data source,
    same limits: no pts/coin, see the `TrendingVideoRead` docstring).

    `translate_keyword` reuses exactly the keyword translation logic of the crawl flow
    (`crawl_service.translate_keyword_to_chinese`) — previously the Trending page
    lacked this option though the Crawl page had it, so Vietnamese search almost
    always returned 0 results on Bilibili."""
    translation_failed = False
    search_keyword = keyword
    if translate_keyword:
        search_keyword, translated_ok = await crawl_service.translate_keyword_to_chinese(
            db, user_id, keyword
        )
        translation_failed = not translated_ok

    async with BilibiliClient() as client:
        results = await client.search_videos(search_keyword, page=page)

    seen: set[str] = set()
    videos: list[TrendingVideoRead] = []
    for item in results:
        bvid = item.get("bvid")
        if not bvid or bvid in seen:
            continue
        seen.add(bvid)
        videos.append(_from_search_item(item))

    _attach_library_status(db, videos)
    _attach_channel_info(db, videos)
    return TrendingPageRead(
        videos=videos,
        page=page,
        has_more=bool(videos),
        source="search",
        translation_failed=translation_failed,
    )


async def get_bilibili_ranking(rid: int, day: int = 3) -> list[TrendingVideoRead]:
    async with BilibiliClient() as client:
        items = await client.get_ranking(rid=rid, day=day)
    return [_from_ranking_item(item) for item in items]


async def get_related(db: Session, bvid: str) -> TrendingPageRead:
    """Related videos (Phase 22) — public endpoint `archive/related`, the same
    data shape as `popular` (owner/stat/pic/duration), reusing
    `_from_popular_item`. No pagination (Bilibili returns everything at once, at most
    ~40 videos) — `has_more` is always `False`.
    """
    async with BilibiliClient() as client:
        items = await client.get_related(bvid)
    videos = [_from_popular_item(item) for item in items]
    _attach_library_status(db, videos)
    _attach_channel_info(db, videos)
    return TrendingPageRead(videos=videos, page=1, has_more=False, source="popular")


async def get_channel_videos(
    db: Session, mid: str, page: int = 1, page_size: int = 25
) -> TrendingPageRead:
    """Other videos of 1 channel (Phase 22) — `degraded=True` when hit by
    risk control (see `channel_service.list_channel_videos`), does NOT raise up to the
    router: 1 failing auxiliary API must not break the whole preview popup."""
    result = await channel_service.list_channel_videos(mid, page=page, page_size=page_size)
    videos = [_from_space_video_item(item) for item in result.videos]
    _attach_library_status(db, videos)
    _attach_channel_info(db, videos)
    return TrendingPageRead(
        videos=videos,
        page=page,
        has_more=bool(videos) and not result.degraded,
        source="popular",
        degraded=result.degraded,
    )


async def get_category_page(
    db: Session, rid: int, page: int = 1, day: int = 3
) -> TrendingPageRead:
    """The first page comes from the ranking (truly "hot"), later pages
    come from search by the category's Chinese name because ranking has no pagination.
    """
    category = db.get(Category, rid)

    async with BilibiliClient() as client:
        if page <= _RANKING_PAGE:
            items = await client.get_ranking(rid=rid, day=day)
            videos = [_from_ranking_item(item) for item in items]
            _attach_library_status(db, videos)
            _attach_channel_info(db, videos)
            # Only promise a next page once we know which keyword the search uses.
            return TrendingPageRead(
                videos=videos, page=page, has_more=category is not None, source="ranking"
            )

        if category is None or not category.name_zh:
            return TrendingPageRead(videos=[], page=page, has_more=False, source="search")

        # Search page 1 duplicates the ranking content so start from page 2.
        results = await client.search_videos(category.name_zh, page=page)

    seen: set[str] = set()
    videos: list[TrendingVideoRead] = []
    for item in results:
        bvid = item.get("bvid")
        if not bvid or bvid in seen:
            continue
        seen.add(bvid)
        videos.append(_from_search_item(item))

    _attach_library_status(db, videos)
    _attach_channel_info(db, videos)
    return TrendingPageRead(videos=videos, page=page, has_more=bool(videos), source="search")


async def get_categories_stats(
    db: Session, rids: list[int], day: int = 3, save_history: bool = True
) -> list[CategoryStatsRead]:
    """Stats of each category to draw a chart, also recording 1 point into history.

    Called in parallel because each category is a separate request; a failing category is skipped
    instead of spoiling the whole chart.
    """

    async def one(rid: int) -> tuple[CategoryStatsRead, float] | None:
        category = db.get(Category, rid)
        if category is None:
            return None
        try:
            videos = await get_bilibili_ranking(rid=rid, day=day)
        except Exception as exc:  # noqa: BLE001 — 1 failing category must not block the whole chart
            logger.warning("Lấy thống kê chuyên mục %s thất bại: %s", rid, exc)
            return None
        if not videos:
            return None

        plays = [v.play_count or 0 for v in videos]
        likes = [v.like_count or 0 for v in videos]
        pts_values = [v.heat_score or 0 for v in videos]
        # The representative video is chosen by `pts` (the real ranking score), not raw
        # views — a video with huge views but low pts (old/low engagement) is not
        # what makes this category "hot" by Bilibili's own algorithm.
        top = max(videos, key=lambda v: v.heat_score or 0)
        avg_plays = sum(plays) // len(plays)
        total_pts = int(sum(pts_values))
        # Average pts per ranking day — allows comparing between different
        # time windows (day=1 vs day=3).
        heat_score = (total_pts / len(pts_values)) / max(day, 1)

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
                total_pts=total_pts,
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
                total_pts=stats.total_pts,
                heat_score=heat_score,
            )

    return sorted((s for s, _ in pairs), key=lambda s: s.total_pts, reverse=True)


# Phase 20 — the "Topics of interest" chart moved to a secondary page
# (Trend report), no longer blocking the way on the main Discovery screen. Previously
# history ONLY grew when the user opened the page themselves (`GET /stats` called
# `get_categories_stats(save_history=True)`) — moving to a secondary page without
# changing how it is recorded would make the data even sparser (fewer people visit the secondary page than
# the main one). This background loop records regularly whether or not anyone opens the page.
SNAPSHOT_INTERVAL_SECONDS = 4 * 3600


async def run_periodic_snapshot(
    session_factory, interval_seconds: float = SNAPSHOT_INTERVAL_SECONDS
) -> None:
    """Loop recording snapshots of the followed categories — runs in the background inside the
    backend process itself, same pattern as
    `storage_cleanup_service.run_periodic_cleanup()` (see the docstring there for the
    reason for not using external cron/APScheduler: the packaged desktop app has no
    crontab to install).

    Records right away the first time, then sleeps — a personal machine is turned on/off constantly, and waiting a full
    `interval_seconds` before the first write may mean nothing is recorded all day.
    """
    while True:
        try:
            with session_factory() as db:
                rids = category_service.get_followed_rids(db)
                if rids:
                    await get_categories_stats(db, rids, save_history=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            # 1 failing cycle (Bilibili hiccup, network loss...) must not
            # kill the loop for good — retry in the next cycle.
            logger.exception("Ghi snapshot chuyên mục định kỳ thất bại, sẽ thử lại ở chu kỳ sau")
        await asyncio.sleep(interval_seconds)
