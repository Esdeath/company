import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from company_api.models import (
    Comment,
    EmailOutbox,
    User,
    UserSession,
    UserStatus,
    UserToken,
    UserTokenPurpose,
)
from company_api.user_auth import CurrentUser, UserRecord, UserSessionRecord
from company_api.user_auth_repository import SqlAlchemyUserAuthRepository

NOW = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)
USER_ID = UUID("00000000-0000-0000-0000-000000000123")
TOKEN_ID = UUID("00000000-0000-0000-0000-000000000456")


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


class FakeResult:
    def __init__(self, value: object | None = None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class FakeSession:
    def __init__(
        self,
        scalar_results: list[object | None] | None = None,
        *,
        commit_error: IntegrityError | None = None,
    ) -> None:
        self.scalar_results = iter(scalar_results or [])
        self.commit_error = commit_error
        self.statements: list[object] = []
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.events: list[tuple[str, int]] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc_value, traceback

    async def scalar(self, statement: object) -> object | None:
        self.statements.append(statement)
        return next(self.scalar_results)

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return FakeResult()

    def add(self, value: object) -> None:
        self.added.append(value)

    async def delete(self, value: object) -> None:
        self.deleted.append(value)

    async def flush(self) -> None:
        self.events.append(("flush", len(self.added)))

    async def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.events.append(("commit", len(self.added)))


class SessionFactory:
    def __init__(self, sessions: list[FakeSession]) -> None:
        self.sessions = iter(sessions)

    def __call__(self) -> FakeSession:
        return next(self.sessions)


def sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def record() -> UserRecord:
    return UserRecord(
        id=USER_ID,
        email="reader@example.com",
        normalized_email="reader@example.com",
        username="价值读者",
        normalized_username="价值读者",
        password_hash="$argon2id$stored",
        status=UserStatus.PENDING_VERIFICATION,
        email_verified_at=None,
        first_comment_approved_at=None,
        reply_email_enabled=True,
        created_at=NOW,
        updated_at=NOW,
        username_changed_at=None,
    )


def session_record(*, user_id: UUID = USER_ID) -> UserSessionRecord:
    return UserSessionRecord(
        token_hash="s" * 64,
        user_id=user_id,
        csrf_token="csrf-token",
        expires_at=NOW + timedelta(days=30),
    )


def user_row(*, status: UserStatus = UserStatus.PENDING_VERIFICATION) -> User:
    return User(
        id=USER_ID,
        email="reader@example.com",
        normalized_email="reader@example.com",
        username="价值读者",
        normalized_username="价值读者",
        password_hash="$argon2id$stored",
        status=status,
        email_verified_at=NOW if status == UserStatus.ACTIVE else None,
        first_comment_approved_at=None,
        reply_email_enabled=True,
        created_at=NOW,
        updated_at=NOW,
        username_changed_at=None,
    )


def token_row(purpose: UserTokenPurpose) -> UserToken:
    return UserToken(
        id=TOKEN_ID,
        token_hash="t" * 64,
        purpose=purpose,
        user_id=USER_ID,
        created_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=30),
        consumed_at=None,
    )


class DriverIntegrityError(Exception):
    def __init__(self, constraint_name: str) -> None:
        self.diag = type("Diagnostic", (), {"constraint_name": constraint_name})()
        super().__init__(constraint_name)


def integrity_error(constraint_name: str) -> IntegrityError:
    return IntegrityError(
        "INSERT",
        {},
        DriverIntegrityError(constraint_name),
    )


