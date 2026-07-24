"""PostgreSQL persistence for public article comments."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from company_api.models import (
    Comment,
    CommentStatus,
    Document,
    EmailOutbox,
    Notification,
    NotificationType,
    User,
)


@dataclass(frozen=True, slots=True)
class CommentCursor:
    created_at: datetime
    id: UUID


@dataclass(frozen=True, slots=True)
class CommentRecord:
    id: UUID
    document_id: UUID
    author_id: UUID | None
    author_username: str | None
    parent_id: UUID | None
    body: str | None
    status: CommentStatus
    created_at: datetime
    edited_at: datetime | None


@dataclass(frozen=True, slots=True)
class ParentCommentRecord:
    id: UUID
    document_id: UUID
    author_id: UUID | None
    parent_id: UUID | None
    status: CommentStatus


@dataclass(frozen=True, slots=True)
class NewCommentRecord:
    id: UUID
    document_id: UUID
    author_id: UUID
    author_username: str
    parent_id: UUID | None
    body: str
    status: CommentStatus
    created_at: datetime


class ParentCommentInvalid(Exception):
    """The locked reply target or its root cannot receive a reply."""


class CommentRepository(Protocol):
    async def document_exists(self, document_id: UUID) -> bool: ...

    async def get_parent(self, comment_id: UUID) -> ParentCommentRecord | None: ...

    async def create_comment(
        self,
        record: NewCommentRecord,
        *,
        reply_target: ParentCommentRecord | None,
    ) -> CommentRecord: ...

    async def list_top_level(
        self,
        document_id: UUID,
        *,
        cursor: CommentCursor | None,
        limit: int,
    ) -> list[CommentRecord]: ...

    async def list_replies(self, root_ids: list[UUID]) -> list[CommentRecord]: ...

    async def list_pending(self, document_id: UUID, viewer_id: UUID) -> list[CommentRecord]: ...

    async def count_published(self, document_id: UUID) -> int: ...

    async def get_comment(self, comment_id: UUID) -> CommentRecord | None: ...


class SqlAlchemyCommentRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def document_exists(self, document_id: UUID) -> bool:
        async with self._session_factory() as session:
            return bool(await session.scalar(select(exists().where(Document.id == document_id))))

    async def get_parent(self, comment_id: UUID) -> ParentCommentRecord | None:
        async with self._session_factory() as session:
            comment = await session.get(Comment, comment_id)
            return _parent_record(comment) if comment is not None else None

    async def create_comment(
        self,
        record: NewCommentRecord,
        *,
        reply_target: ParentCommentRecord | None,
    ) -> CommentRecord:
        async with self._session_factory() as session:
            locked_target, locked_root = await _lock_reply_context(
                session,
                record,
                reply_target,
            )
            comment = Comment(
                id=record.id,
                document_id=record.document_id,
                author_id=record.author_id,
                parent_id=locked_root.id if locked_root is not None else None,
                body=record.body,
                status=record.status,
                created_at=record.created_at,
            )
            session.add(comment)
            if (
                record.status == CommentStatus.PUBLISHED
                and locked_target is not None
                and locked_target.author_id is not None
                and locked_target.author_id != record.author_id
            ):
                recipient = await session.get(User, locked_target.author_id)
                if recipient is not None:
                    session.add(
                        Notification(
                            recipient_id=recipient.id,
                            type=NotificationType.REPLY,
                            actor_id=record.author_id,
                            comment_id=record.id,
                            document_id=record.document_id,
                            created_at=record.created_at,
                        )
                    )
                    if recipient.reply_email_enabled:
                        document = await session.get(Document, record.document_id)
                        payload: dict[str, object] = {
                            "username": recipient.username,
                            "actor_username": record.author_username,
                            "document_id": str(record.document_id),
                            "comment_id": str(record.id),
                        }
                        if document is not None:
                            payload["company_id"] = str(document.company_id)
                        session.add(
                            EmailOutbox(
                                template="comment_reply",
                                recipient=recipient.email,
                                payload=payload,
                                available_at=record.created_at,
                            )
                        )
            await session.flush()
            saved = _comment_record(comment, record.author_username)
            await session.commit()
            return saved

    async def list_top_level(
        self,
        document_id: UUID,
        *,
        cursor: CommentCursor | None,
        limit: int,
    ) -> list[CommentRecord]:
        async with self._session_factory() as session:
            child = aliased(Comment)
            has_published_reply = exists().where(
                child.parent_id == Comment.id,
                child.status == CommentStatus.PUBLISHED,
            )
            statement = _comment_select().where(
                Comment.document_id == document_id,
                Comment.parent_id.is_(None),
                or_(
                    Comment.status == CommentStatus.PUBLISHED,
                    and_(Comment.status == CommentStatus.DELETED, has_published_reply),
                ),
            )
            if cursor is not None:
                statement = statement.where(
                    or_(
                        Comment.created_at < cursor.created_at,
                        and_(Comment.created_at == cursor.created_at, Comment.id < cursor.id),
                    )
                )
            rows = (
                await session.execute(
                    statement.order_by(Comment.created_at.desc(), Comment.id.desc()).limit(limit)
                )
            ).all()
            return [_comment_record(comment, username) for comment, username in rows]

    async def list_replies(self, root_ids: list[UUID]) -> list[CommentRecord]:
        if not root_ids:
            return []
        async with self._session_factory() as session:
            statement = (
                _comment_select()
                .where(
                    Comment.parent_id.in_(root_ids),
                    Comment.status == CommentStatus.PUBLISHED,
                )
                .order_by(Comment.created_at.asc(), Comment.id.asc())
            )
            rows = (await session.execute(statement)).all()
            return [_comment_record(comment, username) for comment, username in rows]

    async def list_pending(self, document_id: UUID, viewer_id: UUID) -> list[CommentRecord]:
        async with self._session_factory() as session:
            statement = (
                _comment_select()
                .where(
                    Comment.document_id == document_id,
                    Comment.author_id == viewer_id,
                    Comment.status == CommentStatus.PENDING,
                )
                .order_by(Comment.created_at.desc(), Comment.id.desc())
            )
            rows = (await session.execute(statement)).all()
            return [_comment_record(comment, username) for comment, username in rows]

    async def count_published(self, document_id: UUID) -> int:
        async with self._session_factory() as session:
            statement = (
                select(func.count())
                .select_from(Comment)
                .where(
                    Comment.document_id == document_id,
                    Comment.status == CommentStatus.PUBLISHED,
                )
            )
            return int(await session.scalar(statement) or 0)

    async def get_comment(self, comment_id: UUID) -> CommentRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(_comment_select().where(Comment.id == comment_id))
            ).one_or_none()
            if row is None:
                return None
            comment, username = row
            return _comment_record(comment, username)


def _comment_select() -> Select[tuple[Comment, str]]:
    return select(Comment, User.username).outerjoin(User, User.id == Comment.author_id)


async def _lock_reply_context(
    session: AsyncSession,
    record: NewCommentRecord,
    reply_target: ParentCommentRecord | None,
) -> tuple[Comment | None, Comment | None]:
    if reply_target is None:
        if record.parent_id is not None:
            raise ParentCommentInvalid
        return None, None

    direct = await session.scalar(
        select(Comment).where(Comment.id == reply_target.id).with_for_update()
    )
    if (
        direct is None
        or direct.document_id != record.document_id
        or direct.status != CommentStatus.PUBLISHED
    ):
        raise ParentCommentInvalid

    root = direct
    if direct.parent_id is not None:
        locked_root = await session.scalar(
            select(Comment).where(Comment.id == direct.parent_id).with_for_update()
        )
        if locked_root is None:
            raise ParentCommentInvalid
        root = locked_root
    if (
        root.document_id != record.document_id
        or root.parent_id is not None
        or root.status != CommentStatus.PUBLISHED
    ):
        raise ParentCommentInvalid
    return direct, root


def _comment_record(comment: Comment, username: str | None) -> CommentRecord:
    return CommentRecord(
        id=comment.id,
        document_id=comment.document_id,
        author_id=comment.author_id,
        author_username=username,
        parent_id=comment.parent_id,
        body=comment.body,
        status=comment.status,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
    )


def _parent_record(comment: Comment) -> ParentCommentRecord:
    return ParentCommentRecord(
        id=comment.id,
        document_id=comment.document_id,
        author_id=comment.author_id,
        parent_id=comment.parent_id,
        status=comment.status,
    )
