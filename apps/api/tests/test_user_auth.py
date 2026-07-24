import asyncio
from collections.abc import Coroutine
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from pwdlib import PasswordHash

from company_api.config import Settings
from company_api.email_tokens import EmailTokenSigner
from company_api.models import UserStatus, UserTokenPurpose
from company_api.rate_limit import fixed_window_start
from company_api.user_auth import (
    AccountSuspended,
    ChallengeInvalid,
    CredentialsInvalid,
    CurrentUser,
    NewUserSession,
    RateLimitExceeded,
    RegistrationClosed,
    TokenInvalid,
    UserAuthService,
    UsernameChangeTooSoon,
    UsernameUnavailable,
    UserRecord,
    UserSessionRecord,
    normalize_username,
    token_hash,
)

NOW = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)
USER_ID = UUID("00000000-0000-0000-0000-000000000123")
TOKEN_ID = UUID("00000000-0000-0000-0000-000000000456")


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self.blocked_actions: set[str] = set()
        self.calls: list[tuple[str, str, int, timedelta, datetime]] = []

    async def consume(
        self,
        action: str,
        subject: str,
        *,
        limit: int,
        window: timedelta,
        now: datetime,
    ) -> bool:
        fixed_window_start(now, window)
        self.calls.append((action, subject, limit, window, now))
        return action not in self.blocked_actions


