"""Test bảng phân khu chính chủ `_TID_GROUP` (Phase Trending cải thiện,
2026-09-16) — thay cho việc đoán nhóm bằng từ khoá tiếng Trung.

Bug cụ thể đã verify trong DB thật trước khi sửa: rid=138 (搞笑/Hài hước) bị
heuristic cũ xếp vào "Giải trí" (khớp từ khoá 搞笑 trong `_GROUP_HINTS`), nhưng
theo bảng phân khu thật của Bilibili (đối chiếu tài liệu cộng đồng
github.com/pskdje/bilibili-API-collect) thì 138 thuộc phân khu 生活 (Đời sống).
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.category import Category
from app.services import category_service


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


class TestGuessGroup:
    def test_known_tid_uses_canonical_table_not_keyword_guess(self) -> None:
        """138 (搞笑) chứa từ khoá "搞笑" khớp heuristic cũ ra "Giải trí", nhưng
        bảng chính thức phải thắng — verify đúng nhóm thật (Đời sống)."""
        assert category_service._guess_group(138, "搞笑") == "Đời sống"

    def test_unknown_tid_falls_back_to_keyword_heuristic(self) -> None:
        """tid lạ (chưa có trong bảng chính thức, ví dụ phân khu Bilibili vừa
        thêm) vẫn phải đoán được bằng từ khoá — không được trả về None ngay."""
        assert category_service._guess_group(999999, "美食测试") == "Ẩm thực"

    def test_unknown_tid_and_no_keyword_match_returns_none(self) -> None:
        assert category_service._guess_group(999999, "完全陌生的名字") is None


class TestResyncKnownGroups:
    def test_fixes_stale_wrong_group_without_rediscovery(self, session_factory) -> None:
        """Mục đã lưu nhóm sai từ trước (do heuristic cũ) phải được sửa lại chỉ
        bằng cách gọi resync — không cần chuyên mục đó xuất hiện lại trong lần
        quét API mới (nó có thể không còn "hot" đủ để lọt vào popular/online)."""
        with session_factory() as db:
            db.add(Category(rid=138, name_zh="搞笑", group_name="Giải trí"))
            db.commit()

            changed = category_service.resync_known_groups(db)

            assert changed == 1
            assert db.get(Category, 138).group_name == "Đời sống"

    def test_already_correct_group_not_counted_as_changed(self, session_factory) -> None:
        with session_factory() as db:
            db.add(Category(rid=21, name_zh="日常", group_name="Đời sống"))
            db.commit()

            changed = category_service.resync_known_groups(db)

            assert changed == 0

    def test_unmapped_tid_keeps_existing_group_untouched(self, session_factory) -> None:
        """tid không có trong bảng chính thức lẫn không khớp từ khoá nào —
        đừng xoá mất nhóm cũ (có thể do người dùng/phiên trước đặt), giữ nguyên."""
        with session_factory() as db:
            db.add(Category(rid=999999, name_zh="完全陌生的名字", group_name="Khác cũ"))
            db.commit()

            changed = category_service.resync_known_groups(db)

            assert changed == 0
            assert db.get(Category, 999999).group_name == "Khác cũ"


class TestCountPendingTranslations:
    def test_counts_only_categories_without_name_vi(self, session_factory) -> None:
        with session_factory() as db:
            db.add(Category(rid=1, name_zh="a", name_vi="đã dịch"))
            db.add(Category(rid=2, name_zh="b", name_vi=None))
            db.add(Category(rid=3, name_zh="c", name_vi=None))
            db.commit()

            assert category_service.count_pending_translations(db) == 2


class TestTranslateMissingNames:
    """Verify wiring (dùng `translate_cached` — có cache bền, đúng ý "chỉ dịch
    khi có chủ đề mới" — thay vì `translate_text` thô như code cũ) bằng mock,
    không gọi API dịch thật (2026-09-16: Google free bị rate-limit lúc test
    thật do gọi dồn dập trong phiên — không phải lỗi code, xem Ghi chú phase)."""

    @pytest.mark.asyncio
    async def test_uses_cached_translation_helper_not_raw_translate(
        self, session_factory
    ) -> None:
        with session_factory() as db:
            db.add(Category(rid=1, name_zh="搞笑", name_vi=None))
            db.commit()

            with patch(
                "app.services.category_service.translate_service.translate_cached",
                new_callable=AsyncMock,
            ) as mock_translate:
                mock_translate.return_value = ("Hài hước", False)

                translated = await category_service.translate_missing_names(db, user_id=1)

            assert translated == 1
            mock_translate.assert_awaited_once_with(
                db, 1, "搞笑", source_lang="zh", target_lang="vi"
            )
            assert db.get(Category, 1).name_vi == "Hài hước"

    @pytest.mark.asyncio
    async def test_failed_translation_leaves_category_pending_for_retry(
        self, session_factory
    ) -> None:
        """Hết quota (Google rate-limit, hết key OpenAI...) không được crash cả
        lượt dịch — mục đó ở lại `name_vi=None` để lần sau (background task kế
        tiếp) tự thử lại, đúng ý "tự động, không cần bấm lại"."""
        with session_factory() as db:
            db.add(Category(rid=1, name_zh="搞笑", name_vi=None))
            db.commit()

            with patch(
                "app.services.category_service.translate_service.translate_cached",
                new_callable=AsyncMock,
            ) as mock_translate:
                mock_translate.side_effect = RuntimeError("hết quota")

                translated = await category_service.translate_missing_names(db, user_id=1)

            assert translated == 0
            assert db.get(Category, 1).name_vi is None

    @pytest.mark.asyncio
    async def test_no_pending_categories_returns_zero_without_calling_translate(
        self, session_factory
    ) -> None:
        with session_factory() as db:
            db.add(Category(rid=1, name_zh="a", name_vi="đã dịch"))
            db.commit()

            with patch(
                "app.services.category_service.translate_service.translate_cached",
                new_callable=AsyncMock,
            ) as mock_translate:
                translated = await category_service.translate_missing_names(db, user_id=1)

            assert translated == 0
            mock_translate.assert_not_awaited()
