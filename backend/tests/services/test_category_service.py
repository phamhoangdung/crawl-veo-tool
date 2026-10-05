"""Test the official zone table `_TID_GROUP` (Trending improvement phase,
2026-09-16) — replacing guessing the group from Chinese keywords.

The specific bug verified in the real DB before the fix: rid=138 (搞笑/Humor) was put by the old
heuristic into "Entertainment" (matching the keyword 搞笑 in `_GROUP_HINTS`), but
per Bilibili's real zone table (cross-checked with community docs
github.com/pskdje/bilibili-API-collect) 138 belongs to zone 生活 (Life).
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
        """138 (搞笑) contains the keyword "搞笑" which matches the old heuristic into "Entertainment", but
        the official table must win — verify the right group (Life)."""
        assert category_service._guess_group(138, "搞笑") == "Đời sống"

    def test_unknown_tid_falls_back_to_keyword_heuristic(self) -> None:
        """An unknown tid (not in the official table, e.g. a zone Bilibili just
        added) must still be guessable by keyword — it must not return None right away."""
        assert category_service._guess_group(999999, "美食测试") == "Ẩm thực"

    def test_unknown_tid_and_no_keyword_match_returns_none(self) -> None:
        assert category_service._guess_group(999999, "完全陌生的名字") is None


class TestResyncKnownGroups:
    def test_fixes_stale_wrong_group_without_rediscovery(self, session_factory) -> None:
        """An entry saved with the wrong group earlier (by the old heuristic) must be fixed
        just by calling resync — without that category appearing again in a
        new API scan (it may no longer be "hot" enough to make it into popular/online)."""
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
        """A tid neither in the official table nor matching any keyword —
        do not wipe the old group (it may have been set by the user/an earlier session), keep it."""
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
    """Verify wiring (uses `translate_cached` — a durable cache, matching the intent "only translate
    when there is a new topic" — instead of the raw `translate_text` like the old code) with a mock,
    no real translation API calls (2026-09-16: free Google was rate-limited during the
    real test due to bursts of calls in one session — not a code bug, see the phase notes)."""

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
        """Out of quota (Google rate limit, out of OpenAI keys...) must not crash the whole
        translation pass — that entry stays at `name_vi=None` so next time (the next background
        task) it retries by itself, matching the intent "automatic, no need to click again"."""
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


class TestEnsureDefaultCategories:
    def test_first_run_seeds_all_defaults_and_follows_only_starter_set(
        self, session_factory
    ) -> None:
        with session_factory() as db:
            added = category_service.ensure_default_categories(db)
            assert added == len(category_service._DEFAULT_CATEGORIES)
            followed = {c.rid for c in db.query(Category).filter(Category.is_followed)}
            assert followed == set(category_service._DEFAULT_FOLLOWED_RIDS)
            assert db.query(Category).filter(Category.name_vi.is_(None)).count() == 0

    def test_idempotent_on_second_call(self, session_factory) -> None:
        with session_factory() as db:
            category_service.ensure_default_categories(db)
            assert category_service.ensure_default_categories(db) == 0

    def test_existing_db_gets_missing_defaults_without_touching_user_choices(
        self, session_factory
    ) -> None:
        """An old DB has only 1 row the user changed: the missing entries must be topped up,
        without overwriting the name/group, and the new entries must NOT auto-enable following."""
        with session_factory() as db:
            db.add(Category(rid=4, name_zh="游戏", name_vi="Tên tôi tự đặt", is_followed=False))
            db.commit()

            added = category_service.ensure_default_categories(db)

            assert added == len(category_service._DEFAULT_CATEGORIES) - 1
            game = db.get(Category, 4)
            assert game.name_vi == "Tên tôi tự đặt"
            assert game.is_followed is False
            assert db.query(Category).filter(Category.is_followed).count() == 0

    def test_default_rids_are_unique(self) -> None:
        rids = [rid for rid, *_ in category_service._DEFAULT_CATEGORIES]
        assert len(rids) == len(set(rids))