class InMemoryUserAuthRepository:
    def __init__(self) -> None:
        self.challenges: dict[str, datetime] = {}
        self.users: dict[UUID, UserRecord] = {}
        self.sessions: dict[str, UserSessionRecord] = {}
        self.tokens: dict[UUID, tuple[str, UserTokenPurpose, UUID, datetime, datetime | None]] = {}
        self.outbox: list[tuple[UUID, str, str, dict[str, object]]] = []
        self.anonymized_users: list[UUID] = []
        self.password_hash_before_session: str | None = None
        self.password_hash_before_update: str | None = None
        self.password_hash_before_delete: str | None = None

    async def create_challenge(
        self,
        challenge_hash: str,
        *,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        del created_at
        self.challenges[challenge_hash] = expires_at

    async def consume_challenge(self, challenge_hash: str, *, now: datetime) -> bool:
        expires_at = self.challenges.pop(challenge_hash, None)
        return expires_at is not None and expires_at > now

    async def find_user_by_email(self, normalized_email: str) -> UserRecord | None:
        return next(
            (user for user in self.users.values() if user.normalized_email == normalized_email),
            None,
        )

    async def username_is_available(
        self,
        normalized_username: str,
        *,
        excluding_user_id: UUID | None = None,
    ) -> bool:
        return not any(
            user.normalized_username == normalized_username and user.id != excluding_user_id
            for user in self.users.values()
        )

    async def register_user(
        self,
        user: UserRecord,
        *,
        token_id: UUID,
        token_hash: str,
        token_expires_at: datetime,
        email_template: str,
        email_payload: dict[str, object],
        now: datetime,
    ) -> None:
        existing = await self.find_user_by_email(user.normalized_email)
        if existing is not None:
            self.users.pop(existing.id)
        self.users[user.id] = user
        self._replace_token(
            token_id,
            token_hash,
            UserTokenPurpose.VERIFY_EMAIL,
            user.id,
            token_expires_at,
            now,
        )
        self.outbox.append((token_id, email_template, user.email, email_payload))

    async def create_user_token(
        self,
        user_id: UUID,
        purpose: UserTokenPurpose,
        *,
        token_id: UUID,
        token_hash: str,
        expires_at: datetime,
        email_template: str,
        recipient: str,
        email_payload: dict[str, object],
        now: datetime,
    ) -> None:
        self._replace_token(token_id, token_hash, purpose, user_id, expires_at, now)
        self.outbox.append((token_id, email_template, recipient, email_payload))

    def _replace_token(
        self,
        token_id: UUID,
        digest: str,
        purpose: UserTokenPurpose,
        user_id: UUID,
        expires_at: datetime,
        now: datetime,
    ) -> None:
        for old_id, (_, old_purpose, old_user_id, _, consumed_at) in list(self.tokens.items()):
            if old_purpose == purpose and old_user_id == user_id and consumed_at is None:
                old = self.tokens[old_id]
                self.tokens[old_id] = (*old[:4], now)
        self.tokens[token_id] = (digest, purpose, user_id, expires_at, None)

    async def activate_user_and_create_session(
        self,
        token_id: UUID,
        token_digest: str,
        session: UserSessionRecord,
        *,
        now: datetime,
    ) -> tuple[CurrentUser, UserSessionRecord] | None:
        token = self.tokens.get(token_id)
        if (
            token is None
            or token[0] != token_digest
            or token[1] != UserTokenPurpose.VERIFY_EMAIL
            or token[3] <= now
            or token[4] is not None
        ):
            return None
        user = self.users[token[2]]
        user = replace(
            user,
            status=UserStatus.ACTIVE,
            email_verified_at=now,
            updated_at=now,
        )
        self.users[user.id] = user
        self.tokens[token_id] = (*token[:4], now)
        actual_session = replace(session, user_id=user.id)
        self.sessions[session.token_hash] = actual_session
        return current_user(user), actual_session

    async def create_session(
        self,
        session: UserSessionRecord,
        *,
        expected_password_hash: str,
        created_at: datetime,
    ) -> UserRecord | None:
        del created_at
        user = self.users.get(session.user_id)
        if user is None:
            return None
        if self.password_hash_before_session is not None:
            user = replace(user, password_hash=self.password_hash_before_session)
            self.users[user.id] = user
            self.sessions = {
                key: value for key, value in self.sessions.items() if value.user_id != user.id
            }
        if user.password_hash != expected_password_hash or user.status != UserStatus.ACTIVE:
            return None
        self.sessions[session.token_hash] = session
        return user

    async def get_session(
        self,
        session_hash: str,
        *,
        now: datetime,
    ) -> tuple[UserSessionRecord, UserRecord] | None:
        session = self.sessions.get(session_hash)
        if session is None or session.expires_at <= now:
            return None
        user = self.users.get(session.user_id)
        if user is None:
            return None
        return session, user

    async def delete_session(self, session_hash: str) -> None:
        self.sessions.pop(session_hash, None)

    async def reset_password_and_create_session(
        self,
        token_id: UUID,
        token_digest: str,
        password_hash: str,
        session: UserSessionRecord,
        *,
        now: datetime,
    ) -> tuple[CurrentUser, UserSessionRecord] | None:
        token = self.tokens.get(token_id)
        if (
            token is None
            or token[0] != token_digest
            or token[1] != UserTokenPurpose.RESET_PASSWORD
            or token[3] <= now
            or token[4] is not None
        ):
            return None
        user = self.users[token[2]]
        self.users[user.id] = replace(user, password_hash=password_hash, updated_at=now)
        self.tokens[token_id] = (*token[:4], now)
        self.sessions = {
            key: value for key, value in self.sessions.items() if value.user_id != user.id
        }
        actual_session = replace(session, user_id=user.id)
        self.sessions[session.token_hash] = actual_session
        return current_user(self.users[user.id]), actual_session

    async def update_username(
        self,
        user_id: UUID,
        username: str,
        normalized_username: str,
        *,
        now: datetime,
        changed_after: datetime,
    ) -> UserRecord | None:
        user = self.users.get(user_id)
        if user is None or (
            user.username_changed_at is not None and user.username_changed_at > changed_after
        ):
            return None
        updated = replace(
            user,
            username=username,
            normalized_username=normalized_username,
            updated_at=now,
            username_changed_at=now,
        )
        self.users[user_id] = updated
        return updated

    async def update_password(
        self,
        user_id: UUID,
        expected_password_hash: str,
        password_hash: str,
        session: UserSessionRecord,
        *,
        now: datetime,
    ) -> UserRecord | None:
        user = self.users.get(user_id)
        if user is None:
            return None
        if self.password_hash_before_update is not None:
            user = replace(user, password_hash=self.password_hash_before_update)
            self.users[user_id] = user
            self.sessions = {
                key: value for key, value in self.sessions.items() if value.user_id != user_id
            }
        if user.password_hash != expected_password_hash:
            return None
        updated = replace(user, password_hash=password_hash, updated_at=now)
        self.users[user_id] = updated
        self.sessions = {
            key: value for key, value in self.sessions.items() if value.user_id != user_id
        }
        self.sessions[session.token_hash] = session
        return updated

    async def update_preferences(
        self,
        user_id: UUID,
        *,
        reply_email_enabled: bool,
        now: datetime,
    ) -> UserRecord | None:
        user = self.users.get(user_id)
        if user is None:
            return None
        updated = replace(
            user,
            reply_email_enabled=reply_email_enabled,
            updated_at=now,
        )
        self.users[user_id] = updated
        return updated

    async def delete_account(
        self,
        user_id: UUID,
        expected_password_hash: str,
        *,
        now: datetime,
    ) -> bool:
        del now
        user = self.users.get(user_id)
        if user is None:
            return False
        if self.password_hash_before_delete is not None:
            user = replace(user, password_hash=self.password_hash_before_delete)
            self.users[user_id] = user
            self.sessions = {
                key: value for key, value in self.sessions.items() if value.user_id != user_id
            }
        if user.status != UserStatus.ACTIVE or user.password_hash != expected_password_hash:
            return False
        self.users.pop(user_id)
        self.sessions = {
            key: value for key, value in self.sessions.items() if value.user_id != user_id
        }
        self.tokens = {key: value for key, value in self.tokens.items() if value[2] != user_id}
        self.anonymized_users.append(user_id)
        return True


def settings(*, registration_enabled: bool = True) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://company@postgres/company",
        admin_username="admin",
        admin_password_hash=PasswordHash.recommended().hash("admin-password"),
        session_cookie_secure=False,
        user_registration_enabled=registration_enabled,
        user_session_lifetime_seconds=2_592_000,
        user_token_signing_key="x" * 32,
    )


