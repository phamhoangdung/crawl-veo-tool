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


def _parse_published_at(raw: str | int | None) -> str | None:
    """Chuẩn hoá ngày đăng về ISO 8601 UTC — 2 nguồn trả 2 định dạng khác nhau:
    ranking trả chuỗi giờ Bắc Kinh 'YYYY-MM-DD HH:MM' (không có offset trong
    chuỗi, verify qua đối chiếu với `pubdate` unix timestamp của cùng 1 video ở
    endpoint `x/web-interface/view` — chênh đúng 8 tiếng), search trả unix
    timestamp UTC thuần (`pubdate`).
    """
    if raw is None:
        return None
    try:
        if isinstance(raw, int):
            return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M")  # noqa: DTZ007 — gán tz ngay dòng dưới
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, OSError):
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
    mid = item.get("mid")
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
        # Field mapping verify bằng request thật tới x/web-interface/view
        # (2026-09-16): review=bình luận, video_review=danmaku, xem docstring
        # TrendingVideoRead.
        comment_count=item.get("review"),
        danmaku_count=item.get("video_review"),
        coin_count=item.get("coins"),
        heat_score=item.get("pts"),
        published_at=_parse_published_at(item.get("create")),
        # Phase 22: `mid` phẳng ở top-level item (khác `_from_popular_item`
        # phải đào vào `owner.mid`).
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
        # search không trả `coins`/`pts` — None, không giả định bằng 0 (0 sẽ
        # trông như "có dữ liệu nhưng bằng 0", sai với thực tế "không có").
        coin_count=None,
        heat_score=None,
        published_at=_parse_published_at(item.get("pubdate")),
        channel_id=str(mid) if mid else None,
    )


def _from_popular_item(item: dict) -> TrendingVideoRead:
    # `popular` trả `stat` đầy đủ như endpoint chi tiết video thật (view/like/
    # danmaku/reply/coin) — verify bằng request thật 2026-09-16, khác hẳn
    # `ranking/region` phải suy luận field `review`/`video_review` mập mờ.
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
        # Không có pts/xếp hạng tính điểm — đây là danh sách phổ biến biên tập
        # của Bilibili, không phải bảng xếp hạng theo thuật toán như ranking.
        heat_score=None,
        published_at=_parse_published_at(item.get("pubdate")),
        # Phase 22: `owner.mid` (khác `_from_ranking_item`/`_from_search_item`
        # có `mid` phẳng ở top-level).
        channel_id=str(mid) if mid else None,
    )