def test_registration_stages_user_token_and_safe_outbox_before_one_commit() -> None:
    fake = FakeSession([None])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    run(
        repository.register_user(
            record(),
            token_id=TOKEN_ID,
            token_hash="t" * 64,
            token_expires_at=NOW + timedelta(hours=24),
            email_template="verify_email",
            email_payload={"username": "价值读者"},
            now=NOW,
        )
    )

    assert fake.events == [("flush", 2), ("commit", 3)]
    assert [type(value) for value in fake.added] == [User, UserToken, EmailOutbox]
    stored_user = next(value for value in fake.added if isinstance(value, User))
    stored_token = next(value for value in fake.added if isinstance(value, UserToken))
    outbox = next(value for value in fake.added if isinstance(value, EmailOutbox))
    assert stored_user.normalized_email == "reader@example.com"
    assert stored_token.token_hash == "t" * 64
    assert stored_token.expires_at == NOW + timedelta(hours=24)
    assert outbox.token_id == TOKEN_ID
    assert outbox.recipient == "reader@example.com"
    assert outbox.payload == {"username": "价值读者"}
    assert "token" not in outbox.payload


def test_registration_preserves_unrelated_integrity_error() -> None:
    error = integrity_error("fk_email_outbox_token_id_user_tokens")
    fake = FakeSession([None], commit_error=error)
    lookup = FakeSession([None])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake, lookup]))  # type: ignore[arg-type]

    with pytest.raises(IntegrityError) as caught:
        run(
            repository.register_user(
                record(),
                token_id=TOKEN_ID,
                token_hash="t" * 64,
                token_expires_at=NOW + timedelta(hours=24),
                email_template="verify_email",
                email_payload={"username": "价值读者"},
                now=NOW,
            )
        )

    assert caught.value is error


def test_username_update_preserves_unrelated_integrity_error() -> None:
    error = integrity_error("ck_unrelated_constraint")
    fake = FakeSession([user_row(status=UserStatus.ACTIVE)], commit_error=error)
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    with pytest.raises(IntegrityError) as caught:
        run(
            repository.update_username(
                USER_ID,
                "新名字",
                "新名字",
                now=NOW,
                changed_after=NOW - timedelta(days=30),
            )
        )

    assert caught.value is error


def test_verification_locks_user_then_token_and_activates_with_session() -> None:
    token = token_row(UserTokenPurpose.VERIFY_EMAIL)
    user = user_row()
    fake = FakeSession([USER_ID, user, token])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    activated = run(
        repository.activate_user_and_create_session(
            TOKEN_ID,
            "t" * 64,
            session_record(user_id=UUID(int=0)),
            now=NOW,
        )
    )

    assert activated == (
        CurrentUser(USER_ID, "reader@example.com", "价值读者", NOW, None, True),
        session_record(),
    )
    assert "FROM user_tokens" in sql(fake.statements[0])
    assert "FOR UPDATE" not in sql(fake.statements[0])
    assert "FROM users" in sql(fake.statements[1])
    assert "FOR UPDATE" in sql(fake.statements[1])
    assert "FROM user_tokens" in sql(fake.statements[2])
    assert "FOR UPDATE" in sql(fake.statements[2])
    assert "user_tokens.token_hash" in sql(fake.statements[2])
    assert "user_tokens.purpose" in sql(fake.statements[2])
    assert "user_tokens.consumed_at IS NULL" in sql(fake.statements[2])
    assert "user_tokens.expires_at >" in sql(fake.statements[2])
    assert token.consumed_at == NOW
    assert user.status == UserStatus.ACTIVE
    assert user.email_verified_at == NOW
    stored_session = next(value for value in fake.added if isinstance(value, UserSession))
    assert stored_session.user_id == USER_ID
    assert fake.events == [("commit", 1)]


def test_reset_locks_user_then_token_updates_hash_and_revokes_sessions() -> None:
    token = token_row(UserTokenPurpose.RESET_PASSWORD)
    user = user_row(status=UserStatus.ACTIVE)
    fake = FakeSession([USER_ID, user, token])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    reset = run(
        repository.reset_password_and_create_session(
            TOKEN_ID,
            "t" * 64,
            "$argon2id$new",
            session_record(user_id=UUID(int=0)),
            now=NOW,
        )
    )

    assert reset is not None
    assert reset[1] == session_record()
    assert "FOR UPDATE" not in sql(fake.statements[0])
    assert "FROM users" in sql(fake.statements[1])
    assert "FOR UPDATE" in sql(fake.statements[1])
    assert "FROM user_tokens" in sql(fake.statements[2])
    assert "FOR UPDATE" in sql(fake.statements[2])
    assert token.consumed_at == NOW
    assert user.password_hash == "$argon2id$new"
    assert any(
        "DELETE FROM user_sessions" in sql(statement) and "user_sessions.user_id" in sql(statement)
        for statement in fake.statements
    )
    assert fake.events == [("commit", 1)]