def user_record(
    *,
    status: UserStatus = UserStatus.ACTIVE,
    username_changed_at: datetime | None = None,
) -> UserRecord:
    verified_at = NOW if status != UserStatus.PENDING_VERIFICATION else None
    return UserRecord(
        id=USER_ID,
        email="reader@example.com",
        normalized_email="reader@example.com",
        username="价值读者",
        normalized_username="价值读者",
        password_hash=PasswordHash.recommended().hash("correct-password"),
        status=status,
        email_verified_at=verified_at,
        first_comment_approved_at=None,
        reply_email_enabled=True,
        created_at=NOW,
        updated_at=NOW,
        username_changed_at=username_changed_at,
    )


def current_user(user: UserRecord) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        email=user.email,
        username=user.username,
        email_verified_at=user.email_verified_at,
        first_comment_approved_at=user.first_comment_approved_at,
        reply_email_enabled=user.reply_email_enabled,
    )


def service(
    repository: InMemoryUserAuthRepository,
    limiter: InMemoryRateLimiter | None = None,
    *,
    registration_enabled: bool = True,
) -> UserAuthService:
    return UserAuthService(
        repository,
        limiter or InMemoryRateLimiter(),
        EmailTokenSigner("x" * 32),
        settings(registration_enabled=registration_enabled),
        clock=lambda: NOW,
        uuid_factory=lambda: USER_ID if not repository.users else TOKEN_ID,
    )


def challenge(auth: UserAuthService) -> str:
    return run(auth.issue_challenge())


def session_for(repository: InMemoryUserAuthRepository, auth: UserAuthService) -> NewUserSession:
    repository.users[USER_ID] = user_record()
    return run(auth.login("READER@EXAMPLE.COM", "correct-password", challenge(auth)))


def test_challenge_is_one_time_even_when_registration_is_closed() -> None:
    repository = InMemoryUserAuthRepository()
    auth = service(repository, registration_enabled=False)
    issued = challenge(auth)

    with pytest.raises(RegistrationClosed):
        run(auth.register("reader@example.com", "价值读者", "secret-password", issued))
    with pytest.raises(ChallengeInvalid):
        run(auth.register("reader@example.com", "价值读者", "secret-password", issued))


