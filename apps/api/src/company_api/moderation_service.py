"""Administrator comment moderation and site-user administration rules."""

import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Never, Protocol
from uuid import UUID

from company_api.comment_repository import CommentCursor
from company_api.comment_service import _decode_cursor, _encode_cursor
from company_api.models import CommentStatus, ReportStatus
from company_api.moderation_repository import (
    ModerationCommentRecord,
    ModerationReportRecord,
    ModerationRepository,
    ModerationStateConflictError,
    ModerationTargetMissingError,
    ModerationUserRecord,
)
from company_api.moderation_schemas import (
    ModerationCommentPage,
    ModerationCommentRead,
    ModerationReportPage,
    ModerationReportRead,
    ModerationUserPage,
    ModerationUserRead,
)

ADMIN_PAGE_SIZE = 50


class ModerationNotFound(Exception):
    """The moderation target does not exist."""


class ModerationConflict(Exception):
    """The moderation target has already changed state."""


class CursorRecord(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def created_at(self) -> datetime: ...


class ModerationOperations(Protocol):
    async def list_comments(
        self, status: CommentStatus | None, cursor: str | None
    ) -> ModerationCommentPage: ...

    async def approve(self, comment_id: UUID, administrator: str) -> ModerationCommentRead: ...

    async def reject(
        self, comment_id: UUID, administrator: str, reason: str
    ) -> ModerationCommentRead: ...

    async def remove(self, comment_id: UUID, administrator: str) -> ModerationCommentRead: ...

    async def list_reports(
        self, status: ReportStatus | None, cursor: str | None
    ) -> ModerationReportPage: ...

    async def resolve_report(
        self, report_id: UUID, administrator: str, resolution: ReportStatus
    ) -> ModerationReportRead: ...

    async def list_users(self, query: str, cursor: str | None) -> ModerationUserPage: ...

    async def suspend_user(self, user_id: UUID) -> ModerationUserRead: ...

    async def restore_user(self, user_id: UUID) -> ModerationUserRead: ...


class ModerationService:
    def __init__(
        self,
        repository: ModerationRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    async def list_comments(
        self, status: CommentStatus | None, cursor: str | None
    ) -> ModerationCommentPage:
        rows = await self._repository.list_comments(
            status=status,
            cursor=_optional_cursor(cursor),
            limit=ADMIN_PAGE_SIZE + 1,
        )
        items, next_cursor = _page(rows)
        return ModerationCommentPage(
            items=[_comment_read(item) for item in items],
            next_cursor=next_cursor,
        )

    async def approve(self, comment_id: UUID, administrator: str) -> ModerationCommentRead:
        try:
            saved = await self._repository.approve(comment_id, administrator, now=self._clock())
        except (ModerationTargetMissingError, ModerationStateConflictError) as error:
            _raise_moderation_error(error)
        return _comment_read(saved)

    async def reject(
        self, comment_id: UUID, administrator: str, reason: str
    ) -> ModerationCommentRead:
        clean_reason = reason.strip()
        if not clean_reason or len(clean_reason) > 500:
            raise ValueError("拒绝原因必须包含 1 到 500 个字符")
        try:
            saved = await self._repository.reject(
                comment_id, administrator, clean_reason, now=self._clock()
            )
        except (ModerationTargetMissingError, ModerationStateConflictError) as error:
            _raise_moderation_error(error)
        return _comment_read(saved)

    async def remove(self, comment_id: UUID, administrator: str) -> ModerationCommentRead:
        try:
            saved = await self._repository.remove(comment_id, administrator, now=self._clock())
        except (ModerationTargetMissingError, ModerationStateConflictError) as error:
            _raise_moderation_error(error)
        return _comment_read(saved)

    async def list_reports(
        self, status: ReportStatus | None, cursor: str | None
    ) -> ModerationReportPage:
        rows = await self._repository.list_reports(
            status=status,
            cursor=_optional_cursor(cursor),
            limit=ADMIN_PAGE_SIZE + 1,
        )
        items, next_cursor = _page(rows)
        return ModerationReportPage(
            items=[_report_read(item) for item in items],
            next_cursor=next_cursor,
        )

    async def resolve_report(
        self, report_id: UUID, administrator: str, resolution: ReportStatus
    ) -> ModerationReportRead:
        if resolution not in {ReportStatus.KEPT, ReportStatus.REMOVED}:
            raise ValueError("举报处理结果无效")
        try:
            saved = await self._repository.resolve_report(
                report_id,
                administrator,
                resolution,
                now=self._clock(),
            )
        except (ModerationTargetMissingError, ModerationStateConflictError) as error:
            _raise_moderation_error(error)
        return _report_read(saved)

    async def list_users(self, query: str, cursor: str | None) -> ModerationUserPage:
        clean_query = unicodedata.normalize("NFKC", query.strip()).casefold()
        if not 1 <= len(clean_query) <= 100:
            raise ValueError("用户搜索必须包含 1 到 100 个字符")
        rows = await self._repository.list_users(
            clean_query,
            cursor=_optional_cursor(cursor),
            limit=ADMIN_PAGE_SIZE + 1,
        )
        items, next_cursor = _page(rows)
        return ModerationUserPage(
            items=[_user_read(item) for item in items],
            next_cursor=next_cursor,
        )

    async def suspend_user(self, user_id: UUID) -> ModerationUserRead:
        try:
            saved = await self._repository.suspend_user(user_id, now=self._clock())
        except ModerationTargetMissingError as error:
            raise ModerationNotFound from error
        return _user_read(saved)

    async def restore_user(self, user_id: UUID) -> ModerationUserRead:
        try:
            saved = await self._repository.restore_user(user_id, now=self._clock())
        except (ModerationTargetMissingError, ModerationStateConflictError) as error:
            _raise_moderation_error(error)
        return _user_read(saved)


def _optional_cursor(value: str | None) -> CommentCursor | None:
    return _decode_cursor(value) if value is not None else None


def _raise_moderation_error(error: Exception) -> Never:
    if isinstance(error, ModerationTargetMissingError):
        raise ModerationNotFound from error
    raise ModerationConflict from error


def _page[T: CursorRecord](rows: list[T]) -> tuple[list[T], str | None]:
    has_more = len(rows) > ADMIN_PAGE_SIZE
    items = rows[:ADMIN_PAGE_SIZE]
    next_cursor = _encode_cursor(items[-1]) if has_more and items else None
    return items, next_cursor


def _comment_read(item: ModerationCommentRecord) -> ModerationCommentRead:
    return ModerationCommentRead.model_validate(item, from_attributes=True)


def _report_read(item: ModerationReportRecord) -> ModerationReportRead:
    return ModerationReportRead.model_validate(item, from_attributes=True)


def _user_read(item: ModerationUserRecord) -> ModerationUserRead:
    return ModerationUserRead.model_validate(item, from_attributes=True)