@pytest.mark.parametrize("token_changed", [False, True], ids=["disappeared", "changed"])
def test_verification_rejects_token_changed_after_owner_lookup(token_changed: bool) -> None:
    user = user_row()
    locked_token = token_row(UserTokenPurpose.VERIFY_EMAIL) if token_changed else None
    if locked_token is not None:
        locked_token.token_hash = "x" * 64
        locked_token.consumed_at = NOW
    fake = FakeSession([USER_ID, user, locked_token])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    activated = run(
        repository.activate_user_and_create_session(
            TOKEN_ID,
            "t" * 64,
            session_record(user_id=UUID(int=0)),
            now=NOW,
        )
    )

    assert activated is None
    assert user.status == UserStatus.PENDING_VERIFICATION
    assert fake.added == []
    assert fake.events == [("commit", 0)]


def test_session_creation_locks_user_and_rejects_changed_password_hash() -> None:
    user = user_row(status=UserStatus.ACTIVE)
    user.password_hash = "$argon2id$concurrent-reset"
    fake = FakeSession([user])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    created = run(
        repository.create_session(
            session_record(),
            expected_password_hash="$argon2id$observed",
            created_at=NOW,
        )
    )

    assert created is None
    assert "FOR UPDATE" in sql(fake.statements[0])
    assert fake.added == []
    assert fake.events == [("commit", 0)]


def test_password_update_locks_user_and_does_not_overwrite_changed_hash() -> None:
    user = user_row(status=UserStatus.ACTIVE)
    user.password_hash = "$argon2id$concurrent-reset"
    fake = FakeSession([user])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    updated = run(
        repository.update_password(
            USER_ID,
            "$argon2id$observed",
            "$argon2id$replacement",
            session_record(),
            now=NOW,
        )
    )

    assert updated is None
    assert "FOR UPDATE" in sql(fake.statements[0])
    assert user.password_hash == "$argon2id$concurrent-reset"
    assert fake.added == []
    assert fake.events == [("commit", 0)]


def test_token_replacement_locks_user_before_invalidating_previous_tokens() -> None:
    user = user_row(status=UserStatus.ACTIVE)
    fake = FakeSession([user])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    run(
        repository.create_user_token(
            USER_ID,
            UserTokenPurpose.RESET_PASSWORD,
            token_id=TOKEN_ID,
            token_hash="t" * 64,
            expires_at=NOW + timedelta(minutes=30),
            email_template="reset_password",
            recipient="reader@example.com",
            email_payload={"username": "价值读者"},
            now=NOW,
        )
    )

    assert "FROM users" in sql(fake.statements[0])
    assert "FOR UPDATE" in sql(fake.statements[0])
    assert "DELETE FROM email_outbox" in sql(fake.statements[1])
    assert "UPDATE user_tokens" in sql(fake.statements[2])
    assert len(fake.added) == 2
    assert fake.events == [("flush", 1), ("commit", 2)]


def test_token_replacement_deletes_pending_messages_for_superseded_tokens() -> None:
    user = user_row(status=UserStatus.ACTIVE)
    fake = FakeSession([user])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    run(
        repository.create_user_token(
            USER_ID,
            UserTokenPurpose.RESET_PASSWORD,
            token_id=TOKEN_ID,
            token_hash="t" * 64,
            expires_at=NOW + timedelta(minutes=30),
            email_template="reset_password",
            recipient="reader@example.com",
            email_payload={"username": "价值读者"},
            now=NOW,
        )
    )

    delete_index = next(
        index
        for index, statement in enumerate(fake.statements)
        if sql(statement).startswith("DELETE FROM email_outbox")
    )
    invalidate_index = next(
        index
        for index, statement in enumerate(fake.statements)
        if sql(statement).startswith("UPDATE user_tokens")
    )
    delete_sql = sql(fake.statements[delete_index])
    assert delete_index < invalidate_index
    assert "email_outbox.sent_at IS NULL" in delete_sql
    assert "user_tokens.user_id" in delete_sql
    assert "user_tokens.purpose" in delete_sql
    assert "user_tokens.consumed_at IS NULL" in delete_sql