def test_registration_normalizes_identity_hashes_password_and_queues_24_hour_token() -> None:
    repository = InMemoryUserAuthRepository()
    auth = service(repository)

    run(auth.register(" Reader@Example.COM ", "Ｖalue_读者", "secret-password", challenge(auth)))

    registered = next(iter(repository.users.values()))
    assert registered.email == "Reader@example.com"
    assert registered.normalized_email == "reader@example.com"
    assert registered.username == "Value_读者"
    assert registered.normalized_username == "value_读者"
    assert registered.status == UserStatus.PENDING_VERIFICATION
    assert registered.password_hash != "secret-password"
    assert PasswordHash.recommended().verify("secret-password", registered.password_hash)
    token_id, (digest, purpose, user_id, expires_at, consumed_at) = next(
        iter(repository.tokens.items())
    )
    assert purpose == UserTokenPurpose.VERIFY_EMAIL
    assert user_id == registered.id
    assert expires_at == NOW + timedelta(hours=24)
    assert consumed_at is None
    assert repository.outbox == [
        (token_id, "verify_email", registered.email, {"username": registered.username})
    ]
    assert digest != EmailTokenSigner("x" * 32).issue(token_id, purpose)


def test_duplicate_active_email_has_generic_success_and_does_not_change_account() -> None:
    repository = InMemoryUserAuthRepository()
    original = user_record()
    repository.users[USER_ID] = original
    auth = service(repository)

    result = run(
        auth.register(
            "READER@example.com",
            "A_Different_Name",
            "new-password",
            challenge(auth),
        )
    )

    assert result is None
    assert repository.users[USER_ID] == original
    assert repository.outbox == []


def test_registration_rejects_casefolded_username_collision() -> None:
    repository = InMemoryUserAuthRepository()
    repository.users[USER_ID] = user_record()
    auth = service(repository)

    with pytest.raises(UsernameUnavailable):
        run(
            auth.register(
                "other@example.com",
                "价值读者",
                "secret-password",
                challenge(auth),
            )
        )


def test_verification_activates_user_and_returns_30_day_session() -> None:
    repository = InMemoryUserAuthRepository()
    auth = service(repository)
    run(auth.register("reader@example.com", "价值读者", "secret-password", challenge(auth)))
    token_id = next(iter(repository.tokens))
    raw_token = EmailTokenSigner("x" * 32).issue(token_id, UserTokenPurpose.VERIFY_EMAIL)

    verified = run(auth.verify_email(raw_token, challenge(auth)))
    authenticated = run(auth.authenticate(verified.session_token))

    assert verified.expires_at == NOW + timedelta(days=30)
    assert authenticated is not None
    assert authenticated.current_user == CurrentUser(
        id=USER_ID,
        email="reader@example.com",
        username="价值读者",
        email_verified_at=NOW,
        first_comment_approved_at=None,
        reply_email_enabled=True,
    )
    with pytest.raises(TokenInvalid):
        run(auth.verify_email(raw_token, challenge(auth)))


def test_expired_verification_token_is_rejected() -> None:
    repository = InMemoryUserAuthRepository()
    repository.users[USER_ID] = user_record(status=UserStatus.PENDING_VERIFICATION)
    signer = EmailTokenSigner("x" * 32)
    raw_token = signer.issue(TOKEN_ID, UserTokenPurpose.VERIFY_EMAIL)
    repository.tokens[TOKEN_ID] = (
        signer.digest(raw_token),
        UserTokenPurpose.VERIFY_EMAIL,
        USER_ID,
        NOW,
        None,
    )
    auth = service(repository)

    with pytest.raises(TokenInvalid):
        run(auth.verify_email(raw_token, challenge(auth)))


def test_login_matches_email_case_insensitively_and_consumes_bad_challenge() -> None:
    repository = InMemoryUserAuthRepository()
    repository.users[USER_ID] = user_record()
    auth = service(repository)
    issued = challenge(auth)

    logged_in = run(auth.login("READER@EXAMPLE.COM", "correct-password", issued))

    assert logged_in.current_user == current_user(repository.users[USER_ID])
    assert logged_in.expires_at == NOW + timedelta(days=30)
    assert logged_in.session_token not in repository.sessions
    assert token_hash(logged_in.session_token) in repository.sessions
    with pytest.raises(ChallengeInvalid):
        run(auth.login("READER@EXAMPLE.COM", "correct-password", issued))


