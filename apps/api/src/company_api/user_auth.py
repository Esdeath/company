"""Ordinary-user authentication and account operations."""

import hashlib
import hmac
import secrets
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from pwdlib import PasswordHash

from company_api.config import Settings
from company_api.email_tokens import EmailTokenSigner
from company_api.models import UserStatus, UserTokenPurpose
from company_api.rate_limit import RateLimiter

CHALLENGE_LIFETIME = timedelta(minutes=10)
VERIFY_EMAIL_LIFETIME = timedelta(hours=24)
PASSWORD_RESET_LIFETIME = timedelta(minutes=30)
USERNAME_CHANGE_COOLDOWN = timedelta(days=30)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: UUID
    email: str
    normalized_email: str
    username: str
    normalized_username: str
    password_hash: str
    status: UserStatus
    email_verified_at: datetime | None
    first_comment_approved_at: datetime | None
    reply_email_enabled: bool
    created_at: datetime
    updated_at: datetime
    username_changed_at: datetime | None


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: UUID
    email: str
    username: str
    email_verified_at: datetime | None
    first_comment_approved_at: datetime | None
    reply_email_enabled: bool


@dataclass(frozen=True, slots=True)
class UserSessionRecord:
    token_hash: str
    user_id: UUID
    csrf_token: str
    expires_at: datetime
    current_user: CurrentUser | None = None


@dataclass(frozen=True, slots=True)
class NewUserSession:
    session_token: str
    csrf_token: str
    expires_at: datetime
    current_user: CurrentUser


class ChallengeInvalid(Exception):
    """The anonymous one-time challenge is missing, expired, or consumed."""


class CredentialsInvalid(Exception):
    """The supplied account credentials are invalid."""


class RegistrationClosed(Exception):
    """New user registration is disabled."""


class UsernameUnavailable(Exception):
    """The public username is already in use."""


class TokenInvalid(Exception):
    """An email action token is invalid, expired, or already consumed."""


class AccountSuspended(Exception):
    """The account has been suspended."""


class UsernameChangeTooSoon(Exception):
    """The username was changed within the cooldown period."""


class RateLimitExceeded(Exception):
    """The account operation exceeded its fixed-window allowance."""


class UserAuthRepository(Protocol):
    async def create_challenge(
        self,
        challenge_hash: str,
        *,
        created_at: datetime,
        expires_at: datetime,
    ) -> None: ...

    async def consume_challenge(self, challenge_hash: str, *, now: datetime) -> bool: ...

    async def find_user_by_email(self, normalized_email: str) -> UserRecord | None: ...

    async def username_is_available(
        self,
        normalized_username: str,
        *,
        excluding_user_id: UUID | None = None,
    ) -> bool: ...

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
    ) -> None: ...

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
    ) -> None: ...

    async def activate_user_and_create_session(
        self,
        token_id: UUID,
        token_digest: str,
        session: UserSessionRecord,
        *,
        now: datetime,
    ) -> tuple[CurrentUser, UserSessionRecord] | None: ...

    async def create_session(
        self,
        session: UserSessionRecord,
        *,
        expected_password_hash: str,
        created_at: datetime,
    ) -> UserRecord | None: ...

    async def get_session(
        self,
        session_hash: str,
        *,
        now: datetime,
    ) -> tuple[UserSessionRecord, UserRecord] | None: ...

    async def delete_session(self, session_hash: str) -> None: ...

    async def reset_password_and_create_session(
        self,
        token_id: UUID,
        token_digest: str,
        password_hash: str,
        session: UserSessionRecord,
        *,
        now: datetime,
    ) -> tuple[CurrentUser, UserSessionRecord] | None: ...

    async def update_username(
        self,
        user_id: UUID,
        username: str,
        normalized_username: str,
        *,
        now: datetime,
        changed_after: datetime,
    ) -> UserRecord | None: ...

    async def update_password(
        self,
        user_id: UUID,
        expected_password_hash: str,
        password_hash: str,
        session: UserSessionRecord,
        *,
        now: datetime,
    ) -> UserRecord | None: ...

    async def update_preferences(
        self,
        user_id: UUID,
        *,
        reply_email_enabled: bool,
        now: datetime,
    ) -> UserRecord | None: ...

    async def delete_account(
        self,
        user_id: UUID,
        expected_password_hash: str,
        *,
        now: datetime,
    ) -> bool: ...