def test_deletion_locks_account_anonymizes_comments_and_deletes_private_owner() -> None:
    user = user_row(status=UserStatus.ACTIVE)
    fake = FakeSession([user])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    assert run(repository.delete_account(USER_ID, "$argon2id$stored", now=NOW)) is True

    assert "FOR UPDATE" in sql(fake.statements[0])
    anonymize = next(
        statement for statement in fake.statements if "UPDATE comments" in sql(statement)
    )
    compiled = anonymize.compile(dialect=postgresql.dialect())  # type: ignore[attr-defined]
    assert compiled.params["author_id"] is None
    assert Comment.__tablename__ in sql(anonymize)
    assert fake.deleted == [user]
    assert fake.events == [("commit", 0)]


def test_deletion_rejects_password_hash_changed_before_the_user_lock() -> None:
    user = user_row(status=UserStatus.ACTIVE)
    user.password_hash = "$argon2id$concurrent-reset"
    fake = FakeSession([user])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    deleted = run(repository.delete_account(USER_ID, "$argon2id$observed", now=NOW))

    assert deleted is False
    assert "FOR UPDATE" in sql(fake.statements[0])
    assert fake.deleted == []
    assert not any("UPDATE comments" in sql(statement) for statement in fake.statements)
    assert fake.events == [("commit", 0)]


def test_deletion_rejects_account_suspended_before_the_user_lock() -> None:
    user = user_row(status=UserStatus.SUSPENDED)
    fake = FakeSession([user])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    deleted = run(repository.delete_account(USER_ID, "$argon2id$stored", now=NOW))

    assert deleted is False
    assert "FOR UPDATE" in sql(fake.statements[0])
    assert fake.deleted == []
    assert not any("UPDATE comments" in sql(statement) for statement in fake.statements)
    assert fake.events == [("commit", 0)]


@pytest.mark.parametrize("reply_email_enabled", [False, True])
def test_preference_update_only_cancels_reply_email_when_disabling(
    reply_email_enabled: bool,
) -> None:
    user = user_row(status=UserStatus.ACTIVE)
    fake = FakeSession([user])
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    updated = run(
        repository.update_preferences(
            USER_ID,
            reply_email_enabled=reply_email_enabled,
            now=NOW,
        )
    )

    assert updated is not None
    assert "FOR UPDATE" in sql(fake.statements[0])
    cleanup = [sql(statement) for statement in fake.statements[1:]]
    if reply_email_enabled:
        assert cleanup == []
    else:
        assert len(cleanup) == 2
        assert cleanup[0].startswith("DELETE FROM email_outbox")
        assert "email_outbox.template = 'comment_reply'" in cleanup[0]
        assert "email_outbox.sent_at IS NULL" in cleanup[0]
        assert "user_tokens.user_id" in cleanup[0]
        assert cleanup[1].startswith("UPDATE user_tokens")
        assert "user_tokens.purpose" in cleanup[1]
        assert "user_tokens.consumed_at IS NULL" in cleanup[1]


def test_one_time_challenge_uses_delete_returning() -> None:
    fake = FakeSession()
    repository = SqlAlchemyUserAuthRepository(SessionFactory([fake]))  # type: ignore[arg-type]

    assert run(repository.consume_challenge("c" * 64, now=NOW)) is False

    statement = sql(fake.statements[0])
    assert statement.startswith("DELETE FROM user_auth_challenges")
    assert "RETURNING user_auth_challenges.token_hash" in statement
    assert fake.events == [("commit", 0)]