def _from_space_video_item(item: dict) -> TrendingVideoRead:
    """`x/space/wbi/arc/search` (`data.list.vlist[]`) — Phase 22.

    **CHƯA verify field thật**: đo thật 2026-09-22 với 10 kênh phổ biến, cả
    10/10 request đều bị risk-control chặn (412/-352) trước khi có được 1
    response thật để đối chiếu — xem `channel_service.ChannelVideosResult`.
    Field mapping dưới đây dựa theo tài liệu cộng đồng
    (SocialSisterYi/bilibili-API-collect) — `length` (không phải `duration`
    như các endpoint khác) là tên field ĐÃ ĐƯỢC TÀI LIỆU XÁC NHẬN khác biệt.
    Ai verify được bằng response thật (có cookie/may mắn né được risk-control)
    xin đối chiếu lại converter này.
    """
    mid = item.get("mid")
    return TrendingVideoRead(
        bvid=item.get("bvid", ""),
        title=item.get("title", ""),
        author_name=item.get("author"),
        play_count=item.get("play"),
        like_count=None,  # vlist không có field lượt thích theo tài liệu cộng đồng
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
    """Gắn `video_id`/`already_in_library` bằng 1 query duy nhất cho cả danh
    sách (không N+1) — Phase 20: màn Khám phá cần biết video nào đã tải để
    hiện thanh %/badge ngay trên thẻ, không phải đoán qua bvid ở frontend.
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
    """Phase 22: ghi nhận kênh vừa thấy (`upsert_seen_batch`) + gắn
    `channel_is_followed` — cùng 1 query duy nhất cho cả danh sách, cùng
    pattern chống N+1 với `_attach_library_status`.
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
    """Danh sách phổ biến TOÀN TRANG Bilibili (không giới hạn 1 chuyên mục) —
    dùng cho tab "Tất cả". Có phân trang thật (khác `ranking/region`), nên
    không cần fallback sang search như `get_category_page`.
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
    """Tìm kiếm tự do theo từ khoá bất kỳ — không giới hạn trong 1 chuyên mục.
    Dùng chung `_from_search_item` với `get_category_page` (cùng nguồn dữ liệu,
    cùng hạn chế: không có pts/coin, xem docstring `TrendingVideoRead`).

    `translate_keyword` tái dùng đúng logic dịch từ khoá của luồng crawl
    (`crawl_service.translate_keyword_to_chinese`) — trước đây trang Trending
    không có tuỳ chọn này dù trang Crawl có, khiến search tiếng Việt gần như
    luôn ra 0 kết quả trên Bilibili."""
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
    """Video liên quan (Phase 22) — endpoint công khai `archive/related`, cùng
    hình dạng dữ liệu với `popular` (owner/stat/pic/duration), dùng lại
    `_from_popular_item`. Không phân trang (Bilibili trả trọn 1 lần, tối đa
    ~40 video) — `has_more` luôn `False`.
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
    """Video khác trong 1 kênh (Phase 22) — `degraded=True` khi bị
    risk-control (xem `channel_service.list_channel_videos`), KHÔNG raise lên
    router: 1 API phụ lỗi không được làm vỡ cả popup xem trước."""
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
    """Trang đầu lấy từ bảng xếp hạng (đúng nghĩa 'đang hot'), các trang sau
    lấy từ search theo tên tiếng Trung của category vì ranking không phân trang.
    """
    category = db.get(Category, rid)

    async with BilibiliClient() as client:
        if page <= _RANKING_PAGE:
            items = await client.get_ranking(rid=rid, day=day)
            videos = [_from_ranking_item(item) for item in items]
            _attach_library_status(db, videos)
            _attach_channel_info(db, videos)
            # Chỉ hứa còn trang sau khi biết search bằng từ khoá nào.
            return TrendingPageRead(
                videos=videos, page=page, has_more=category is not None, source="ranking"
            )

        if category is None or not category.name_zh:
            return TrendingPageRead(videos=[], page=page, has_more=False, source="search")

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

    _attach_library_status(db, videos)
    _attach_channel_info(db, videos)
    return TrendingPageRead(videos=videos, page=page, has_more=bool(videos), source="search")


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
        pts_values = [v.heat_score or 0 for v in videos]
        # Video đại diện chọn theo `pts` (điểm xếp hạng thật), không phải view
        # thô — 1 video view khủng nhưng pts thấp (cũ/ít tương tác) không phải
        # thứ đang khiến chuyên mục này "hot" theo đúng thuật toán của Bilibili.
        top = max(videos, key=lambda v: v.heat_score or 0)
        avg_plays = sum(plays) // len(plays)
        total_pts = int(sum(pts_values))
        # pts trung bình trên mỗi ngày xếp hạng — cho phép so sánh giữa các
        # khung thời gian khác nhau (day=1 vs day=3).
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


# Phase 20 — biểu đồ "Chủ đề đang được quan tâm" chuyển sang trang phụ
# (Báo cáo xu hướng), không còn nằm chắn đường ở màn Khám phá chính. Trước đây
# lịch sử CHỈ dày lên khi người dùng tự mở trang (`GET /stats` gọi
# `get_categories_stats(save_history=True)`) — chuyển sang trang phụ mà không
# đổi cách ghi thì dữ liệu càng thưa hơn (ít người ghé trang phụ hơn trang
# chính). Vòng lặp nền này ghi đều đặn bất kể có ai mở trang hay không.
SNAPSHOT_INTERVAL_SECONDS = 4 * 3600


async def run_periodic_snapshot(
    session_factory, interval_seconds: float = SNAPSHOT_INTERVAL_SECONDS
) -> None:
    """Vòng lặp ghi snapshot các chuyên mục đang theo dõi — chạy nền trong
    chính process backend, cùng pattern với
    `storage_cleanup_service.run_periodic_cleanup()` (xem docstring ở đó về lý
    do không dùng cron ngoài/APScheduler: app đóng gói desktop không có
    crontab để cài).

    Ghi ngay lần đầu rồi mới ngủ — máy cá nhân bật/tắt liên tục, đợi đủ
    `interval_seconds` mới ghi lần đầu thì có khi cả ngày không ghi được gì.
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
            # 1 chu kỳ lỗi (Bilibili tạm trục trặc, mất mạng...) không được
            # phép giết hẳn vòng lặp — thử lại ở chu kỳ sau.
            logger.exception("Ghi snapshot chuyên mục định kỳ thất bại, sẽ thử lại ở chu kỳ sau")
        await asyncio.sleep(interval_seconds)
