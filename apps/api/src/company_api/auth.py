"""Single-administrator authentication with server-side sessions."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pwdlib import PasswordHash

from company_api.config import Settings


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SessionRecord:
    token_hash: str
    username: str
    credential_fingerprint: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class NewSession:
    session_token: str
    username: str
    csrf_token: str
    expires_at: datetime


class InvalidLoginChallenge(Exception):
    """The one-time pre-authentication CSRF challenge is missing or invalid."""


class InvalidCredentials(Exception):
    """The administrator credentials are invalid."""


class AuthRepository(Protocol):
    async def create_login_challenge(
        self,
        challenge_hash: str,
        *,
        created_at: datetime,
        expires_at: datetime,
    ) -> None: ...

    async def consume_login_challenge(self, challenge_hash: str, *, now: datetime) -> bool: ...

    async def create_session(
        self,
        record: SessionRecord,
        *,
        created_at: datetime,
    ) -> None: ...

    async def get_session(self, session_hash: str, *, now: datetime) -> SessionRecord | None: ...

    async def delete_session(self, session_hash: str) -> None: ...


class AuthOperations(Protocol):
    async def issue_login_challenge(self) -> str: ...

    async def login(self, username: str, password: str, challenge: str) -> NewSession: ...

    async def authenticate(self, session_token: str) -> SessionRecord | None: ...

    def csrf_is_valid(self, session: SessionRecord, submitted_token: str) -> bool: ...

    async def logout(self, session: SessionRecord) -> None: ...


class AuthService:
    def __init__(self, repository: AuthRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings
        self._password_hash = PasswordHash.recommended()
        self._credential_fingerprint = token_hash(settings.admin_password_hash)

    async def issue_login_challenge(self) -> str:
        now = datetime.now(UTC)
        challenge = secrets.token_urlsafe(32)
        await self._repository.create_login_challenge(
            token_hash(challenge),
            created_at=now,
            expires_at=now + timedelta(seconds=self._settings.login_challenge_lifetime_seconds),
        )
        return challenge

    async def login(self, username: str, password: str, challenge: str) -> NewSession:
        if not challenge or not await self._repository.consume_login_challenge(
            token_hash(challenge),
            now=datetime.now(UTC),
        ):
            raise InvalidLoginChallenge

        username_matches = hmac.compare_digest(username, self._settings.admin_username)
        password_matches = self._password_hash.verify(
            password,
            self._settings.admin_password_hash,
        )
        if not username_matches or not password_matches:
            raise InvalidCredentials

        now = datetime.now(UTC)
        session_token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        record = SessionRecord(
            token_hash=token_hash(session_token),
            username=self._settings.admin_username,
            credential_fingerprint=self._credential_fingerprint,
            csrf_token=csrf_token,
            expires_at=now + timedelta(seconds=self._settings.session_lifetime_seconds),
        )
        await self._repository.create_session(record, created_at=now)
        return NewSession(
            session_token=session_token,
            username=record.username,
            csrf_token=record.csrf_token,
            expires_at=record.expires_at,
        )

    async def authenticate(self, session_token: str) -> SessionRecord | None:
        if not session_token:
            return None
        session = await self._repository.get_session(
            token_hash(session_token),
            now=datetime.now(UTC),
        )
        if session is not None and not hmac.compare_digest(
            session.credential_fingerprint,
            self._credential_fingerprint,
        ):
            await self._repository.delete_session(session.token_hash)
            return None
        return session

    def csrf_is_valid(self, session: SessionRecord, submitted_token: str) -> bool:
        return bool(submitted_token) and hmac.compare_digest(
            session.csrf_token,
            submitted_token,
        )

    async def logout(self, session: SessionRecord) -> None:
        await self._repository.delete_session(session.token_hash)
