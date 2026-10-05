from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CategoryRead(BaseModel):
    rid: int
    name: str
    # The Chinese name serves both for display and as the search keyword when scrolling past
    # the 11 videos that ranking/region returns.
    name_zh: str | None = None
    group: str | None = None
    is_followed: bool = False


class FollowCategoriesRequest(BaseModel):
    rids: list[int]


class SnapshotPoint(BaseModel):
    """1 point on the trend line of one category."""

    rid: int
    captured_at: datetime
    total_plays: int
    avg_plays: int
    # Total `pts` score — the REAL ranking score Bilibili computes itself (aggregating
    # views+likes+coins+shares+saves+time), verified with a real request 2026-09-16:
    # descending pts order matches the returned ranking exactly, even when raw views
    # do not (a video with more views but newer/less engagement still ranks lower). More
    # reliable than `total_plays` for measuring the "real hotness" of a category.
    total_pts: int
    heat_score: float


class CategoryHistoryRead(BaseModel):
    rid: int
    name: str
    points: list[SnapshotPoint]


class TrendingVideoRead(BaseModel):
    bvid: str
    title: str
    author_name: str | None = None
    play_count: int | None = None
    like_count: int | None = None
    duration_seconds: int | None = None
    cover_url: str | None = None
    # The 4 fields below had their field mapping verified with a real request to `x/web-interface/view`
    # (2026-09-16) — Bilibili's raw field names (`review`/`video_review`) are not
    # self-explanatory; only by comparing with `stat.reply`/`stat.danmaku` was the meaning certain.
    comment_count: int | None = None  # comments (ranking/search: `review`)
    danmaku_count: int | None = None  # scrolling comments (ranking: `video_review`; search: `danmaku`)
    coin_count: int | None = None  # coins given — only ranking has it, search does not return this field
    # Bilibili's real ranking score (`pts`) — only ranking has it (search does not
    # return this field). None means this video came from search, not from a real
    # ranking — the frontend uses it to tell them apart; not every video is "hot".
    heat_score: float | None = None
    # Phase 20: merged Discovery screen — lets the Trending grid know this video is already in the
    # library (real id in the DB) to show download status/"My videos" link
    # right on the card, without guessing via bvid. None = never downloaded.
    video_id: int | None = None
    already_in_library: bool = False
    published_at: str | None = None  # ISO 8601 UTC
    # Phase 22: real channel id (Bilibili: str(mid)) — present in popular/search/ranking
    # under field mid/owner.mid (see trending_service._from_*_item). None if the
    # API does not return it (rare).
    channel_id: str | None = None
    channel_is_followed: bool = False


class TrendingPageRead(BaseModel):
    """1 page of videos. `has_more` tells the frontend whether there is more to scroll."""

    videos: list[TrendingVideoRead]
    page: int
    has_more: bool
    # "ranking" = the real per-category ranking (truly "trending");
    # "popular" = the site-wide popular list of Bilibili ("All" tab, with real
    # pagination, not tied to one category); "search" = search by keyword (the category
    # name when scrolling past page 1, or the free search box) — broader but
    # mixed with unrelated videos, NOT "trending". The frontend displays
    # each source differently, not concatenated as one list.
    source: Literal["ranking", "popular", "search"] = "ranking"
    # Only meaningful when source="search" and the caller enabled translate_keyword — reports that
    # keyword translation failed (it already fell back to verbatim search) so the UI can warn, like
    # `translation_failed` of the crawl job (see crawl_service).
    translation_failed: bool = False
    # Phase 22: True when the data source was blocked by Bilibili risk control (only
    # applies to the "other videos in the channel" page — see channel_service.list_channel_videos).
    # Very different from a "truly empty list" — the frontend must show a degraded-state
    # message, not "this channel has no videos".
    degraded: bool = False


class ChannelRead(BaseModel):
    platform: str
    channel_id: str
    name: str
    avatar_url: str | None = None
    is_followed: bool = False


class SetChannelFollowedRequest(BaseModel):
    followed: bool


class CategoryStatsRead(BaseModel):
    """Stats of 1 category, used to draw a chart comparing the level of interest."""

    rid: int
    name: str
    group: str | None = None
    video_count: int
    total_plays: int
    avg_plays: int
    max_plays: int
    total_likes: int
    # Total `pts` (Bilibili's real ranking score) of the videos currently ranked in the
    # category — the main metric to compare "hotness" between categories,
    # replacing `total_plays` (easily skewed by one old video with huge views but
    # that nobody really cares about any more, see the `SnapshotPoint.total_pts` docstring).
    total_pts: int
    top_video_title: str | None = None
