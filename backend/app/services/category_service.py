"""Bilibili categories: discovered from the API, stored in the DB, with metrics accumulated over time.

Bilibili has no endpoint returning the taxonomy tree, but every video API carries
`tid`/`tname` — scanning those APIs is enough to build the real category list, and to
keep up automatically when Bilibili adds a new category.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.bilibili.client import BilibiliClient
from app.models.category import Category, CategorySnapshot
from app.services import translate_service

logger = logging.getLogger(__name__)

# Zone (tid) table → Vietnamese group, cross-checked against community docs
# (github.com/pskdje/bilibili-API-collect, docs/video/video_zone.md — a copy
# of the original repo SocialSisterYi/bilibili-API-collect before it was taken down) — the OFFICIAL
# source Bilibili uses to classify videos at upload time, not guessed from keywords.
#
# **Verified for real (2026-09-16):** checked against the existing DB — rid=138 (搞笑/Humor)
# was wrongly placed under "Entertainment" by the old heuristic (matching the keyword 搞笑),
# but per the real zone table 138 belongs to zone 生活 (Life, tid 160).
# The list below includes rids at BOTH the main-zone and sub-zone levels —
# the rid returned by ranking/region may be at either level depending on the category.
#
# Skip tids marked "已下线" (retired) in the source docs — an old tid may be
# reused by Bilibili for something else, keeping it is more likely to mislabel than leaving it empty.
_TID_GROUP: dict[int, str] = {
    # 动画 Anime/Animation
    1: "Anime", 24: "Anime", 25: "Anime", 47: "Anime", 257: "Anime",
    210: "Anime", 86: "Anime", 253: "Anime", 27: "Anime",
    # 番剧 Serialized animation
    13: "Phim hoạt hình", 51: "Phim hoạt hình", 152: "Phim hoạt hình",
    32: "Phim hoạt hình", 33: "Phim hoạt hình",
    # 国创 Chinese animation
    167: "Hoạt hình Trung Quốc", 153: "Hoạt hình Trung Quốc",
    168: "Hoạt hình Trung Quốc", 169: "Hoạt hình Trung Quốc",
    170: "Hoạt hình Trung Quốc", 195: "Hoạt hình Trung Quốc",
    # 音乐 Music
    3: "Âm nhạc", 28: "Âm nhạc", 29: "Âm nhạc", 31: "Âm nhạc", 59: "Âm nhạc",
    243: "Âm nhạc", 30: "Âm nhạc", 193: "Âm nhạc", 266: "Âm nhạc",
    265: "Âm nhạc", 267: "Âm nhạc", 244: "Âm nhạc", 130: "Âm nhạc",
    # 舞蹈 Dance
    129: "Vũ đạo", 20: "Vũ đạo", 198: "Vũ đạo", 199: "Vũ đạo", 200: "Vũ đạo",
    255: "Vũ đạo", 154: "Vũ đạo", 156: "Vũ đạo",
    # 游戏 Game
    4: "Game", 17: "Game", 171: "Game", 172: "Game", 65: "Game",
    173: "Game", 121: "Game", 136: "Game", 19: "Game",
    # 知识 Knowledge
    36: "Kiến thức", 201: "Kiến thức", 124: "Kiến thức", 228: "Kiến thức",
    207: "Kiến thức", 208: "Kiến thức", 209: "Kiến thức", 229: "Kiến thức",
    122: "Kiến thức",
    # 科技 Technology
    188: "Công nghệ", 95: "Công nghệ", 230: "Công nghệ", 231: "Công nghệ",
    232: "Công nghệ", 233: "Công nghệ",
    # 运动 Sports
    234: "Thể thao", 235: "Thể thao", 249: "Thể thao", 164: "Thể thao",
    236: "Thể thao", 237: "Thể thao", 238: "Thể thao",
    # 汽车 Vehicles
    223: "Xe cộ", 258: "Xe cộ", 227: "Xe cộ", 247: "Xe cộ", 245: "Xe cộ",
    246: "Xe cộ", 240: "Xe cộ", 248: "Xe cộ", 176: "Xe cộ",
    # 生活 Life — 138 (搞笑) belongs to this group, NOT Entertainment.
    160: "Đời sống", 138: "Đời sống", 254: "Đời sống", 250: "Đời sống",
    251: "Đời sống", 239: "Đời sống", 161: "Đời sống", 162: "Đời sống",
    21: "Đời sống",
    # 美食 Food
    211: "Ẩm thực", 76: "Ẩm thực", 212: "Ẩm thực", 213: "Ẩm thực",
    214: "Ẩm thực", 215: "Ẩm thực",
    # 动物圈 Animals
    217: "Động vật", 218: "Động vật", 219: "Động vật", 222: "Động vật",
    221: "Động vật", 220: "Động vật", 75: "Động vật",
    # 鬼畜 Remix (kuso)
    119: "Chế", 22: "Chế", 26: "Chế", 126: "Chế", 216: "Chế", 127: "Chế",
    # 时尚 Fashion
    155: "Thời trang", 157: "Thời trang", 252: "Thời trang",
    158: "Thời trang", 159: "Thời trang",
    # 资讯 News (note: Bilibili has no separate ranking for this zone)
    202: "Tin tức", 203: "Tin tức", 204: "Tin tức", 205: "Tin tức",
    206: "Tin tức",
    # 娱乐 Entertainment
    5: "Giải trí", 241: "Giải trí", 262: "Giải trí", 263: "Giải trí",
    242: "Giải trí", 264: "Giải trí", 137: "Giải trí", 71: "Giải trí",
    # 影视 Film & TV
    181: "Phim ảnh", 182: "Phim ảnh", 183: "Phim ảnh", 260: "Phim ảnh",
    259: "Phim ảnh", 184: "Phim ảnh", 85: "Phim ảnh", 256: "Phim ảnh",
    261: "Phim ảnh",
    # 纪录片 Documentaries
    177: "Phim tài liệu", 37: "Phim tài liệu", 178: "Phim tài liệu",
    179: "Phim tài liệu", 180: "Phim tài liệu",
    # 电影 Movies
    23: "Điện ảnh", 147: "Điện ảnh", 145: "Điện ảnh", 146: "Điện ảnh",
    83: "Điện ảnh",
    # 电视剧 TV series
    11: "Phim truyền hình", 185: "Phim truyền hình", 187: "Phim truyền hình",
}

# Fallback group hints by keyword — only used for tids NOT in the official
# table above (zones too new, community docs not updated yet).
_GROUP_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("美食", "吃"), "Ẩm thực"),
    (("动物", "喵", "汪", "宠"), "Động vật"),
    (("音乐", "乐", "唱", "演奏", "音"), "Âm nhạc"),
    (("游戏", "电竞", "网游", "单机"), "Game"),
    (("影视", "剧", "电影", "短片"), "Phim ảnh"),
    (("舞", "宅舞"), "Vũ đạo"),
    (("数码", "科技", "软件", "计算机"), "Công nghệ"),
    (("汽车", "车"), "Xe cộ"),
    (("健身", "篮球", "足球", "运动", "体育"), "Thể thao"),
    (("知识", "科普", "学习", "职场", "社科", "人文", "财经"), "Kiến thức"),
    (("生活", "日常", "出行", "家居", "亲子", "三农"), "Đời sống"),
    (("搞笑", "鬼畜", "综艺", "娱乐"), "Giải trí"),
    (("动画", "动漫", "手书", "MAD", "MMD"), "Anime"),
    (("时尚", "美妆", "穿搭", "颜值"), "Thời trang"),
    (("手工", "绘画", "设计", "创意"), "Sáng tạo"),
]


def _guess_group(rid: int, name_zh: str) -> str | None:
    if rid in _TID_GROUP:
        return _TID_GROUP[rid]
    for keywords, group in _GROUP_HINTS:
        if any(keyword in name_zh for keyword in keywords):
            return group
    return None


# Hardcoded default categories (rid, Chinese name, Vietnamese name, group) so the user
# has a selectable list on the first run without having to "Scan new categories".
# The first half are Bilibili's main zones (tid per `_TID_GROUP`), the second half are commonly used
# niches. The automatic scan still runs to catch new/renamed categories.
_DEFAULT_CATEGORIES: list[tuple[int, str, str, str]] = [
    (1, "动画", "Hoạt hình (Anime)", "Anime"),
    (3, "音乐", "Âm nhạc", "Âm nhạc"),
    (4, "游戏", "Game", "Game"),
    (5, "娱乐", "Giải trí", "Giải trí"),
    (11, "电视剧", "Phim truyền hình", "Phim truyền hình"),
    (13, "番剧", "Phim hoạt hình dài tập", "Phim hoạt hình"),
    (23, "电影", "Điện ảnh", "Điện ảnh"),
    (36, "知识", "Kiến thức", "Kiến thức"),
    (119, "鬼畜", "Chế (Kuso)", "Chế"),
    (129, "舞蹈", "Vũ đạo", "Vũ đạo"),
    (155, "时尚", "Thời trang", "Thời trang"),
    (160, "生活", "Đời sống", "Đời sống"),
    (168, "国创", "Hoạt hình Trung Quốc", "Hoạt hình Trung Quốc"),
    (177, "纪录片", "Phim tài liệu", "Phim tài liệu"),
    (181, "影视", "Phim ảnh", "Phim ảnh"),
    (188, "科技", "Công nghệ", "Công nghệ"),
    (217, "动物圈", "Động vật", "Động vật"),
    (223, "汽车", "Xe cộ", "Xe cộ"),
    (234, "运动", "Thể thao", "Thể thao"),
    (211, "美食记录", "Ẩm thực - Ghi chép", "Ẩm thực"),
    (76, "美食制作", "Ẩm thực - Nấu ăn", "Ẩm thực"),
    (21, "日常", "Đời sống thường ngày", "Đời sống"),
    (138, "搞笑", "Hài hước", "Đời sống"),
    (218, "喵星人", "Động vật - Mèo", "Động vật"),
    (219, "汪星人", "Động vật - Chó", "Động vật"),
]

# Following is only enabled on the first run (when the table is still empty).
_DEFAULT_FOLLOWED_RIDS = frozenset({211, 138, 21})


def ensure_default_categories(db: Session) -> int:
    """Insert the missing default categories, returning the number of rows added.

    Runs on every startup so an old DB (with a few categories already) is topped up too.
    Does not touch existing rows — keeps the name/group/`is_followed` the user chose.
    `is_followed` default only applies when the table is completely empty, so it does not
    re-enable a category the user unfollowed.
    """
    existing = {rid for (rid,) in db.query(Category.rid).all()}
    first_run = not existing
    added = 0
    for rid, name_zh, name_vi, group in _DEFAULT_CATEGORIES:
        if rid in existing:
            continue
        db.add(
            Category(
                rid=rid,
                name_zh=name_zh,
                name_vi=name_vi,
                group_name=group,
                is_followed=first_run and rid in _DEFAULT_FOLLOWED_RIDS,
            )
        )
        added += 1
    if added:
        db.commit()
    return added


def resync_known_groups(db: Session) -> int:
    """Reassign the group for EVERY category in the DB according to the latest `_TID_GROUP`.

    Unlike the loop in `discover_categories()` (which only touches categories just
    seen in this call), this function scans the whole table — necessary because a followed
    category may not be "hot" enough to appear again in the next scan,
    yet still needs its group fixed if `_TID_GROUP` was just updated (like the
    2026-09-16 fix: "Humor" rid=138 was wrongly guessed into "Entertainment").
    Returns the number of rows whose group changed.
    """
    changed = 0
    for category in db.query(Category).all():
        new_group = _guess_group(category.rid, category.name_zh)
        if new_group is not None and new_group != category.group_name:
            category.group_name = new_group
            changed += 1
    if changed:
        db.commit()
    return changed


async def discover_categories(db: Session) -> list[Category]:
    """Scan the APIs that carry tid/tname to update the category list.

    New categories are added; existing ones only get `last_seen_at` updated. Absent
    categories are not deleted — the API only returns what is hot, absence does not mean dead.
    """
    found: dict[int, str] = {}

    async with BilibiliClient() as client:
        for fetch in (
            lambda: client.get_popular(page=1, page_size=50),
            lambda: client.get_popular(page=2, page_size=50),
            client.get_online_list,
        ):
            try:
                items = await fetch()
            except Exception as exc:  # noqa: BLE001 — 1 failing source must not block the whole scan
                logger.warning("Quét chuyên mục thất bại ở 1 nguồn: %s", exc)
                continue
            for item in items:
                tid, tname = item.get("tid"), item.get("tname")
                if isinstance(tid, int) and tname:
                    found.setdefault(tid, tname)

    now = datetime.now(timezone.utc)
    created: list[Category] = []
    for rid, name_zh in found.items():
        category = db.get(Category, rid)
        if category is None:
            category = Category(
                rid=rid,
                name_zh=name_zh,
                group_name=_guess_group(rid, name_zh),
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(category)
            created.append(category)
        else:
            category.name_zh = name_zh
            category.last_seen_at = now

    db.commit()
    resync_known_groups(db)
    if created:
        logger.info("Phát hiện %d chuyên mục mới", len(created))
    return created


def count_pending_translations(db: Session) -> int:
    """Number of categories without a Vietnamese name — used to decide whether to run
    the background translation again (saves a spare DB query when there is nothing to translate)."""
    return db.query(Category).filter(Category.name_vi.is_(None)).count()


async def translate_missing_names(db: Session, user_id: int, limit: int = 100) -> int:
    """Translate category names that lack Vietnamese. Returns the number of entries translated.

    Translation results are cached durably in the `translation_cache` table (keyed by the hash of the
    text content, see `translate_service`) — categories with the same name or calling this function
    many times cost no extra real translation API calls, matching the intent "only translate when there is
    really a new topic". This function is called from `BackgroundTasks` (see
    `app/api/trending.py`) so it need not be limited low to avoid blocking requests —
    limit is now only a safe ceiling (so one huge scan does not run forever).
    """
    pending = (
        db.query(Category)
        .filter(Category.name_vi.is_(None))
        .order_by(Category.rid)
        .limit(limit)
        .all()
    )
    if not pending:
        return 0

    translated = 0
    for category in pending:
        try:
            name_vi, _from_cache = await translate_service.translate_cached(
                db, user_id, category.name_zh, source_lang="zh", target_lang="vi"
            )
        except Exception as exc:  # noqa: BLE001 — if translation fails leave it as is, retry next time
            logger.warning("Dịch tên chuyên mục %s thất bại: %s", category.rid, exc)
            continue
        name_vi = name_vi.strip()
        if name_vi:
            category.name_vi = name_vi
            translated += 1

    db.commit()
    return translated


def set_followed(db: Session, rids: list[int]) -> None:
    """Set the list of followed categories (replacing the whole previous selection)."""
    db.query(Category).filter(Category.is_followed.is_(True)).update(
        {Category.is_followed: False}
    )
    if rids:
        db.query(Category).filter(Category.rid.in_(rids)).update(
            {Category.is_followed: True}, synchronize_session=False
        )
    db.commit()


def get_followed_rids(db: Session) -> list[int]:
    rows = db.execute(
        select(Category.rid).where(Category.is_followed.is_(True)).order_by(Category.rid)
    ).all()
    return [row[0] for row in rows]


def save_snapshot(
    db: Session,
    rid: int,
    *,
    video_count: int,
    total_plays: int,
    avg_plays: int,
    max_plays: int,
    total_likes: int,
    total_pts: int,
    heat_score: float,
    min_interval_minutes: int = 30,
) -> CategorySnapshot | None:
    """Record 1 metrics point, skipping if one was just recorded recently.

    Reopening the Trending page a few times within a minute should not create a series of points
    that are too close together — the chart line would get dense without adding information.
    """
    latest = db.execute(
        select(func.max(CategorySnapshot.captured_at)).where(CategorySnapshot.rid == rid)
    ).scalar()

    now = datetime.now(timezone.utc)
    if latest is not None:
        # SQLite returns naive datetimes; reassign UTC so the comparison does not raise TypeError.
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        if now - latest < timedelta(minutes=min_interval_minutes):
            return None

    snapshot = CategorySnapshot(
        rid=rid,
        captured_at=now,
        video_count=video_count,
        total_plays=total_plays,
        avg_plays=avg_plays,
        max_plays=max_plays,
        total_likes=total_likes,
        total_pts=total_pts,
        heat_score=heat_score,
    )
    db.add(snapshot)
    db.commit()
    return snapshot


def get_history(db: Session, rids: list[int], days: int = 30) -> list[CategorySnapshot]:
    if not rids:
        return []
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return (
        db.query(CategorySnapshot)
        .filter(CategorySnapshot.rid.in_(rids), CategorySnapshot.captured_at >= since)
        .order_by(CategorySnapshot.captured_at)
        .all()
    )
