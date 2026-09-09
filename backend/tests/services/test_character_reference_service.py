import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.models.user import User
from app.services import character_reference_service as service

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1))
    session.commit()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(service, "references_dir", lambda: tmp_path)


class TestValidateName:
    def test_rejects_names_that_break_mention_parsing(self) -> None:
        """`name` được gọi trong prompt dạng `@ten` — khoảng trắng/dấu tiếng Việt
        làm việc parse `@ten` không xác định, nên phải chặn từ lúc tạo."""
        for invalid in ["Có Dấu", "hai tu", "dau-gach", "@at", ""]:
            with pytest.raises(service.CharacterReferenceError):
                service.validate_name(invalid)

    def test_accepts_slug_and_normalises_case(self) -> None:
        """Chữ hoa được hạ về chữ thường thay vì báo lỗi — người dùng gõ `@Hero`
        trong prompt vẫn khớp ref tên `hero` (mention parsing cũng lowercase)."""
        assert service.validate_name("  Sunhui_Hero  ") == "sunhui_hero"
        assert service.validate_name("UPPER") == "upper"
        assert service.validate_name("prop_01") == "prop_01"


class TestCreateReference:
    def test_saves_all_images_and_returns_slug(self, db: Session) -> None:
        record = service.create_reference(
            db, 1, "sunhui_hero", [("a.png", _PNG), ("b.jpg", _PNG)], "nhân vật chính"
        )

        assert record.name == "sunhui_hero"
        assert len(record.file_paths) == 2

    def test_rejects_duplicate_name(self, db: Session) -> None:
        service.create_reference(db, 1, "hero", [("a.png", _PNG)])

        with pytest.raises(service.CharacterReferenceError, match="Đã có bộ ảnh"):
            service.create_reference(db, 1, "hero", [("a.png", _PNG)])

    def test_rejects_empty_image_list(self, db: Session) -> None:
        with pytest.raises(service.CharacterReferenceError, match="ít nhất 1 ảnh"):
            service.create_reference(db, 1, "hero", [])

    def test_rejects_unsupported_extension(self, db: Session) -> None:
        with pytest.raises(service.CharacterReferenceError, match="không hỗ trợ"):
            service.create_reference(db, 1, "hero", [("a.gif", _PNG)])

    def test_rejects_oversized_image(self, db: Session) -> None:
        oversized = b"0" * (10 * 1024 * 1024 + 1)
        with pytest.raises(service.CharacterReferenceError, match="vượt giới hạn"):
            service.create_reference(db, 1, "hero", [("a.png", oversized)])


class TestResolveMentions:
    def test_matches_existing_and_reports_missing(self, db: Session) -> None:
        service.create_reference(db, 1, "hero", [("a.png", _PNG)])
        service.create_reference(db, 1, "prop_bag", [("a.png", _PNG)])

        found, missing = service.resolve_mentions(
            db, 1, "@hero @prop_bag @khong_co medium shot, 50mm"
        )

        assert [r.name for r in found] == ["hero", "prop_bag"]
        assert missing == ["khong_co"]

    def test_deduplicates_repeated_mentions(self, db: Session) -> None:
        """Cùng 1 ref gọi nhiều lần trong prompt không được đính kèm ảnh 2 lần —
        vừa tốn payload gửi lên provider, vừa có thể làm lệch kết quả."""
        service.create_reference(db, 1, "hero", [("a.png", _PNG)])

        found, missing = service.resolve_mentions(db, 1, "@hero and @hero again")

        assert len(found) == 1
        assert missing == []

    def test_prompt_without_mentions_returns_nothing(self, db: Session) -> None:
        found, missing = service.resolve_mentions(db, 1, "a plain scene description")

        assert found == []
        assert missing == []


class TestDelete:
    def test_removes_record_and_files(self, db: Session) -> None:
        from pathlib import Path

        record = service.create_reference(db, 1, "hero", [("a.png", _PNG)])
        saved = Path(record.file_paths[0])
        assert saved.exists()

        assert service.delete_reference(db, 1, record.id) is True
        assert not saved.exists()
        assert service.list_references(db, 1) == []

    def test_returns_false_for_unknown_id(self, db: Session) -> None:
        assert service.delete_reference(db, 1, 999) is False
