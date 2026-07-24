"""Domain rules and viewer-specific shaping for article comments."""

import base64
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from company_api.comment_repository import (
    CommentCursor,
    CommentRecord,
    CommentRepository,
    DuplicateCommentReportError,
    InvalidCommentReportError,
    NewCommentRecord,
    NewCommentReportRecord,
)
from company_api.comment_repository import (
    ParentCommentInvalid as ParentCommentInvalid,
)
from company_api.comment_schemas import (
    CommentAuthorRead,
    CommentPage,
    CommentRead,
    CommentThreadRead,
)
from company_api.models import CommentStatus
from company_api.user_auth import CurrentUser

PAGE_SIZE = 20


class CursorRecord(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def created_at(self) -> datetime: ...


class DocumentNotFound(Exception):
    """The requested document does not exist."""


class CommentNotFound(Exception):
    """The requested comment is not visible to the viewer."""


class DuplicateCommentReport(Exception):
    """The viewer already reported this comment."""


class CommentReportNotAllowed(Exception):
    """The viewer cannot report this comment."""


class CommentOperations(Protocol):
    async def list_comments(
        self, document_id: UUID, viewer_id: UUID | None, cursor: str | None
    ) -> CommentPage: ...

    async def create_comment(
        self,
        document_id: UUID,
        actor: CurrentUser,
        body: str,
        parent_id: UUID | None,
    ) -> CommentRead: ...

    async def get_thread(self, comment_id: UUID, viewer_id: UUID | None) -> CommentThreadRead: ...

    async def update_comment(
        self, comment_id: UUID, actor: CurrentUser, body: str
    ) -> CommentRead: ...

    async def delete_comment(self, comment_id: UUID, actor: CurrentUser) -> CommentRead: ...

    async def report_comment(
        self,
        comment_id: UUID,
        actor: CurrentUser,
        reason: str,
        details: str | None,
    ) -> None: ...


class CommentService:
    def __init__(
        self,
        repository: CommentRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        uuid_factory: Callable[[], UUID] = uuid.uuid4,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._uuid_factory = uuid_factory

    async def list_comments(
        self, document_id: UUID, viewer_id: UUID | None, cursor: str | None
    ) -> CommentPage:
        if not await self._repository.document_exists(document_id):
            raise DocumentNotFound
        decoded_cursor = _decode_cursor(cursor) if cursor is not None else None
        roots = await self._repository.list_top_level(
            document_id,
            cursor=decoded_cursor,
            limit=PAGE_SIZE + 1,
        )
        has_more = len(roots) > PAGE_SIZE
        roots = roots[:PAGE_SIZE]
        replies = await self._repository.list_replies([item.id for item in roots])
        replies_by_root: dict[UUID, list[CommentRecord]] = {}
        for reply in replies:
            if reply.parent_id is not None:
                replies_by_root.setdefault(reply.parent_id, []).append(reply)
        pending = (
            await self._repository.list_pending(document_id, viewer_id)
            if viewer_id is not None
            else []
        )
        next_cursor = _encode_cursor(roots[-1]) if has_more and roots else None
        return CommentPage(
            items=[self._read(root, viewer_id, replies_by_root.get(root.id, [])) for root in roots],
            viewer_pending=[self._read(item, viewer_id) for item in pending],
            next_cursor=next_cursor,
            total_count=await self._repository.count_published(document_id),
        )

    async def create_comment(
        self,
        document_id: UUID,
        actor: CurrentUser,
        body: str,
        parent_id: UUID | None,
    ) -> CommentRead:
        _validate_comment_body(body)
        if not await self._repository.document_exists(document_id):
            raise DocumentNotFound

        reply_target = None
        stored_parent_id = None
        if parent_id is not None:
            reply_target = await self._repository.get_parent(parent_id)
            if (
                reply_target is None
                or reply_target.document_id != document_id
                or reply_target.status != CommentStatus.PUBLISHED
            ):
                raise ParentCommentInvalid
            stored_parent_id = reply_target.parent_id or reply_target.id

        status = (
            CommentStatus.PUBLISHED
            if actor.first_comment_approved_at is not None
            else CommentStatus.PENDING
        )
        saved = await self._repository.create_comment(
            NewCommentRecord(
                id=self._uuid_factory(),
                document_id=document_id,
                author_id=actor.id,
                author_username=actor.username,
                parent_id=stored_parent_id,
                body=body,
                status=status,
                created_at=self._clock(),
            ),
            reply_target=reply_target,
        )
        return self._read(saved, actor.id)

    async def get_thread(self, comment_id: UUID, viewer_id: UUID | None) -> CommentThreadRead:
        target = await self._repository.get_comment(comment_id)
        if (
            target is None
            or not _is_visible(target, viewer_id)
            or (target.parent_id is not None and target.status == CommentStatus.DELETED)
        ):
            raise CommentNotFound
        root = target
        if target.parent_id is not None:
            possible_root = await self._repository.get_comment(target.parent_id)
            if possible_root is None or not _is_visible(possible_root, viewer_id):
                raise CommentNotFound
            root = possible_root
        replies = await self._repository.list_replies([root.id])
        if root.status == CommentStatus.DELETED and not replies:
            raise CommentNotFound
        pending = (
            await self._repository.list_pending(root.document_id, viewer_id)
            if viewer_id is not None
            else []
        )
        thread_pending = [
            item for item in pending if item.id == root.id or item.parent_id == root.id
        ]
        return CommentThreadRead(
            root=self._read(root, viewer_id, replies),
            target_comment_id=comment_id,
            viewer_pending=[self._read(item, viewer_id) for item in thread_pending],
        )

    async def update_comment(self, comment_id: UUID, actor: CurrentUser, body: str) -> CommentRead:
        _validate_comment_body(body)
        saved = await self._repository.update_owned_comment(
            comment_id, actor.id, body, now=self._clock()
        )
        if saved is None:
            raise CommentNotFound
        return self._read(saved, actor.id)

    async def delete_comment(self, comment_id: UUID, actor: CurrentUser) -> CommentRead:
        saved = await self._repository.delete_owned_comment(comment_id, actor.id, now=self._clock())
        if saved is None:
            raise CommentNotFound
        return self._read(saved, actor.id)

    async def report_comment(
        self,
        comment_id: UUID,
        actor: CurrentUser,
        reason: str,
        details: str | None,
    ) -> None:
        clean_reason = reason.strip()
        clean_details = details.strip() if details is not None else None
        if not clean_reason or len(clean_reason) > 100:
            raise ValueError("举报原因必须包含 1 到 100 个字符")
        if clean_details == "":
            clean_details = None
        if clean_details is not None and len(clean_details) > 2_000:
            raise ValueError("举报说明不能超过 2000 个字符")
        try:
            await self._repository.create_report(
                NewCommentReportRecord(
                    id=self._uuid_factory(),
                    comment_id=comment_id,
                    reporter_id=actor.id,
                    reason=clean_reason,
                    details=clean_details,
                    created_at=self._clock(),
                )
            )
        except DuplicateCommentReportError as error:
            raise DuplicateCommentReport from error
        except InvalidCommentReportError as error:
            raise CommentReportNotAllowed from error

    def _read(
        self,
        item: CommentRecord,
        viewer_id: UUID | None,
        replies: list[CommentRecord] | None = None,
    ) -> CommentRead:
        is_author = viewer_id is not None and item.author_id == viewer_id
        editable = is_author and item.status in {
            CommentStatus.PENDING,
            CommentStatus.PUBLISHED,
        }
        return CommentRead(
            id=item.id,
            document_id=item.document_id,
            parent_id=item.parent_id,
            body=None if item.status == CommentStatus.DELETED else item.body,
            status=item.status,
            author=CommentAuthorRead(
                id=item.author_id,
                username=item.author_username or "已注销用户",
            ),
            created_at=item.created_at,
            edited_at=item.edited_at,
            replies=[self._read(reply, viewer_id) for reply in replies or []],
            can_edit=editable,
            can_delete=editable,
            can_report=(
                viewer_id is not None
                and item.status == CommentStatus.PUBLISHED
                and item.author_id != viewer_id
            ),
        )


def _is_visible(item: CommentRecord, viewer_id: UUID | None) -> bool:
    return item.status in {CommentStatus.PUBLISHED, CommentStatus.DELETED} or (
        item.status == CommentStatus.PENDING
        and viewer_id is not None
        and item.author_id == viewer_id
    )


def _encode_cursor(item: CursorRecord) -> str:
    payload = json.dumps([item.created_at.isoformat(), str(item.id)], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor(value: str) -> CommentCursor:
    try:
        padding = "=" * (-len(value) % 4)
        created_at_value, id_value = json.loads(base64.urlsafe_b64decode(value + padding).decode())
        created_at = datetime.fromisoformat(created_at_value)
        if created_at.tzinfo is None:
            raise ValueError
        return CommentCursor(created_at=created_at, id=UUID(id_value))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("评论分页游标无效") from error


def _validate_comment_body(body: str) -> None:
    if len(body) > 2_000 or not body.strip():
        raise ValueError("评论正文必须包含 1 到 2000 个字符")
