"""Private site-user notifications and reply-email unsubscribe operations."""

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from typing import Protocol
from uuid import UUID

from sqlalchemy import Select, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from company_api.email_tokens import EmailTokenSigner
from company_api.models import (
    Comment,
    Document,
    Notification,
    NotificationType,
    User,
    UserAuthChallenge,
    UserToken,
    UserTokenPurpose,
)
from company_api.user_auth import token_hash
from company_api.user_schemas import NotificationPage, NotificationRead


class NotificationNotFound(Exception):
    """The notification does not belong to the current user."""


class UnsubscribeTokenInvalid(Exception):
    """The unsubscribe challenge or email token is no longer valid."""


@dataclass(frozen=True, slots=True)
class NotificationRecord:
    id: UUID
    recipient_id: UUID
    type: NotificationType
    company_id: UUID
    document_id: UUID
    comment_id: UUID
    actor_username: str | None
    comment_body: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationRepository(Protocol):
    async def list(self, recipient_id: UUID) -> list[NotificationRecord]: ...

    async def mark_read(
        self, notification_id: UUID, recipient_id: UUID, *, now: datetime
    ) -> NotificationRecord | None: ...

    async def mark_all_read(self, recipient_id: UUID, *, now: datetime) -> None: ...

    async def unsubscribe(
        self,
        token_id: UUID,
        token_digest: str,
        challenge_hash: str,
        *,
        now: datetime,
    ) -> bool: ...


class NotificationOperations(Protocol):
    async def list(self, user_id: UUID) -> NotificationPage: ...

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> NotificationRead: ...

    async def mark_all_read(self, user_id: UUID) -> None: ...

    async def unsubscribe(self, token: str, challenge: str) -> None: ...


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepository,
        token_signer: EmailTokenSigner,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._token_signer = token_signer
        self._clock = clock or (lambda: datetime.now(UTC))

    async def list(self, user_id: UUID) -> NotificationPage:
        rows = await self._repository.list(user_id)
        ordered = sorted(
            rows,
            key=lambda row: (
                row.read_at is not None,
                -row.created_at.timestamp(),
                -row.id.int,
            ),
        )
        return NotificationPage(
            items=[_notification_read(row) for row in ordered],
            unread_count=sum(row.read_at is None for row in ordered),
        )

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> NotificationRead:
        row = await self._repository.mark_read(notification_id, user_id, now=self._clock())
        if row is None:
            raise NotificationNotFound
        return _notification_read(row)

    async def mark_all_read(self, user_id: UUID) -> None:
        await self._repository.mark_all_read(user_id, now=self._clock())

    async def unsubscribe(self, token: str, challenge: str) -> None:
        token_id, digest = _validate_unsubscribe_token(self._token_signer, token)
        if not challenge or not await self._repository.unsubscribe(
            token_id,
            digest,
            token_hash(challenge),
            now=self._clock(),
        ):
            raise UnsubscribeTokenInvalid


class SqlAlchemyNotificationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, recipient_id: UUID) -> list[NotificationRecord]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    _notification_select()
                    .where(Notification.recipient_id == recipient_id)
                    .order_by(
                        Notification.read_at.is_not(None),
                        Notification.created_at.desc(),
                        Notification.id.desc(),
                    )
                )
            ).all()
            return [_notification_record(*row) for row in rows]

    async def mark_read(
        self, notification_id: UUID, recipient_id: UUID, *, now: datetime
    ) -> NotificationRecord | None:
        async with self._session_factory() as session:
            notification = await session.scalar(
                select(Notification)
                .where(
                    Notification.id == notification_id,
                    Notification.recipient_id == recipient_id,
                )
                .with_for_update()
            )
            if notification is None:
                await session.commit()
                return None
            if notification.read_at is None:
                notification.read_at = now
            row = (
                await session.execute(
                    _notification_select().where(Notification.id == notification.id)
                )
            ).one()
            saved = _notification_record(*row)
            await session.commit()
            return saved

    async def mark_all_read(self, recipient_id: UUID, *, now: datetime) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(Notification)
                .where(
                    Notification.recipient_id == recipient_id,
                    Notification.read_at.is_(None),
                )
                .values(read_at=now)
            )
            await session.commit()

    async def unsubscribe(
        self,
        token_id: UUID,
        token_digest: str,
        challenge_hash: str,
        *,
        now: datetime,
    ) -> bool:
        async with self._session_factory() as session:
            consumed_challenge = (
                await session.execute(
                    delete(UserAuthChallenge)
                    .where(
                        UserAuthChallenge.token_hash == challenge_hash,
                        UserAuthChallenge.expires_at > now,
                    )
                    .returning(UserAuthChallenge.token_hash)
                )
            ).scalar_one_or_none()
            if consumed_challenge is None:
                await session.commit()
                return False

            token = await session.scalar(
                select(UserToken).where(UserToken.id == token_id).with_for_update()
            )
            if (
                token is None
                or token.purpose != UserTokenPurpose.UNSUBSCRIBE
                or token.consumed_at is not None
                or token.expires_at <= now
                or not hmac.compare_digest(token.token_hash, token_digest)
            ):
                await session.commit()
                return False
            user = await session.scalar(
                select(User).where(User.id == token.user_id).with_for_update()
            )
            if user is None:
                await session.commit()
                return False
            token.consumed_at = now
            user.reply_email_enabled = False
            user.updated_at = now
            await session.commit()
            return True


def _notification_select() -> Select[tuple[Notification, UUID, str | None, str]]:
    actor = aliased(User)
    return (
        select(Notification, Document.company_id, Comment.body, actor.username)
        .join(Document, Document.id == Notification.document_id)
        .join(Comment, Comment.id == Notification.comment_id)
        .outerjoin(actor, actor.id == Notification.actor_id)
    )


def _notification_record(
    notification: Notification,
    company_id: UUID,
    comment_body: str | None,
    actor_username: str | None,
) -> NotificationRecord:
    return NotificationRecord(
        id=notification.id,
        recipient_id=notification.recipient_id,
        type=notification.type,
        company_id=company_id,
        document_id=notification.document_id,
        comment_id=notification.comment_id,
        actor_username=actor_username,
        comment_body=comment_body,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


def _notification_read(row: NotificationRecord) -> NotificationRead:
    actor = escape(row.actor_username or "一位读者", quote=True)
    return NotificationRead(
        id=row.id,
        type=row.type,
        company_id=row.company_id,
        document_id=row.document_id,
        comment_id=row.comment_id,
        actor_username=escape(row.actor_username, quote=True) if row.actor_username else None,
        excerpt=_excerpt(row.comment_body),
        message=_notification_message(row.type, actor),
        created_at=row.created_at,
        read_at=row.read_at,
    )


def _notification_message(notification_type: NotificationType, actor: str) -> str:
    if notification_type == NotificationType.REPLY:
        return f"{actor} 回复了你的评论"
    if notification_type == NotificationType.COMMENT_APPROVED:
        return "你的评论已通过审核"
    return "你的评论未通过审核"


def _excerpt(value: str | None) -> str:
    text = " ".join((value or "").split())
    return escape(text[:280], quote=True)


def _validate_unsubscribe_token(signer: EmailTokenSigner, raw: str) -> tuple[UUID, str]:
    try:
        token_id = UUID(raw.split(".", 1)[0])
    except (ValueError, IndexError):
        raise UnsubscribeTokenInvalid from None
    digest = signer.digest(raw)
    if not signer.matches(token_id, UserTokenPurpose.UNSUBSCRIBE, digest, raw):
        raise UnsubscribeTokenInvalid
    return token_id, digest
