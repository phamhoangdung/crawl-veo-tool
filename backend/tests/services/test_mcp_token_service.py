import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.models.user import User
from app.services import mcp_token_service as service


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1))
    session.commit()
    yield session
    session.close()


class TestCreateToken:
    def test_returns_plaintext_once_and_stores_only_hash(self, db: Session) -> None:
        """A DB leak must not allow reusing a token — only a one-way hash is stored,
        unlike a provider API key (which must be two-way encrypted since it must be decrypted to be sent)."""
        issued = service.create_token(db, 1, "claude-code", ["gen:write"])

        assert issued.plain_token.startswith("sk_local_")
        assert issued.plain_token not in issued.record.token_hash
        assert len(issued.record.token_hash) == 64

    def test_rejects_unknown_scope(self, db: Session) -> None:
        with pytest.raises(service.McpTokenError, match="không hợp lệ"):
            service.create_token(db, 1, "agent", ["keys:read"])

    def test_rejects_empty_scope_list(self, db: Session) -> None:
        with pytest.raises(service.McpTokenError, match="ít nhất 1 scope"):
            service.create_token(db, 1, "agent", [])

    def test_rejects_blank_name(self, db: Session) -> None:
        with pytest.raises(service.McpTokenError, match="Cần đặt tên"):
            service.create_token(db, 1, "   ", ["gen:write"])

    def test_deduplicates_repeated_scopes(self, db: Session) -> None:
        issued = service.create_token(db, 1, "agent", ["gen:write", "gen:write"])

        assert issued.record.scopes == ["gen:write"]

    def test_two_tokens_never_share_value(self, db: Session) -> None:
        first = service.create_token(db, 1, "a", ["gen:write"])
        second = service.create_token(db, 1, "b", ["gen:write"])

        assert first.plain_token != second.plain_token


class TestAuthenticate:
    def test_accepts_valid_token_and_records_usage(self, db: Session) -> None:
        issued = service.create_token(db, 1, "agent", ["gen:write"])

        record = service.authenticate(db, issued.plain_token)

        assert record is not None
        assert record.id == issued.record.id
        assert record.last_used_at is not None

    def test_rejects_unknown_and_empty_token(self, db: Session) -> None:
        service.create_token(db, 1, "agent", ["gen:write"])

        assert service.authenticate(db, "sk_local_khong_ton_tai") is None
        assert service.authenticate(db, "") is None

    def test_rejects_revoked_token(self, db: Session) -> None:
        issued = service.create_token(db, 1, "agent", ["gen:write"])
        service.revoke_token(db, 1, issued.record.id)

        assert service.authenticate(db, issued.plain_token) is None


class TestRequireScope:
    def test_passes_when_scope_granted(self, db: Session) -> None:
        issued = service.create_token(db, 1, "agent", ["gen:write", "assets:read"])

        service.require_scope(issued.record, "gen:write")

    def test_blocks_when_scope_missing(self, db: Session) -> None:
        """A read-only token must not be allowed to spend money — this is the main reason scopes exist."""
        issued = service.create_token(db, 1, "readonly", ["assets:read"])

        with pytest.raises(service.McpTokenError, match="gen:write"):
            service.require_scope(issued.record, "gen:write")


class TestRevoke:
    def test_revoking_twice_returns_false(self, db: Session) -> None:
        issued = service.create_token(db, 1, "agent", ["gen:write"])

        assert service.revoke_token(db, 1, issued.record.id) is True
        assert service.revoke_token(db, 1, issued.record.id) is False

    def test_unknown_id_returns_false(self, db: Session) -> None:
        assert service.revoke_token(db, 1, 999) is False

    def test_revoked_token_still_listed_for_audit(self, db: Session) -> None:
        """Keep the revoked record so we can still see what access was ever granted to whom."""
        issued = service.create_token(db, 1, "agent", ["gen:write"])
        service.revoke_token(db, 1, issued.record.id)

        tokens = service.list_tokens(db, 1)

        assert len(tokens) == 1
        assert tokens[0].revoked_at is not None
