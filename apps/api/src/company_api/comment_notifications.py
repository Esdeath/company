"""Shared reply notification and email-outbox construction."""

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from company_api.models import (
    Comment,
    Document,
    EmailOutbox,
    Notification,
    NotificationType,
    User,
    UserToken,
    UserTokenPurpose,
)

UNSUBSCRIBE_LIFETIME = timedelta(days=30)


async def add_reply_publication_side_effects(
    session: AsyncSession,
    *,
    comment_id: UUID,
    document_id: UUID,
    actor_id: UUID,
    actor_username: str,
    reply_target: Comment | None,
    created_at: datetime,
    unsubscribe_token_factory: Callable[[], tuple[UUID, str]],
) -> None:
    if reply_target is None or reply_target.author_id is None or reply_target.author_id == actor_id:
        return
    recipient = await session.get(User, reply_target.author_id)
    if recipient is None:
        return
    session.add(
        Notification(
            recipient_id=recipient.id,
            type=NotificationType.REPLY,
            actor_id=actor_id,
            comment_id=comment_id,
            document_id=document_id,
            created_at=created_at,
        )
    )
    if not recipient.reply_email_enabled:
        return
    token_id, token_hash = unsubscribe_token_factory()
    session.add(
        UserToken(
            id=token_id,
            token_hash=token_hash,
            purpose=UserTokenPurpose.UNSUBSCRIBE,
            user_id=recipient.id,
            created_at=created_at,
            expires_at=created_at + UNSUBSCRIBE_LIFETIME,
        )
    )
    document = await session.get(Document, document_id)
    payload: dict[str, object] = {
        "username": recipient.username,
        "actor_username": actor_username,
        "document_id": str(document_id),
        "comment_id": str(comment_id),
    }
    if document is not None:
        payload["company_id"] = str(document.company_id)
    session.add(
        EmailOutbox(
            token_id=token_id,
            template="comment_reply",
            recipient=recipient.email,
            payload=payload,
            available_at=created_at,
        )
    )
