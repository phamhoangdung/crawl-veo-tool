"""Chuyên mục Bilibili: phát hiện từ API, lưu DB, tích luỹ số liệu theo thời gian.

Bilibili không có endpoint trả cây phân loại, nhưng mọi API video đều kèm
`tid`/`tname` — quét các API đó là dựng được danh sách chuyên mục thật, và tự
bắt kịp khi Bilibili thêm mục mới.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.bilibili.client import BilibiliClient
from app.models.category import Category, CategorySnapshot
from app.services import translate_service

logger = logging.getLogger(__name__)

# Gợi ý nhóm cho chuyên mục mới, khớp theo từ khoá trong tên tiếng Trung.
# Không khớp thì để None — UI xếp vào "Khác", vẫn dùng được bình thường.
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


def _guess_group(name_zh: str) -> str | None:
    for keywords, group in _GROUP_HINTS:
        if any(keyword in name_zh for keyword in keywords):
            return group
    return None


async def discover_categories(db: Session) -> list[Category]:
    """Quét các API có kèm tid/tname để cập nhật danh sách chuyên mục.

    Chuyên mục mới được thêm; mục đã có chỉ cập nhật `last_seen_at`. Không xoá
    mục vắng mặt — API chỉ trả những gì đang hot, vắng không có nghĩa là đã chết.
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
            except Exception as exc:  # noqa: BLE001 — 1 nguồn lỗi không chặn cả việc quét
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
                group_name=_guess_group(name_zh),
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(category)
            created.append(category)
        else:
            category.name_zh = name_zh
            category.last_seen_at = now

    db.commit()
    if created:
        logger.info("Phát hiện %d chuyên mục mới", len(created))
    return created


async def translate_missing_names(db: Session, user_id: int, limit: int = 20) -> int:
    """Dịch tên chuyên mục chưa có tiếng Việt. Trả về số mục đã dịch.

    Dịch dần từng đợt để không bắt người dùng chờ hàng chục lần gọi API; mục
    chưa dịch vẫn dùng được (UI hiển thị tên tiếng Trung).
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
            name_vi = await translate_service.translate_text(
                db, user_id, category.name_zh, source_lang="zh", target_lang="vi"
            )
        except Exception as exc:  # noqa: BLE001 — dịch hỏng thì để nguyên, thử lại lần sau
            logger.warning("Dịch tên chuyên mục %s thất bại: %s", category.rid, exc)
            continue
        name_vi = name_vi.strip()
        if name_vi:
            category.name_vi = name_vi
            translated += 1

    db.commit()
    return translated


def set_followed(db: Session, rids: list[int]) -> None:
    """Đặt danh sách chuyên mục đang theo dõi (thay thế toàn bộ lựa chọn cũ)."""
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
    heat_score: float,
    min_interval_minutes: int = 30,
) -> CategorySnapshot | None:
    """Ghi 1 điểm số liệu, bỏ qua nếu vừa ghi gần đây.

    Mở lại trang Trending vài lần trong 1 phút không nên tạo ra chuỗi điểm sát
    nhau — đường biểu đồ sẽ dày đặc mà không thêm thông tin.
    """
    latest = db.execute(
        select(func.max(CategorySnapshot.captured_at)).where(CategorySnapshot.rid == rid)
    ).scalar()

    now = datetime.now(timezone.utc)
    if latest is not None:
        # SQLite trả datetime naive; gán lại UTC để so sánh không nổ TypeError.
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