class UserAuthOperations(Protocol):
    async def issue_challenge(self) -> str: ...

    async def register(self, email: str, username: str, password: str, challenge: str) -> None: ...

    async def verify_email(self, token: str, challenge: str) -> NewUserSession: ...

    async def login(self, email: str, password: str, challenge: str) -> NewUserSession: ...

    async def authenticate(self, session_token: str) -> UserSessionRecord | None: ...

    def csrf_is_valid(self, session: UserSessionRecord, submitted_token: str) -> bool: ...

    async def logout(self, session: UserSessionRecord) -> None: ...

    async def request_password_reset(self, email: str, challenge: str) -> None: ...

    async def reset_password(self, token: str, password: str, challenge: str) -> NewUserSession: ...

    async def update_username(self, session: UserSessionRecord, username: str) -> CurrentUser: ...

    async def update_password(
        self,
        session: UserSessionRecord,
        current_password: str,
        password: str,
    ) -> NewUserSession: ...

    async def update_preferences(
        self, session: UserSessionRecord, *, reply_email_enabled: bool
    ) -> CurrentUser: ...

    async def delete_account(self, session: UserSessionRecord, password: str) -> None: ...


class UserAuthService:
    def __init__(
        self,
        repository: UserAuthRepository,
        rate_limiter: RateLimiter,
        token_signer: EmailTokenSigner,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
        uuid_factory: Callable[[], UUID] = uuid.uuid4,
    ) -> None:
        self._repository = repository
        self._rate_limiter = rate_limiter
        self._token_signer = token_signer
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._uuid_factory = uuid_factory
        self._password_hash = PasswordHash.recommended()
        self._dummy_password_hash = self._password_hash.hash(secrets.token_urlsafe(32))

    async def issue_challenge(self) -> str:
        now = self._clock()
        challenge = secrets.token_urlsafe(32)
        await self._repository.create_challenge(
            token_hash(challenge),
            created_at=now,
            expires_at=now + CHALLENGE_LIFETIME,
        )
        return challenge

    async def register(self, email: str, username: str, password: str, challenge: str) -> None:
        await self._consume_challenge(challenge)
        if not self._settings.user_registration_enabled:
            raise RegistrationClosed
        normalized_email, display_email = normalize_email(email)
        await self._consume_rate_limit(
            "register", normalized_email, limit=5, window=timedelta(hours=1)
        )
        existing = await self._repository.find_user_by_email(normalized_email)
        if existing is not None and existing.status != UserStatus.PENDING_VERIFICATION:
            return

        display_username, normalized_username = normalize_username(username)
        validate_password(password)
        excluding = existing.id if existing is not None else None
        if not await self._repository.username_is_available(
            normalized_username, excluding_user_id=excluding
        ):
            raise UsernameUnavailable
        if existing is not None:
            await self._consume_rate_limit(
                "resend_verification",
                normalized_email,
                limit=3,
                window=timedelta(hours=1),
            )

        now = self._clock()
        user = UserRecord(
            id=existing.id if existing is not None else self._uuid_factory(),
            email=display_email,
            normalized_email=normalized_email,
            username=display_username,
            normalized_username=normalized_username,
            password_hash=self._password_hash.hash(password),
            status=UserStatus.PENDING_VERIFICATION,
            email_verified_at=None,
            first_comment_approved_at=None,
            reply_email_enabled=True,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
            username_changed_at=existing.username_changed_at if existing is not None else None,
        )
        token_id, digest = self._issue_token(UserTokenPurpose.VERIFY_EMAIL)
        await self._repository.register_user(
            user,
            token_id=token_id,
            token_hash=digest,
            token_expires_at=now + VERIFY_EMAIL_LIFETIME,
            email_template="verify_email",
            email_payload={"username": display_username},
            now=now,
        )

    async def verify_email(self, token: str, challenge: str) -> NewUserSession:
        await self._consume_challenge(challenge)
        now = self._clock()
        await self._consume_rate_limit(
            "verify_email", token_hash(token), limit=10, window=timedelta(hours=1)
        )
        token_id, digest = self._validate_token(token, UserTokenPurpose.VERIFY_EMAIL)
        session_token, stored = self._new_session(UUID(int=0))
        activated = await self._repository.activate_user_and_create_session(
            token_id, digest, stored, now=now
        )
        if activated is None:
            raise TokenInvalid
        current, stored = activated
        return NewUserSession(
            session_token=session_token,
            csrf_token=stored.csrf_token,
            expires_at=stored.expires_at,
            current_user=current,
        )

    async def login(self, email: str, password: str, challenge: str) -> NewUserSession:
        await self._consume_challenge(challenge)
        normalized_email, _ = normalize_email(email)
        await self._consume_rate_limit(
            "login", normalized_email, limit=5, window=timedelta(minutes=15)
        )
        user = await self._repository.find_user_by_email(normalized_email)
        stored_hash = user.password_hash if user is not None else self._dummy_password_hash
        password_matches = self._password_hash.verify(password, stored_hash)
        if user is None or not password_matches or user.status == UserStatus.PENDING_VERIFICATION:
            raise CredentialsInvalid
        if user.status == UserStatus.SUSPENDED:
            raise AccountSuspended
        return await self._create_session(user)

    async def authenticate(self, session_token: str) -> UserSessionRecord | None:
        if not session_token:
            return None
        session_hash = token_hash(session_token)
        result = await self._repository.get_session(session_hash, now=self._clock())
        if result is None:
            return None
        session, user = result
        if user.status != UserStatus.ACTIVE:
            await self._repository.delete_session(session_hash)
            return None
        return UserSessionRecord(
            token_hash=session.token_hash,
            user_id=session.user_id,
            csrf_token=session.csrf_token,
            expires_at=session.expires_at,
            current_user=to_current_user(user),
        )

    def csrf_is_valid(self, session: UserSessionRecord, submitted_token: str) -> bool:
        return bool(submitted_token) and hmac.compare_digest(session.csrf_token, submitted_token)

    async def logout(self, session: UserSessionRecord) -> None:
        await self._repository.delete_session(session.token_hash)

    async def request_password_reset(self, email: str, challenge: str) -> None:
        await self._consume_challenge(challenge)
        normalized_email, _ = normalize_email(email)
        await self._consume_rate_limit(
            "password_reset_request", normalized_email, limit=3, window=timedelta(minutes=15)
        )
        user = await self._repository.find_user_by_email(normalized_email)
        if user is None or user.status != UserStatus.ACTIVE:
            return
        now = self._clock()
        token_id, digest = self._issue_token(UserTokenPurpose.RESET_PASSWORD)
        await self._repository.create_user_token(
            user.id,
            UserTokenPurpose.RESET_PASSWORD,
            token_id=token_id,
            token_hash=digest,
            expires_at=now + PASSWORD_RESET_LIFETIME,
            email_template="reset_password",
            recipient=user.email,
            email_payload={"username": user.username},
            now=now,
        )

    async def reset_password(self, token: str, password: str, challenge: str) -> NewUserSession:
        await self._consume_challenge(challenge)
        validate_password(password)
        now = self._clock()
        await self._consume_rate_limit(
            "password_reset", token_hash(token), limit=5, window=timedelta(hours=1)
        )
        token_id, digest = self._validate_token(token, UserTokenPurpose.RESET_PASSWORD)
        session_token, stored = self._new_session(UUID(int=0))
        reset = await self._repository.reset_password_and_create_session(
            token_id,
            digest,
            self._password_hash.hash(password),
            stored,
            now=now,
        )
        if reset is None:
            raise TokenInvalid
        current, stored = reset
        return NewUserSession(
            session_token=session_token,
            csrf_token=stored.csrf_token,
            expires_at=stored.expires_at,
            current_user=current,
        )

    async def update_username(self, session: UserSessionRecord, username: str) -> CurrentUser:
        await self._consume_account_rate_limit(session.user_id)
        await self._active_user(session)
        display, normalized = normalize_username(username)
        if not await self._repository.username_is_available(
            normalized, excluding_user_id=session.user_id
        ):
            raise UsernameUnavailable
        now = self._clock()
        updated = await self._repository.update_username(
            session.user_id,
            display,
            normalized,
            now=now,
            changed_after=now - USERNAME_CHANGE_COOLDOWN,
        )
        if updated is None:
            raise UsernameChangeTooSoon
        return to_current_user(updated)

    async def update_password(
        self,
        session: UserSessionRecord,
        current_password: str,
        password: str,
    ) -> NewUserSession:
        await self._consume_account_rate_limit(session.user_id)
        validate_password(password)
        user = await self._active_user(session)
        if not self._password_hash.verify(current_password, user.password_hash):
            raise CredentialsInvalid
        now = self._clock()
        session_token, stored = self._new_session(user.id)
        updated = await self._repository.update_password(
            user.id,
            user.password_hash,
            self._password_hash.hash(password),
            stored,
            now=now,
        )
        if updated is None:
            raise CredentialsInvalid
        return NewUserSession(
            session_token=session_token,
            csrf_token=stored.csrf_token,
            expires_at=stored.expires_at,
            current_user=to_current_user(updated),
        )

    async def update_preferences(
        self, session: UserSessionRecord, *, reply_email_enabled: bool
    ) -> CurrentUser:
        await self._consume_account_rate_limit(session.user_id)
        await self._active_user(session)
        updated = await self._repository.update_preferences(
            session.user_id,
            reply_email_enabled=reply_email_enabled,
            now=self._clock(),
        )
        if updated is None:
            raise CredentialsInvalid
        return to_current_user(updated)

    async def delete_account(self, session: UserSessionRecord, password: str) -> None:
        await self._consume_account_rate_limit(session.user_id)
        user = await self._active_user(session)
        if not self._password_hash.verify(password, user.password_hash):
            raise CredentialsInvalid
        if not await self._repository.delete_account(
            user.id,
            user.password_hash,
            now=self._clock(),
        ):
            raise CredentialsInvalid

    async def _consume_challenge(self, challenge: str) -> None:
        if not challenge or not await self._repository.consume_challenge(
            token_hash(challenge), now=self._clock()
        ):
            raise ChallengeInvalid

    async def _consume_rate_limit(
        self, action: str, subject: str, *, limit: int, window: timedelta
    ) -> None:
        if not await self._rate_limiter.consume(
            action, subject, limit=limit, window=window, now=self._clock()
        ):
            raise RateLimitExceeded

    async def _consume_account_rate_limit(self, user_id: UUID) -> None:
        await self._consume_rate_limit(
            "account_change", str(user_id), limit=10, window=timedelta(hours=1)
        )

    async def _active_user(self, session: UserSessionRecord) -> UserRecord:
        result = await self._repository.get_session(session.token_hash, now=self._clock())
        if result is None:
            raise CredentialsInvalid
        _, user = result
        if user.status == UserStatus.SUSPENDED:
            raise AccountSuspended
        if user.status != UserStatus.ACTIVE:
            raise CredentialsInvalid
        return user

    def _issue_token(self, purpose: UserTokenPurpose) -> tuple[UUID, str]:
        token_id = self._uuid_factory()
        raw = self._token_signer.issue(token_id, purpose)
        return token_id, self._token_signer.digest(raw)

    def _validate_token(self, raw: str, purpose: UserTokenPurpose) -> tuple[UUID, str]:
        try:
            token_id = UUID(raw.split(".", 1)[0])
        except (ValueError, IndexError):
            raise TokenInvalid from None
        digest = self._token_signer.digest(raw)
        if not self._token_signer.matches(token_id, purpose, digest, raw):
            raise TokenInvalid
        return token_id, digest

    async def _create_session(self, user: UserRecord) -> NewUserSession:
        now = self._clock()
        session_token, stored = self._new_session(user.id)
        current = await self._repository.create_session(
            stored,
            expected_password_hash=user.password_hash,
            created_at=now,
        )
        if current is None:
            raise CredentialsInvalid
        return NewUserSession(
            session_token=session_token,
            csrf_token=stored.csrf_token,
            expires_at=stored.expires_at,
            current_user=to_current_user(current),
        )

    def _new_session(self, user_id: UUID) -> tuple[str, UserSessionRecord]:
        session_token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = self._clock() + timedelta(seconds=self._settings.user_session_lifetime_seconds)
        stored = UserSessionRecord(
            token_hash=token_hash(session_token),
            user_id=user_id,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
        return session_token, stored


def normalize_email(value: str) -> tuple[str, str]:
    try:
        validated = validate_email(value.strip(), check_deliverability=False)
    except EmailNotValidError as error:
        raise ValueError("invalid email") from error
    display = validated.normalized
    return display.casefold(), display


def normalize_username(value: str) -> tuple[str, str]:
    display = unicodedata.normalize("NFKC", value.strip())
    normalized = display.casefold()
    if (
        not 3 <= len(display) <= 30
        or not all(character.isalnum() or character in {"_", "-"} for character in display)
        or len(normalized) > 30
    ):
        raise ValueError("invalid username")
    return display, normalized


def validate_password(value: str) -> None:
    if not 8 <= len(value) <= 200:
        raise ValueError("invalid password")


def to_current_user(user: UserRecord) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        email=user.email,
        username=user.username,
        email_verified_at=user.email_verified_at,
        first_comment_approved_at=user.first_comment_approved_at,
        reply_email_enabled=user.reply_email_enabled,
    )
