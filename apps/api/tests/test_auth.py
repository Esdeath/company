import asyncio
from collections.abc import Coroutine
from datetime import datetime
from typing import Any

import pytest
from pwdlib import PasswordHash

from company_api.auth import (
    AuthService,
    InvalidCredentials,
    InvalidLoginChallenge,
    SessionRecord,
    token_hash,
)
from company_api.config import Settings


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


class FakeAuthRepository:
    def __init__(self) -> None:
        self.challenges: dict[str, datetime] = {}
        self.sessions: dict[str, SessionRecord] = {}

    async def create_login_challenge(
        self,
        challenge_hash: str,
        *,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        del created_at
        self.challenges[challenge_hash] = expires_at

    async def consume_login_challenge(self, challenge_hash: str, *, now: datetime) -> bool:
        expires_at = self.challenges.pop(challenge_hash, None)
        return expires_at is not None and expires_at > now

    async def create_session(self, record: SessionRecord, *, created_at: datetime) -> None:
        del created_at
        self.sessions[record.token_hash] = record

    async def get_session(self, session_hash: str, *, now: datetime) -> SessionRecord | None:
        record = self.sessions.get(session_hash)
        if record is None or record.expires_at <= now:
            return None
        return record

    async def delete_session(self, session_hash: str) -> None:
        self.sessions.pop(session_hash, None)


def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://company@postgres/company",
        admin_username="admin",
        admin_password_hash=PasswordHash.recommended().hash("correct horse battery staple"),
        session_cookie_secure=False,
    )


def test_login_challenge_is_one_time_and_session_is_server_side() -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository, settings())
    challenge = run(service.issue_login_challenge())

    logged_in = run(service.login("admin", "correct horse battery staple", challenge))

    assert challenge not in repository.challenges
    assert logged_in.session_token not in repository.sessions
    assert token_hash(logged_in.session_token) in repository.sessions
    assert run(service.authenticate(logged_in.session_token)) is not None
    with pytest.raises(InvalidLoginChallenge):
        run(service.login("admin", "correct horse battery staple", challenge))


def test_bad_credentials_consume_the_challenge_without_creating_a_session() -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository, settings())
    challenge = run(service.issue_login_challenge())

    with pytest.raises(InvalidCredentials):
        run(service.login("admin", "wrong password", challenge))

    assert repository.challenges == {}
    assert repository.sessions == {}


def test_csrf_is_bound_to_session_and_logout_revokes_it() -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository, settings())
    challenge = run(service.issue_login_challenge())
    logged_in = run(service.login("admin", "correct horse battery staple", challenge))
    session = run(service.authenticate(logged_in.session_token))

    assert session is not None
    assert service.csrf_is_valid(session, logged_in.csrf_token)
    assert not service.csrf_is_valid(session, "wrong-token")

    run(service.logout(session))
    assert run(service.authenticate(logged_in.session_token)) is None


def test_changing_the_password_hash_revokes_existing_sessions() -> None:
    repository = FakeAuthRepository()
    original = AuthService(repository, settings())
    challenge = run(original.issue_login_challenge())
    logged_in = run(original.login("admin", "correct horse battery staple", challenge))
    changed_settings = settings().model_copy(
        update={"admin_password_hash": PasswordHash.recommended().hash("a different password")}
    )

    restored = run(AuthService(repository, changed_settings).authenticate(logged_in.session_token))
    assert restored is None
    assert repository.sessions == {}
