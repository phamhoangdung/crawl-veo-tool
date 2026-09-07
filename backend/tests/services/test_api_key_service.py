from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.models.api_key import ApiKeyStatus
from app.models.user import User
from app.services import api_key_service


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1))
    session.commit()
    yield session
    session.close()


class TestAddAndList:
    def test_add_key_does_not_upsert_creates_new_row_each_time(self, db: Session) -> None:
        """Khác bản 1-key/provider cũ: thêm 2 key cùng provider phải ra 2 row riêng,
        không ghi đè nhau (đúng mục tiêu pool nhiều key/provider)."""
        api_key_service.add_key(db, 1, "openai", "key-a", label="Key A")
        api_key_service.add_key(db, 1, "openai", "key-b", label="Key B")

        keys = api_key_service.list_keys(db, 1)
        assert len(keys) == 2
        assert {k.label for k in keys} == {"Key A", "Key B"}
        assert all(k.status == ApiKeyStatus.ACTIVE for k in keys)

    def test_get_decrypted_key_does_not_mutate_usage_stats(self, db: Session) -> None:
        """get_decrypted_key chỉ "peek" (cost_service dùng để kiểm tra có key hay
        không) — không được cập nhật last_used_at/request_count như pick thật."""
        key = api_key_service.add_key(db, 1, "openai", "key-a")

        result = api_key_service.get_decrypted_key(db, 1, "openai")

        assert result == "key-a"
        db.refresh(key)
        assert key.last_used_at is None
        assert key.request_count == 0


class TestPickKeyForTask:
    def test_returns_none_when_pool_empty(self, db: Session) -> None:
        assert api_key_service.pick_key_for_task(db, 1, "openai") is None

    def test_picks_active_key_and_updates_usage_stats(self, db: Session) -> None:
        key = api_key_service.add_key(db, 1, "openai", "key-a")

        picked = api_key_service.pick_key_for_task(db, 1, "openai")

        assert picked is not None
        assert picked.id == key.id
        assert picked.request_count == 1
        assert picked.last_used_at is not None

    def test_rotates_to_least_recently_used_key(self, db: Session) -> None:
        """2 key cùng provider: key chưa dùng lần nào phải được ưu tiên trước key đã
        dùng — đúng round-robin/LRU thay vì luôn trả về key đầu tiên."""
        key_a = api_key_service.add_key(db, 1, "openai", "key-a")
        key_b = api_key_service.add_key(db, 1, "openai", "key-b")

        first_pick = api_key_service.pick_key_for_task(db, 1, "openai")
        assert first_pick.id == key_a.id  # cả 2 chưa dùng, id nhỏ hơn (insert trước) được chọn trước

        second_pick = api_key_service.pick_key_for_task(db, 1, "openai")
        assert second_pick.id == key_b.id  # key_a vừa dùng nên tới lượt key_b

    def test_skips_key_in_cooldown(self, db: Session) -> None:
        key_a = api_key_service.add_key(db, 1, "openai", "key-a")
        api_key_service.add_key(db, 1, "openai", "key-b")

        api_key_service.pick_key_for_task(db, 1, "openai")  # chọn key_a
        api_key_service.mark_key_result(db, key_a.id, success=False)  # key_a -> cooldown

        picked = api_key_service.pick_key_for_task(db, 1, "openai")
        assert picked.id != key_a.id

    def test_returns_none_when_all_keys_in_cooldown(self, db: Session) -> None:
        key = api_key_service.add_key(db, 1, "openai", "key-a")
        api_key_service.pick_key_for_task(db, 1, "openai")
        api_key_service.mark_key_result(db, key.id, success=False)

        assert api_key_service.pick_key_for_task(db, 1, "openai") is None

    def test_reactivates_key_after_cooldown_expires(self, db: Session) -> None:
        key = api_key_service.add_key(db, 1, "openai", "key-a")
        api_key_service.mark_key_result(db, key.id, success=False)
        # Giả lập cooldown đã hết hạn (đặt về quá khứ) thay vì chờ thật 60 phút.
        key.cooldown_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

        picked = api_key_service.pick_key_for_task(db, 1, "openai")

        assert picked is not None
        assert picked.id == key.id
        assert picked.status == ApiKeyStatus.ACTIVE

    def test_skips_manually_invalidated_key(self, db: Session) -> None:
        key = api_key_service.add_key(db, 1, "openai", "key-a")
        api_key_service.update_key(db, 1, key.id, status=ApiKeyStatus.INVALID)

        assert api_key_service.pick_key_for_task(db, 1, "openai") is None

    def test_different_provider_pools_are_independent(self, db: Session) -> None:
        api_key_service.add_key(db, 1, "openai", "openai-key")

        assert api_key_service.pick_key_for_task(db, 1, "elevenlabs") is None


class TestMarkKeyResult:
    def test_success_does_not_change_status(self, db: Session) -> None:
        key = api_key_service.add_key(db, 1, "openai", "key-a")
        api_key_service.mark_key_result(db, key.id, success=True)
        db.refresh(key)
        assert key.status == ApiKeyStatus.ACTIVE
        assert key.error_count == 0

    def test_failure_sets_cooldown_with_future_timestamp(self, db: Session) -> None:
        key = api_key_service.add_key(db, 1, "openai", "key-a")
        api_key_service.mark_key_result(db, key.id, success=False)
        db.refresh(key)
        assert key.status == ApiKeyStatus.COOLDOWN
        assert key.error_count == 1
        assert key.cooldown_until is not None
        # SQLite làm mất tzinfo khi round-trip qua DB (DateTime(timezone=True) không
        # thực sự giữ offset trên dialect này) — so sánh naive-naive để tránh
        # TypeError, không phải dấu hiệu lỗi logic (query filter ở service dùng
        # SQLAlchemy bind param nên vẫn so sánh đúng, xem test_reactivates_key_after_cooldown_expires).
        assert key.cooldown_until > datetime.now(timezone.utc).replace(tzinfo=None)


class TestUpdateAndDelete:
    def test_update_label(self, db: Session) -> None:
        key = api_key_service.add_key(db, 1, "openai", "key-a", label="old")
        updated = api_key_service.update_key(db, 1, key.id, label="new")
        assert updated.label == "new"

    def test_setting_status_active_clears_cooldown(self, db: Session) -> None:
        key = api_key_service.add_key(db, 1, "openai", "key-a")
        api_key_service.mark_key_result(db, key.id, success=False)

        updated = api_key_service.update_key(db, 1, key.id, status=ApiKeyStatus.ACTIVE)

        assert updated.status == ApiKeyStatus.ACTIVE
        assert updated.cooldown_until is None

    def test_delete_key(self, db: Session) -> None:
        key = api_key_service.add_key(db, 1, "openai", "key-a")
        assert api_key_service.delete_key(db, 1, key.id) is True
        assert api_key_service.list_keys(db, 1) == []

    def test_delete_nonexistent_key_returns_false(self, db: Session) -> None:
        assert api_key_service.delete_key(db, 1, 999) is False

    def test_cannot_access_another_users_key(self, db: Session) -> None:
        key = api_key_service.add_key(db, 1, "openai", "key-a")
        assert api_key_service.get_key(db, user_id=2, key_id=key.id) is None