def test_login_rejects_password_hash_changed_after_verification() -> None:
    repository = InMemoryUserAuthRepository()
    repository.users[USER_ID] = user_record()
    reset_hash = PasswordHash.recommended().hash("reset-won-the-race")
    repository.password_hash_before_session = reset_hash
    auth = service(repository)

    with pytest.raises(CredentialsInvalid):
        run(auth.login("reader@example.com", "correct-password", challenge(auth)))

    assert repository.users[USER_ID].password_hash == reset_hash
    assert repository.sessions == {}


@pytest.mark.parametrize("status", [UserStatus.PENDING_VERIFICATION, UserStatus.SUSPENDED])
def test_login_rejects_ineligible_accounts(status: UserStatus) -> None:
    repository = InMemoryUserAuthRepository()
    repository.users[USER_ID] = user_record(status=status)
    auth = service(repository)

    error = AccountSuspended if status == UserStatus.SUSPENDED else CredentialsInvalid
    with pytest.raises(error):
        run(auth.login("reader@example.com", "correct-password", challenge(auth)))
    assert repository.sessions == {}


def test_logout_revokes_session_and_suspended_session_does_not_authenticate() -> None:
    repository = InMemoryUserAuthRepository()
    auth = service(repository)
    logged_in = session_for(repository, auth)
    stored = run(auth.authenticate(logged_in.session_token))
    assert stored is not None

    repository.users[USER_ID] = replace(repository.users[USER_ID], status=UserStatus.SUSPENDED)
    assert run(auth.authenticate(logged_in.session_token)) is None
    assert repository.sessions == {}

    logged_in = session_for(repository, auth)
    stored = run(auth.authenticate(logged_in.session_token))
    assert stored is not None
    run(auth.logout(stored))
    assert repository.sessions == {}


def test_password_reset_is_generic_and_success_revokes_old_sessions() -> None:
    repository = InMemoryUserAuthRepository()
    repository.users[USER_ID] = user_record()
    auth = service(repository)
    old_session = run(auth.login("reader@example.com", "correct-password", challenge(auth)))

    assert run(auth.request_password_reset("unknown@example.com", challenge(auth))) is None
    assert repository.outbox == []
    run(auth.request_password_reset("READER@example.com", challenge(auth)))
    token_id = next(iter(repository.tokens))
    assert repository.tokens[token_id][3] == NOW + timedelta(minutes=30)
    token = EmailTokenSigner("x" * 32).issue(token_id, UserTokenPurpose.RESET_PASSWORD)
    reset = run(auth.reset_password(token, "new-secret-password", challenge(auth)))

    assert run(auth.authenticate(old_session.session_token)) is None
    assert run(auth.authenticate(reset.session_token)) is not None
    assert PasswordHash.recommended().verify(
        "new-secret-password", repository.users[USER_ID].password_hash
    )


def test_expired_password_reset_token_is_rejected() -> None:
    repository = InMemoryUserAuthRepository()
    repository.users[USER_ID] = user_record()
    signer = EmailTokenSigner("x" * 32)
    raw_token = signer.issue(TOKEN_ID, UserTokenPurpose.RESET_PASSWORD)
    repository.tokens[TOKEN_ID] = (
        signer.digest(raw_token),
        UserTokenPurpose.RESET_PASSWORD,
        USER_ID,
        NOW,
        None,
    )
    auth = service(repository)

    with pytest.raises(TokenInvalid):
        run(auth.reset_password(raw_token, "new-secret-password", challenge(auth)))


def test_username_change_enforces_casefolded_uniqueness_and_30_day_cooldown() -> None:
    repository = InMemoryUserAuthRepository()
    auth = service(repository)
    logged_in = session_for(repository, auth)
    session = run(auth.authenticate(logged_in.session_token))
    assert session is not None

    changed = run(auth.update_username(session, "Ｎew_Name"))
    assert changed.username == "New_Name"
    assert repository.users[USER_ID].normalized_username == "new_name"
    with pytest.raises(UsernameChangeTooSoon):
        run(auth.update_username(session, "Another_Name"))

    other_id = UUID("00000000-0000-0000-0000-000000000999")
    repository.users[other_id] = replace(
        user_record(),
        id=other_id,
        email="other@example.com",
        normalized_email="other@example.com",
        username="Taken_Name",
        normalized_username="taken_name",
    )
    repository.users[USER_ID] = replace(
        repository.users[USER_ID],
        username_changed_at=NOW - timedelta(days=30),
    )
    with pytest.raises(UsernameUnavailable):
        run(auth.update_username(session, "taken_NAME"))


