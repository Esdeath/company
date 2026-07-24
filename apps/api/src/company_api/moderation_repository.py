"""PostgreSQL persistence for comment moderation and site-user administration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import Select, and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from company_api.comment_notifications import add_reply_publication_side_effects
from company_api.comment_repository import CommentCursor
from company_api.models import (
    Comment,
    CommentReport,
    CommentStatus,
    Document,
    Notification,
    NotificationType,
    ReportStatus,
    User,
    UserSession,
    UserStatus,
)


@dataclass(frozen=True, slots=True)
class ModerationCommentRecord:
    id: UUID
    document_id: UUID
    document_title: str
    author_id: UUID | None
    author_username: str | None
    parent_id: UUID | None
    body: str | None
    status: CommentStatus
    created_at: datetime
    edited_at: datetime | None
    moderated_at: datetime | None
    deleted_at: datetime | None
    moderation_reason: str | None
    moderated_by: str | None


@dataclass(frozen=True, slots=True)
class ModerationReportRecord:
    id: UUID
    comment_id: UUID
    reporter_id: UUID
    reporter_username: str
    reason: str
    details: str | None
    status: ReportStatus
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None
    comment: ModerationCommentRecord


@dataclass(frozen=True, slots=True)
class ModerationUserRecord:
    id: UUID
    email: str
    username: str
    status: UserStatus
    email_verified_at: datetime | None
    first_comment_approved_at: datetime | None
    created_at: datetime
    comment_count: int


class ModerationTargetMissingError(Exception):
    """The requested moderation target does not exist."""


class ModerationStateConflictError(Exception):
    """The target changed to an incompatible state."""


class ModerationRepository(Protocol):
    async def list_comments(
        self,
        *,
        status: CommentStatus | None,
        cursor: CommentCursor | None,
        limit: int,
    ) -> list[ModerationCommentRecord]: ...

    async def approve(
        self, comment_id: UUID, administrator: str, *, now: datetime
    ) -> ModerationCommentRecord: ...

    async def reject(
        self, comment_id: UUID, administrator: str, reason: str, *, now: datetime
    ) -> ModerationCommentRecord: ...

    async def remove(
        self, comment_id: UUID, administrator: str, *, now: datetime
    ) -> ModerationCommentRecord: ...

    async def list_reports(
        self,
        *,
        status: ReportStatus | None,
        cursor: CommentCursor | None,
        limit: int,
    ) -> list[ModerationReportRecord]: ...

    async def resolve_report(
        self, report_id: UUID, administrator: str, resolution: ReportStatus, *, now: datetime
    ) -> ModerationReportRecord: ...

    async def list_users(
        self, normalized_query: str, *, cursor: CommentCursor | None, limit: int
    ) -> list[ModerationUserRecord]: ...

    async def suspend_user(self, user_id: UUID, *, now: datetime) -> ModerationUserRecord: ...

    async def restore_user(self, user_id: UUID, *, now: datetime) -> ModerationUserRecord: ...


class SqlAlchemyModerationRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        unsubscribe_token_factory: Callable[[], tuple[UUID, str]],
    ) -> None:
        self._session_factory = session_factory
        self._unsubscribe_token_factory = unsubscribe_token_factory

    async def list_comments(
        self,
        *,
        status: CommentStatus | None,
        cursor: CommentCursor | None,
        limit: int,
    ) -> list[ModerationCommentRecord]:
        async with self._session_factory() as session:
            statement = _comment_select()
            if status is not None:
                statement = statement.where(Comment.status == status)
            statement = _apply_cursor(statement, Comment.created_at, Comment.id, cursor)
            rows = (
                await session.execute(
                    statement.order_by(Comment.created_at.desc(), Comment.id.desc()).limit(limit)
                )
            ).all()
            return [_comment_record(comment, username, title) for comment, username, title in rows]

    async def approve(
        self, comment_id: UUID, administrator: str, *, now: datetime
    ) -> ModerationCommentRecord:
        async with self._session_factory() as session:
            comment, author = await _lock_comment_and_author(session, comment_id)
            if comment.status == CommentStatus.PUBLISHED:
                return await _comment_from_session(session, comment)
            if comment.status != CommentStatus.PENDING:
                raise ModerationStateConflictError

            comment.status = CommentStatus.PUBLISHED
            comment.moderated_at = now
            comment.moderated_by = administrator
            comment.moderation_reason = None
            if author is not None:
                if author.status == UserStatus.ACTIVE and author.first_comment_approved_at is None:
                    author.first_comment_approved_at = now
                session.add(
                    Notification(
                        recipient_id=author.id,
                        type=NotificationType.COMMENT_APPROVED,
                        actor_id=None,
                        comment_id=comment.id,
                        document_id=comment.document_id,
                        created_at=now,
                    )
                )
            reply_target = (
                await session.get(Comment, comment.reply_to_id)
                if comment.reply_to_id is not None
                else None
            )
            if author is not None:
                await add_reply_publication_side_effects(
                    session,
                    comment_id=comment.id,
                    document_id=comment.document_id,
                    actor_id=author.id,
                    actor_username=author.username,
                    reply_target=reply_target,
                    created_at=now,
                    unsubscribe_token_factory=self._unsubscribe_token_factory,
                )
            await session.flush()
            saved = await _comment_from_session(session, comment)
            await session.commit()
            return saved

    async def reject(
        self, comment_id: UUID, administrator: str, reason: str, *, now: datetime
    ) -> ModerationCommentRecord:
        async with self._session_factory() as session:
            comment, author = await _lock_comment_and_author(session, comment_id)
            if comment.status == CommentStatus.REJECTED:
                return await _comment_from_session(session, comment)
            if comment.status != CommentStatus.PENDING:
                raise ModerationStateConflictError

            comment.status = CommentStatus.REJECTED
            comment.moderated_at = now
            comment.moderated_by = administrator
            comment.moderation_reason = reason
            if author is not None:
                session.add(
                    Notification(
                        recipient_id=author.id,
                        type=NotificationType.COMMENT_REJECTED,
                        actor_id=None,
                        comment_id=comment.id,
                        document_id=comment.document_id,
                        created_at=now,
                    )
                )
            await session.flush()
            saved = await _comment_from_session(session, comment)
            await session.commit()
            return saved

    async def remove(
        self, comment_id: UUID, administrator: str, *, now: datetime
    ) -> ModerationCommentRecord:
        async with self._session_factory() as session:
            comment, _ = await _lock_comment_and_author(session, comment_id)
            await _remove_locked_comment(session, comment, administrator, now=now)
            await session.flush()
            saved = await _comment_from_session(session, comment)
            await session.commit()
            return saved

    async def list_reports(
        self,
        *,
        status: ReportStatus | None,
        cursor: CommentCursor | None,
        limit: int,
    ) -> list[ModerationReportRecord]:
        async with self._session_factory() as session:
            statement = _report_select()
            if status is not None:
                statement = statement.where(CommentReport.status == status)
            statement = _apply_cursor(statement, CommentReport.created_at, CommentReport.id, cursor)
            rows = (
                await session.execute(
                    statement.order_by(
                        CommentReport.created_at.desc(), CommentReport.id.desc()
                    ).limit(limit)
                )
            ).all()
            return [_report_record(*row) for row in rows]

    async def resolve_report(
        self,
        report_id: UUID,
        administrator: str,
        resolution: ReportStatus,
        *,
        now: datetime,
    ) -> ModerationReportRecord:
        async with self._session_factory() as session:
            initial = await session.get(CommentReport, report_id)
            if initial is None:
                raise ModerationTargetMissingError

            comment: Comment | None = None
            if resolution == ReportStatus.REMOVED:
                comment, _ = await _lock_comment_and_author(session, initial.comment_id)
            report = await session.scalar(
                select(CommentReport).where(CommentReport.id == report_id).with_for_update()
            )
            if report is None:
                raise ModerationTargetMissingError
            if report.status != ReportStatus.OPEN:
                if report.status != resolution:
                    raise ModerationStateConflictError
                return await _report_from_session(session, report)

            if resolution == ReportStatus.KEPT:
                report.status = ReportStatus.KEPT
                report.resolved_at = now
                report.resolved_by = administrator
            elif resolution == ReportStatus.REMOVED and comment is not None:
                await _remove_locked_comment(session, comment, administrator, now=now)
            else:
                raise ValueError("举报处理结果无效")
            await session.flush()
            saved = await _report_from_session(session, report)
            await session.commit()
            return saved

    async def list_users(
        self, normalized_query: str, *, cursor: CommentCursor | None, limit: int
    ) -> list[ModerationUserRecord]:
        async with self._session_factory() as session:
            statement = (
                select(User, func.count(Comment.id))
                .outerjoin(Comment, Comment.author_id == User.id)
                .where(
                    or_(
                        User.normalized_username.contains(normalized_query, autoescape=True),
                        User.normalized_email.contains(normalized_query, autoescape=True),
                    )
                )
                .group_by(User.id)
            )
            statement = _apply_cursor(statement, User.created_at, User.id, cursor)
            rows = (
                await session.execute(
                    statement.order_by(User.created_at.desc(), User.id.desc()).limit(limit)
                )
            ).all()
            return [_user_record(user, int(count)) for user, count in rows]

    async def suspend_user(self, user_id: UUID, *, now: datetime) -> ModerationUserRecord:
        async with self._session_factory() as session:
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise ModerationTargetMissingError
            user.status = UserStatus.SUSPENDED
            user.updated_at = now
            await session.execute(delete(UserSession).where(UserSession.user_id == user_id))
            count = await _comment_count(session, user_id)
            await session.flush()
            saved = _user_record(user, count)
            await session.commit()
            return saved

    async def restore_user(self, user_id: UUID, *, now: datetime) -> ModerationUserRecord:
        async with self._session_factory() as session:
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise ModerationTargetMissingError
            if user.status == UserStatus.SUSPENDED:
                user.status = (
                    UserStatus.ACTIVE
                    if user.email_verified_at is not None
                    else UserStatus.PENDING_VERIFICATION
                )
                user.updated_at = now
            elif user.status != UserStatus.ACTIVE:
                raise ModerationStateConflictError
            count = await _comment_count(session, user_id)
            await session.flush()
            saved = _user_record(user, count)
            await session.commit()
            return saved


def _comment_select() -> Select[Any]:
    return (
        select(Comment, User.username, Document.title)
        .outerjoin(User, User.id == Comment.author_id)
        .join(Document, Document.id == Comment.document_id)
    )


def _report_select() -> Select[Any]:
    reporter = aliased(User)
    author = aliased(User)
    return (
        select(CommentReport, reporter.username, Comment, author.username, Document.title)
        .join(reporter, reporter.id == CommentReport.reporter_id)
        .join(Comment, Comment.id == CommentReport.comment_id)
        .outerjoin(author, author.id == Comment.author_id)
        .join(Document, Document.id == Comment.document_id)
    )


def _apply_cursor(
    statement: Select[Any],
    created_at_column: Any,
    id_column: Any,
    cursor: CommentCursor | None,
) -> Select[Any]:
    if cursor is None:
        return statement
    return statement.where(
        or_(
            created_at_column < cursor.created_at,
            and_(created_at_column == cursor.created_at, id_column < cursor.id),
        )
    )


async def _lock_comment_and_author(
    session: AsyncSession, comment_id: UUID
) -> tuple[Comment, User | None]:
    comment = await session.scalar(
        select(Comment).where(Comment.id == comment_id).with_for_update()
    )
    if comment is None:
        raise ModerationTargetMissingError
    author = None
    if comment.author_id is not None:
        author = await session.scalar(
            select(User).where(User.id == comment.author_id).with_for_update()
        )
    return comment, author


async def _remove_locked_comment(
    session: AsyncSession,
    comment: Comment,
    administrator: str,
    *,
    now: datetime,
) -> None:
    if comment.status != CommentStatus.DELETED:
        if comment.status != CommentStatus.PUBLISHED:
            raise ModerationStateConflictError
        comment.status = CommentStatus.DELETED
        comment.body = None
        comment.deleted_at = now
        comment.moderated_at = now
        comment.moderated_by = administrator
    reports = (
        await session.scalars(
            select(CommentReport)
            .where(
                CommentReport.comment_id == comment.id,
                CommentReport.status == ReportStatus.OPEN,
            )
            .with_for_update()
        )
    ).all()
    for report in reports:
        report.status = ReportStatus.REMOVED
        report.resolved_at = now
        report.resolved_by = administrator


async def _comment_from_session(session: AsyncSession, comment: Comment) -> ModerationCommentRecord:
    row = (await session.execute(_comment_select().where(Comment.id == comment.id))).one()
    return _comment_record(*row)


async def _report_from_session(
    session: AsyncSession, report: CommentReport
) -> ModerationReportRecord:
    row = (await session.execute(_report_select().where(CommentReport.id == report.id))).one()
    return _report_record(*row)


async def _comment_count(session: AsyncSession, user_id: UUID) -> int:
    count = await session.scalar(
        select(func.count()).select_from(Comment).where(Comment.author_id == user_id)
    )
    return int(count or 0)


def _comment_record(
    comment: Comment, username: str | None, document_title: str
) -> ModerationCommentRecord:
    return ModerationCommentRecord(
        id=comment.id,
        document_id=comment.document_id,
        document_title=document_title,
        author_id=comment.author_id,
        author_username=username,
        parent_id=comment.parent_id,
        body=comment.body,
        status=comment.status,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
        moderated_at=comment.moderated_at,
        deleted_at=comment.deleted_at,
        moderation_reason=comment.moderation_reason,
        moderated_by=comment.moderated_by,
    )


def _report_record(
    report: CommentReport,
    reporter_username: str,
    comment: Comment,
    author_username: str | None,
    document_title: str,
) -> ModerationReportRecord:
    return ModerationReportRecord(
        id=report.id,
        comment_id=report.comment_id,
        reporter_id=report.reporter_id,
        reporter_username=reporter_username,
        reason=report.reason,
        details=report.details,
        status=report.status,
        created_at=report.created_at,
        resolved_at=report.resolved_at,
        resolved_by=report.resolved_by,
        comment=_comment_record(comment, author_username, document_title),
    )


def _user_record(user: User, comment_count: int) -> ModerationUserRecord:
    return ModerationUserRecord(
        id=user.id,
        email=user.email,
        username=user.username,
        status=user.status,
        email_verified_at=user.email_verified_at,
        first_comment_approved_at=user.first_comment_approved_at,
        created_at=user.created_at,
        comment_count=comment_count,
    )
