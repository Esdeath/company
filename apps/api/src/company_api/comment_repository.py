"""PostgreSQL persistence for public comments, author actions, and reports."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from company_api.comment_notifications import add_reply_publication_side_effects
from company_api.models import (
    Comment,
    CommentReport,
    CommentStatus,
    Document,
    ReportStatus,
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


@dataclass(frozen=True, slots=True)
class NewCommentReportRecord:
    id: UUID
    comment_id: UUID
    reporter_id: UUID
    reason: str
    details: str | None
    created_at: datetime


class ParentCommentInvalid(Exception):
    """The locked reply target or its root cannot receive a reply."""


class DuplicateCommentReportError(Exception):
    """The reporter already reported the comment."""


class InvalidCommentReportError(Exception):
    """The comment cannot be reported by this user."""


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

    async def update_owned_comment(
        self, comment_id: UUID, author_id: UUID, body: str, *, now: datetime
    ) -> CommentRecord | None: ...

    async def delete_owned_comment(
        self, comment_id: UUID, author_id: UUID, *, now: datetime
    ) -> CommentRecord | None: ...

    async def create_report(self, record: NewCommentReportRecord) -> None: ...


class SqlAlchemyCommentRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        unsubscribe_token_factory: Callable[[], tuple[UUID, str]],
    ) -> None:
        self._session_factory = session_factory
        self._unsubscribe_token_factory = unsubscribe_token_factory

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
                reply_to_id=locked_target.id if locked_target is not None else None,
                body=record.body,
                status=record.status,
                created_at=record.created_at,
            )
            session.add(comment)
            if record.status == CommentStatus.PUBLISHED:
                await add_reply_publication_side_effects(
                    session,
                    comment_id=record.id,
                    document_id=record.document_id,
                    actor_id=record.author_id,
                    actor_username=record.author_username,
                    reply_target=locked_target,
                    created_at=record.created_at,
                    unsubscribe_token_factory=self._unsubscribe_token_factory,
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

    async def update_owned_comment(
        self, comment_id: UUID, author_id: UUID, body: str, *, now: datetime
    ) -> CommentRecord | None:
        async with self._session_factory() as session:
            comment = await session.scalar(
                select(Comment)
                .where(
                    Comment.id == comment_id,
                    Comment.author_id == author_id,
                    Comment.status.in_([CommentStatus.PENDING, CommentStatus.PUBLISHED]),
                )
                .with_for_update()
            )
            if comment is None:
                return None
            comment.body = body
            comment.edited_at = now
            username = await session.scalar(select(User.username).where(User.id == author_id))
            await session.flush()
            saved = _comment_record(comment, username)
            await session.commit()
            return saved

    async def delete_owned_comment(
        self, comment_id: UUID, author_id: UUID, *, now: datetime
    ) -> CommentRecord | None:
        async with self._session_factory() as session:
            comment = await session.scalar(
                select(Comment)
                .where(
                    Comment.id == comment_id,
                    Comment.author_id == author_id,
                    Comment.status.in_([CommentStatus.PENDING, CommentStatus.PUBLISHED]),
                )
                .with_for_update()
            )
            if comment is None:
                return None
            comment.status = CommentStatus.DELETED
            comment.body = None
            comment.deleted_at = now
            username = await session.scalar(select(User.username).where(User.id == author_id))
            await session.flush()
            saved = _comment_record(comment, username)
            await session.commit()
            return saved

    async def create_report(self, record: NewCommentReportRecord) -> None:
        async with self._session_factory() as session:
            comment = await session.scalar(
                select(Comment).where(Comment.id == record.comment_id).with_for_update()
            )
            if (
                comment is None
                or comment.status != CommentStatus.PUBLISHED
                or comment.author_id == record.reporter_id
            ):
                raise InvalidCommentReportError
            session.add(
                CommentReport(
                    id=record.id,
                    comment_id=record.comment_id,
                    reporter_id=record.reporter_id,
                    reason=record.reason,
                    details=record.details,
                    status=ReportStatus.OPEN,
                    created_at=record.created_at,
                )
            )
            try:
                await session.flush()
            except IntegrityError as error:
                await session.rollback()
                raise DuplicateCommentReportError from error
            await session.commit()


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