def test_password_preferences_and_deletion_require_active_account() -> None:
    repository = InMemoryUserAuthRepository()
    auth = service(repository)
    logged_in = session_for(repository, auth)
    session = run(auth.authenticate(logged_in.session_token))
    assert session is not None

    updated = run(auth.update_preferences(session, reply_email_enabled=False))
    assert updated.reply_email_enabled is False
    replacement = run(auth.update_password(session, "correct-password", "replacement-password"))
    assert run(auth.authenticate(logged_in.session_token)) is None
    replacement_session = run(auth.authenticate(replacement.session_token))
    assert replacement_session is not None
    with pytest.raises(CredentialsInvalid):
        run(auth.delete_account(replacement_session, "wrong-password"))
    run(auth.delete_account(replacement_session, "replacement-password"))
    assert repository.users == {}
    assert repository.sessions == {}
    assert repository.anonymized_users == [USER_ID]


def test_password_change_does_not_overwrite_concurrent_reset() -> None:
    repository = InMemoryUserAuthRepository()
    auth = service(repository)
    logged_in = session_for(repository, auth)
    session = run(auth.authenticate(logged_in.session_token))
    assert session is not None
    reset_hash = PasswordHash.recommended().hash("reset-won-the-race")
    repository.password_hash_before_update = reset_hash

    with pytest.raises(CredentialsInvalid):
        run(auth.update_password(session, "correct-password", "replacement-password"))

    assert repository.users[USER_ID].password_hash == reset_hash
    assert repository.sessions == {}


def test_account_deletion_rejects_a_concurrent_password_reset() -> None:
    repository = InMemoryUserAuthRepository()
    auth = service(repository)
    logged_in = session_for(repository, auth)
    session = run(auth.authenticate(logged_in.session_token))
    assert session is not None
    reset_hash = PasswordHash.recommended().hash("reset-won-the-race")
    repository.password_hash_before_delete = reset_hash

    with pytest.raises(CredentialsInvalid):
        run(auth.delete_account(session, "correct-password"))

    assert repository.users[USER_ID].password_hash == reset_hash
    assert repository.anonymized_users == []


def test_rate_limit_failure_is_exposed_for_anonymous_and_account_actions() -> None:
    repository = InMemoryUserAuthRepository()
    limiter = InMemoryRateLimiter()
    limiter.blocked_actions.add("register")
    auth = service(repository, limiter)

    with pytest.raises(RateLimitExceeded):
        run(auth.register("reader@example.com", "价值读者", "secret-password", challenge(auth)))

    limiter.blocked_actions.clear()
    logged_in = session_for(repository, auth)
    session = run(auth.authenticate(logged_in.session_token))
    assert session is not None
    limiter.blocked_actions.add("account_change")
    with pytest.raises(RateLimitExceeded):
        run(auth.update_preferences(session, reply_email_enabled=False))


def test_suspended_account_cannot_change_username_with_an_existing_session() -> None:
    repository = InMemoryUserAuthRepository()
    repository.users[USER_ID] = user_record(status=UserStatus.SUSPENDED)
    stored = UserSessionRecord(
        token_hash="s" * 64,
        user_id=USER_ID,
        csrf_token="csrf-token",
        expires_at=NOW + timedelta(days=30),
    )
    repository.sessions[stored.token_hash] = stored
    auth = service(repository)

    with pytest.raises(AccountSuspended):
        run(auth.update_username(stored, "New_Name"))


def test_username_normalization_enforces_casefolded_storage_boundary() -> None:
    assert normalize_username("ß" * 15) == ("ß" * 15, "ss" * 15)
    repository = InMemoryUserAuthRepository()
    auth = service(repository)

    with pytest.raises(ValueError, match="username"):
        run(
            auth.register(
                "reader@example.com",
                "ß" * 30,
                "secret-password",
                challenge(auth),
            )
        )

    assert repository.users == {}
    assert repository.tokens == {}
    assert repository.outbox == []
