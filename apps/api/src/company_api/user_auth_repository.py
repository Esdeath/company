"""SQLAlchemy persistence for ordinary-user authentication and accounts."""

import hmac
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from company_api.models import (
    Comment,
    EmailOutbox,
    User,
    UserAuthChallenge,
    UserSession,
    UserStatus,
    UserToken,
    UserTokenPurpose,
)
from company_api.user_auth import (
    CurrentUser,
    UsernameUnavailable,
    UserRecord,
    UserSessionRecord,
)


class SqlAlchemyUserAuthRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_challenge(
        self,
        challenge_hash: str,
        *,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(UserAuthChallenge).where(UserAuthChallenge.expires_at <= created_at)
            )
            session.add(
                UserAuthChallenge(
                    token_hash=challenge_hash,
                    created_at=created_at,
                    expires_at=expires_at,
                )
            )
            await session.commit()

    async def consume_challenge(self, challenge_hash: str, *, now: datetime) -> bool:
        async with self._session_factory() as session:
            statement = (
                delete(UserAuthChallenge)
                .where(
                    UserAuthChallenge.token_hash == challenge_hash,
                    UserAuthChallenge.expires_at > now,
                )
                .returning(UserAuthChallenge.token_hash)
            )
            consumed = (await session.execute(statement)).scalar_one_or_none()
            await session.commit()
            return consumed is not None

    async def find_user_by_email(self, normalized_email: str) -> UserRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(User).where(User.normalized_email == normalized_email)
            )
            return _user_record(row) if row is not None else None

    async def username_is_available(
        self,
        normalized_username: str,
        *,
        excluding_user_id: UUID | None = None,
    ) -> bool:
        statement = select(User.id).where(User.normalized_username == normalized_username)
        if excluding_user_id is not None:
            statement = statement.where(User.id != excluding_user_id)
        async with self._session_factory() as session:
            return await session.scalar(statement) is None

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
        try:
            async with self._session_factory() as session:
                existing = await session.scalar(
                    select(User)
                    .where(User.normalized_email == user.normalized_email)
                    .with_for_update()
                )
                if existing is not None and existing.status != UserStatus.PENDING_VERIFICATION:
                    await session.commit()
                    return

                if existing is None:
                    stored = _new_user(user)
                    session.add(stored)
                else:
                    stored = existing
                    _copy_pending_user(stored, user)

                await self._replace_token_and_enqueue(
                    session,
                    user_id=stored.id,
                    purpose=UserTokenPurpose.VERIFY_EMAIL,
                    token_id=token_id,
                    token_hash=token_hash,
                    expires_at=token_expires_at,
                    template=email_template,
                    recipient=user.email,
                    payload=email_payload,
                    now=now,
                )
                await session.commit()
        except IntegrityError as error:
            constraint_name = _constraint_name(error)
            if constraint_name == "uq_users_normalized_email":
                return
            if constraint_name == "uq_users_normalized_username":
                raise UsernameUnavailable from error
            raise

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
        async with self._session_factory() as session:
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                await session.commit()
                return
            await self._replace_token_and_enqueue(
                session,
                user_id=user_id,
                purpose=purpose,
                token_id=token_id,
                token_hash=token_hash,
                expires_at=expires_at,
                template=email_template,
                recipient=recipient,
                payload=email_payload,
                now=now,
            )
            await session.commit()

    async def activate_user_and_create_session(
        self,
        token_id: UUID,
        token_digest: str,
        session_record: UserSessionRecord,
        *,
        now: datetime,
    ) -> tuple[CurrentUser, UserSessionRecord] | None:
        async with self._session_factory() as session:
            user_id = await self._token_owner_id(session, token_id)
            if user_id is None:
                await session.commit()
                return None
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                await session.commit()
                return None
            token = await self._locked_token(
                session,
                token_id,
                token_digest,
                UserTokenPurpose.VERIFY_EMAIL,
                user_id,
                now,
            )
            if token is None or not _token_matches(
                token,
                token_id=token_id,
                token_digest=token_digest,
                purpose=UserTokenPurpose.VERIFY_EMAIL,
                user_id=user_id,
                now=now,
            ):
                await session.commit()
                return None
            if user.status == UserStatus.SUSPENDED:
                await session.commit()
                return None

            token.consumed_at = now
            user.status = UserStatus.ACTIVE
            user.email_verified_at = now
            user.updated_at = now
            actual_session = _bind_session(session_record, user.id)
            session.add(_new_session(actual_session, created_at=now))
            current = _current_user(user)
            await session.commit()
            return current, actual_session

    async def create_session(
        self,
        record: UserSessionRecord,
        *,
        expected_password_hash: str,
        created_at: datetime,
    ) -> UserRecord | None:
        async with self._session_factory() as session:
            user = await session.scalar(
                select(User).where(User.id == record.user_id).with_for_update()
            )
            if (
                user is None
                or user.status != UserStatus.ACTIVE
                or not hmac.compare_digest(user.password_hash, expected_password_hash)
            ):
                await session.commit()
                return None
            await session.execute(delete(UserSession).where(UserSession.expires_at <= created_at))
            session.add(_new_session(record, created_at=created_at))
            result = _user_record(user)
            await session.commit()
            return result

    async def get_session(
        self,
        session_hash: str,
        *,
        now: datetime,
    ) -> tuple[UserSessionRecord, UserRecord] | None:
        async with self._session_factory() as session:
            statement = (
                select(UserSession, User)
                .join(User, User.id == UserSession.user_id)
                .where(
                    UserSession.token_hash == session_hash,
                    UserSession.expires_at > now,
                )
            )
            row = (await session.execute(statement)).one_or_none()
            if row is None:
                await session.execute(
                    delete(UserSession).where(
                        UserSession.token_hash == session_hash,
                        UserSession.expires_at <= now,
                    )
                )
                await session.commit()
                return None
            stored_session, user = row.tuple()
            return _session_record(stored_session), _user_record(user)

    async def delete_session(self, session_hash: str) -> None:
        async with self._session_factory() as session:
            await session.execute(delete(UserSession).where(UserSession.token_hash == session_hash))
            await session.commit()

    async def reset_password_and_create_session(
        self,
        token_id: UUID,
        token_digest: str,
        password_hash: str,
        session_record: UserSessionRecord,
        *,
        now: datetime,
    ) -> tuple[CurrentUser, UserSessionRecord] | None:
        async with self._session_factory() as session:
            user_id = await self._token_owner_id(session, token_id)
            if user_id is None:
                await session.commit()
                return None
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                await session.commit()
                return None
            token = await self._locked_token(
                session,
                token_id,
                token_digest,
                UserTokenPurpose.RESET_PASSWORD,
                user_id,
                now,
            )
            if token is None or not _token_matches(
                token,
                token_id=token_id,
                token_digest=token_digest,
                purpose=UserTokenPurpose.RESET_PASSWORD,
                user_id=user_id,
                now=now,
            ):
                await session.commit()
                return None
            if user.status != UserStatus.ACTIVE:
                await session.commit()
                return None

            token.consumed_at = now
            user.password_hash = password_hash
            user.updated_at = now
            await session.execute(delete(UserSession).where(UserSession.user_id == user.id))
            actual_session = _bind_session(session_record, user.id)
            session.add(_new_session(actual_session, created_at=now))
            current = _current_user(user)
            await session.commit()
            return current, actual_session

    async def update_username(
        self,
        user_id: UUID,
        username: str,
        normalized_username: str,
        *,
        now: datetime,
        changed_after: datetime,
    ) -> UserRecord | None:
        try:
            async with self._session_factory() as session:
                user = await session.scalar(
                    select(User).where(User.id == user_id).with_for_update()
                )
                if user is None or (
                    user.username_changed_at is not None
                    and user.username_changed_at > changed_after
                ):
                    await session.commit()
                    return None
                user.username = username
                user.normalized_username = normalized_username
                user.username_changed_at = now
                user.updated_at = now
                result = _user_record(user)
                await session.commit()
                return result
        except IntegrityError as error:
            if _constraint_name(error) == "uq_users_normalized_username":
                raise UsernameUnavailable from error
            raise

    async def update_password(
        self,
        user_id: UUID,
        expected_password_hash: str,
        password_hash: str,
        session_record: UserSessionRecord,
        *,
        now: datetime,
    ) -> UserRecord | None:
        async with self._session_factory() as session:
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if (
                user is None
                or user.status != UserStatus.ACTIVE
                or not hmac.compare_digest(user.password_hash, expected_password_hash)
            ):
                await session.commit()
                return None
            user.password_hash = password_hash
            user.updated_at = now
            await session.execute(delete(UserSession).where(UserSession.user_id == user_id))
            session.add(_new_session(session_record, created_at=now))
            result = _user_record(user)
            await session.commit()
            return result

    async def update_preferences(
        self,
        user_id: UUID,
        *,
        reply_email_enabled: bool,
        now: datetime,
    ) -> UserRecord | None:
        async with self._session_factory() as session:
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None or user.status != UserStatus.ACTIVE:
                await session.commit()
                return None
            user.reply_email_enabled = reply_email_enabled
            user.updated_at = now
            result = _user_record(user)
            await session.commit()
            return result

    async def delete_account(self, user_id: UUID, *, now: datetime) -> bool:
        del now
        async with self._session_factory() as session:
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                await session.commit()
                return False
            await session.execute(
                update(Comment).where(Comment.author_id == user_id).values(author_id=None)
            )
            await session.delete(user)
            await session.commit()
            return True

    async def _replace_token_and_enqueue(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        purpose: UserTokenPurpose,
        token_id: UUID,
        token_hash: str,
        expires_at: datetime,
        template: str,
        recipient: str,
        payload: dict[str, object],
        now: datetime,
    ) -> None:
        superseded_token_ids = select(UserToken.id).where(
            UserToken.user_id == user_id,
            UserToken.purpose == purpose,
            UserToken.consumed_at.is_(None),
        )
        await session.execute(
            delete(EmailOutbox).where(
                EmailOutbox.token_id.in_(superseded_token_ids),
                EmailOutbox.sent_at.is_(None),
            )
        )
        await session.execute(
            update(UserToken)
            .where(
                UserToken.user_id == user_id,
                UserToken.purpose == purpose,
                UserToken.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        token = UserToken(
            id=token_id,
            token_hash=token_hash,
            purpose=purpose,
            user_id=user_id,
            created_at=now,
            expires_at=expires_at,
            consumed_at=None,
        )
        session.add(token)
        await session.flush()
        session.add(
            EmailOutbox(
                token_id=token_id,
                template=template,
                recipient=recipient,
                payload=payload,
                attempts=0,
                available_at=now,
                lease_id=None,
                lease_expires_at=None,
                sent_at=None,
                last_error=None,
            )
        )

    async def _locked_token(
        self,
        session: AsyncSession,
        token_id: UUID,
        token_digest: str,
        purpose: UserTokenPurpose,
        user_id: UUID,
        now: datetime,
    ) -> UserToken | None:
        token: UserToken | None = await session.scalar(
            select(UserToken)
            .where(
                UserToken.id == token_id,
                UserToken.token_hash == token_digest,
                UserToken.purpose == purpose,
                UserToken.user_id == user_id,
                UserToken.consumed_at.is_(None),
                UserToken.expires_at > now,
            )
            .with_for_update()
        )
        return token

    async def _token_owner_id(self, session: AsyncSession, token_id: UUID) -> UUID | None:
        user_id: UUID | None = await session.scalar(
            select(UserToken.user_id).where(UserToken.id == token_id)
        )
        return user_id


def _new_user(record: UserRecord) -> User:
    return User(
        id=record.id,
        email=record.email,
        normalized_email=record.normalized_email,
        username=record.username,
        normalized_username=record.normalized_username,
        password_hash=record.password_hash,
        status=record.status,
        email_verified_at=record.email_verified_at,
        first_comment_approved_at=record.first_comment_approved_at,
        reply_email_enabled=record.reply_email_enabled,
        created_at=record.created_at,
        updated_at=record.updated_at,
        username_changed_at=record.username_changed_at,
    )


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    return constraint_name if isinstance(constraint_name, str) else None


def _copy_pending_user(stored: User, record: UserRecord) -> None:
    stored.email = record.email
    stored.normalized_email = record.normalized_email
    stored.username = record.username
    stored.normalized_username = record.normalized_username
    stored.password_hash = record.password_hash
    stored.updated_at = record.updated_at


def _new_session(record: UserSessionRecord, *, created_at: datetime) -> UserSession:
    return UserSession(
        token_hash=record.token_hash,
        user_id=record.user_id,
        csrf_token=record.csrf_token,
        created_at=created_at,
        expires_at=record.expires_at,
    )


def _bind_session(record: UserSessionRecord, user_id: UUID) -> UserSessionRecord:
    return UserSessionRecord(
        token_hash=record.token_hash,
        user_id=user_id,
        csrf_token=record.csrf_token,
        expires_at=record.expires_at,
    )


def _session_record(row: UserSession) -> UserSessionRecord:
    return UserSessionRecord(
        token_hash=row.token_hash,
        user_id=row.user_id,
        csrf_token=row.csrf_token,
        expires_at=row.expires_at,
    )


def _user_record(row: User) -> UserRecord:
    return UserRecord(
        id=row.id,
        email=row.email,
        normalized_email=row.normalized_email,
        username=row.username,
        normalized_username=row.normalized_username,
        password_hash=row.password_hash,
        status=row.status,
        email_verified_at=row.email_verified_at,
        first_comment_approved_at=row.first_comment_approved_at,
        reply_email_enabled=row.reply_email_enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
        username_changed_at=row.username_changed_at,
    )


def _current_user(row: User) -> CurrentUser:
    return CurrentUser(
        id=row.id,
        email=row.email,
        username=row.username,
        email_verified_at=row.email_verified_at,
        first_comment_approved_at=row.first_comment_approved_at,
        reply_email_enabled=row.reply_email_enabled,
    )


def _token_matches(
    token: UserToken,
    *,
    token_id: UUID,
    token_digest: str,
    purpose: UserTokenPurpose,
    user_id: UUID,
    now: datetime,
) -> bool:
    return (
        token.id == token_id
        and token.user_id == user_id
        and token.purpose == purpose
        and token.consumed_at is None
        and token.expires_at > now
        and hmac.compare_digest(token.token_hash, token_digest)
    )
