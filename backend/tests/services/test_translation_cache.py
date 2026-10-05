from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 — load every model so create_all sees every table
from app.core.db import Base
from app.models.translation_cache import TranslationCache, make_key
from app.models.user import User
from app.services import translate_service


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1))
    session.commit()
    yield session
    session.close()


class TestMakeKey:
    def test_same_text_same_key(self) -> None:
        assert make_key("匹克球", "zh", "vi") == make_key("匹克球", "zh", "vi")

    def test_whitespace_normalized(self) -> None:
        """The same title differing only by extra spaces should not count as 2 translations."""
        assert make_key("  匹克球  规则 ", "zh", "vi") == make_key("匹克球 规则", "zh", "vi")

    def test_different_language_pair_different_key(self) -> None:
        assert make_key("hello", "zh", "vi") != make_key("hello", "en", "vi")

    def test_different_text_different_key(self) -> None:
        assert make_key("a", "zh", "vi") != make_key("b", "zh", "vi")


class TestTranslateCached:
    """The cache is the core point: the tooltip fires on every hover so without a cache a few passes of the
    mouse over a 40-row table exhausts the quota."""

    @pytest.mark.anyio
    async def test_second_call_does_not_hit_api(self, db: Session) -> None:
        calls: list[str] = []

        async def fake(db_, uid, text, src, tgt):
            calls.append(text)
            return f"[VI] {text}"

        with patch.object(translate_service, "translate_text", fake):
            first, cached_first = await translate_service.translate_cached(db, 1, "匹克球规则")
            second, cached_second = await translate_service.translate_cached(db, 1, "匹克球规则")

        assert len(calls) == 1
        assert cached_first is False
        assert cached_second is True
        assert first == second == "[VI] 匹克球规则"

    @pytest.mark.anyio
    async def test_whitespace_variant_reuses_cache(self, db: Session) -> None:
        calls: list[str] = []

        async def fake(db_, uid, text, src, tgt):
            calls.append(text)
            return "kết quả"

        with patch.object(translate_service, "translate_text", fake):
            await translate_service.translate_cached(db, 1, "匹克球 规则")
            _, cached = await translate_service.translate_cached(db, 1, "  匹克球   规则 ")

        assert len(calls) == 1
        assert cached is True

    @pytest.mark.anyio
    async def test_counts_hits(self, db: Session) -> None:
        """hit_count lets us know whether the cache is really effective."""

        async def fake(db_, uid, text, src, tgt):
            return "x"

        with patch.object(translate_service, "translate_text", fake):
            for _ in range(3):
                await translate_service.translate_cached(db, 1, "同一个标题")

        row = db.get(TranslationCache, make_key("同一个标题", "zh", "vi"))
        assert row is not None
        # 3 calls = 1 translation + 2 reuses.
        assert row.hit_count == 2

    @pytest.mark.anyio
    async def test_different_texts_cached_separately(self, db: Session) -> None:
        async def fake(db_, uid, text, src, tgt):
            return f"[VI] {text}"

        with patch.object(translate_service, "translate_text", fake):
            await translate_service.translate_cached(db, 1, "标题一")
            await translate_service.translate_cached(db, 1, "标题二")

        assert db.query(TranslationCache).count() == 2

    @pytest.mark.anyio
    async def test_failure_is_not_cached(self, db: Session) -> None:
        """A quota error must not be stored — next time, with quota available, it must be translatable again."""

        async def failing(db_, uid, text, src, tgt):
            raise translate_service.AllProvidersExhaustedError("hết quota")

        with patch.object(translate_service, "translate_text", failing):
            with pytest.raises(translate_service.AllProvidersExhaustedError):
                await translate_service.translate_cached(db, 1, "标题")

        assert db.query(TranslationCache).count() == 0
