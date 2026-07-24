import asyncio
from collections.abc import Coroutine
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from company_api.comment_repository import CommentRecord, NewCommentRecord, ParentCommentRecord
from company_api.comment_service import (
    CommentNotFound,
    CommentService,
    DocumentNotFound,
    ParentCommentInvalid,
    _decode_cursor,
)
from company_api.models import CommentStatus
from company_api.user_auth import CurrentUser

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000601")
OTHER_DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000602")
USER_ID = UUID("00000000-0000-0000-0000-000000000603")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000604")
ROOT_ID = UUID("00000000-0000-0000-0000-000000000605")
REPLY_ID = UUID("00000000-0000-0000-0000-000000000606")
NEW_ID = UUID("00000000-0000-0000-0000-000000000607")


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def actor(*, trusted: bool = False) -> CurrentUser:
    return CurrentUser(
        id=USER_ID,
        email="reader@example.com",
        username="reader",
        email_verified_at=NOW,
        first_comment_approved_at=NOW if trusted else None,
        reply_email_enabled=True,
    )


def comment(
    comment_id: UUID,
    *,
    document_id: UUID = DOCUMENT_ID,
    author_id: UUID | None = OTHER_USER_ID,
    parent_id: UUID | None = None,
    body: str | None = "comment",
    status: CommentStatus = CommentStatus.PUBLISHED,
    created_at: datetime = NOW,
) -> CommentRecord:
    return CommentRecord(
        id=comment_id,
        document_id=document_id,
        author_id=author_id,
        author_username="other" if author_id is not None else None,
        parent_id=parent_id,
        body=body,
        status=status,
        created_at=created_at,
        edited_at=None,
    )


class MemoryCommentRepository:
    def __init__(self) -> None:
        self.documents = {DOCUMENT_ID}
        self.comments: dict[UUID, CommentRecord] = {}
        self.created: list[tuple[NewCommentRecord, ParentCommentRecord | None]] = []

    async def document_exists(self, document_id: UUID) -> bool:
        return document_id in self.documents

    async def get_parent(self, comment_id: UUID) -> ParentCommentRecord | None:
        item = self.comments.get(comment_id)
        if item is None:
            return None
        return ParentCommentRecord(
            id=item.id,
            document_id=item.document_id,
            author_id=item.author_id,
            parent_id=item.parent_id,
            status=item.status,
        )

    async def create_comment(
        self,
        record: NewCommentRecord,
        *,
        reply_target: ParentCommentRecord | None,
    ) -> CommentRecord:
        self.created.append((record, reply_target))
        saved = comment(
            record.id,
            author_id=record.author_id,
            parent_id=record.parent_id,
            body=record.body,
            status=record.status,
            created_at=record.created_at,
        )
        saved = replace(saved, author_username=record.author_username)
        self.comments[saved.id] = saved
        return saved

    async def list_top_level(
        self, document_id: UUID, *, cursor: object | None, limit: int
    ) -> list[CommentRecord]:
        del cursor
        roots = [
            item
            for item in self.comments.values()
            if item.document_id == document_id
            and item.parent_id is None
            and item.status in {CommentStatus.PUBLISHED, CommentStatus.DELETED}
        ]
        return sorted(roots, key=lambda item: (item.created_at, item.id), reverse=True)[:limit]

    async def list_replies(self, root_ids: list[UUID]) -> list[CommentRecord]:
        replies = [
            item
            for item in self.comments.values()
            if item.parent_id in root_ids and item.status == CommentStatus.PUBLISHED
        ]
        return sorted(replies, key=lambda item: (item.created_at, item.id))

    async def list_pending(self, document_id: UUID, viewer_id: UUID) -> list[CommentRecord]:
        return [
            item
            for item in self.comments.values()
            if item.document_id == document_id
            and item.author_id == viewer_id
            and item.status == CommentStatus.PENDING
        ]

    async def count_published(self, document_id: UUID) -> int:
        return sum(
            item.document_id == document_id and item.status == CommentStatus.PUBLISHED
            for item in self.comments.values()
        )

    async def get_comment(self, comment_id: UUID) -> CommentRecord | None:
        return self.comments.get(comment_id)


@pytest.fixture
def repository() -> MemoryCommentRepository:
    return MemoryCommentRepository()


@pytest.fixture
def service(repository: MemoryCommentRepository) -> CommentService:
    return CommentService(repository, clock=lambda: NOW, uuid_factory=lambda: NEW_ID)


def test_create_rejects_missing_documents(service: CommentService) -> None:
    with pytest.raises(DocumentNotFound):
        run(service.create_comment(OTHER_DOCUMENT_ID, actor(), "hello", None))


def test_comment_body_accepts_2000_characters_and_rejects_invalid_text(
    service: CommentService,
) -> None:
    created = run(service.create_comment(DOCUMENT_ID, actor(), "x" * 2_000, None))
    assert created.body == "x" * 2_000

    for invalid in ("", " \n\t ", "x" * 2_001):
        with pytest.raises(ValueError, match="1 到 2000"):
            run(service.create_comment(DOCUMENT_ID, actor(), invalid, None))


def test_untrusted_comment_is_pending_but_trusted_comment_publishes(
    service: CommentService,
) -> None:
    pending = run(service.create_comment(DOCUMENT_ID, actor(), "pending", None))
    published = run(service.create_comment(DOCUMENT_ID, actor(trusted=True), "published", None))

    assert pending.status == CommentStatus.PENDING
    assert published.status == CommentStatus.PUBLISHED


def test_parent_must_be_replyable_and_belong_to_same_document(
    service: CommentService, repository: MemoryCommentRepository
) -> None:
    repository.comments[ROOT_ID] = comment(ROOT_ID, document_id=OTHER_DOCUMENT_ID)
    with pytest.raises(ParentCommentInvalid):
        run(service.create_comment(DOCUMENT_ID, actor(trusted=True), "reply", ROOT_ID))

    repository.comments[ROOT_ID] = comment(ROOT_ID, status=CommentStatus.DELETED, body=None)
    with pytest.raises(ParentCommentInvalid):
        run(service.create_comment(DOCUMENT_ID, actor(trusted=True), "reply", ROOT_ID))


def test_reply_to_reply_flattens_to_root_but_retains_direct_notification_target(
    service: CommentService, repository: MemoryCommentRepository
) -> None:
    repository.comments[ROOT_ID] = comment(ROOT_ID)
    repository.comments[REPLY_ID] = comment(REPLY_ID, parent_id=ROOT_ID)

    run(service.create_comment(DOCUMENT_ID, actor(trusted=True), "nested", REPLY_ID))

    saved, target = repository.created[-1]
    assert saved.parent_id == ROOT_ID
    assert target is not None and target.id == REPLY_ID


def test_listing_keeps_public_order_counts_and_only_viewers_own_pending(
    service: CommentService, repository: MemoryCommentRepository
) -> None:
    repository.comments = {
        ROOT_ID: comment(ROOT_ID, created_at=NOW),
        NEW_ID: comment(NEW_ID, created_at=NOW + timedelta(seconds=1)),
        REPLY_ID: comment(REPLY_ID, parent_id=ROOT_ID, created_at=NOW - timedelta(seconds=1)),
        UUID(int=700): comment(UUID(int=700), author_id=USER_ID, status=CommentStatus.PENDING),
        UUID(int=701): comment(
            UUID(int=701), author_id=OTHER_USER_ID, status=CommentStatus.PENDING
        ),
        UUID(int=702): comment(UUID(int=702), status=CommentStatus.REJECTED),
    }

    page = run(service.list_comments(DOCUMENT_ID, USER_ID, None))

    assert [item.id for item in page.items] == [NEW_ID, ROOT_ID]
    assert [item.id for item in page.items[1].replies] == [REPLY_ID]
    assert [item.id for item in page.viewer_pending] == [UUID(int=700)]
    assert page.total_count == 3


def test_next_cursor_identifies_the_last_visible_created_at_and_id(
    service: CommentService, repository: MemoryCommentRepository
) -> None:
    for number in range(1, 22):
        comment_id = UUID(int=number)
        repository.comments[comment_id] = comment(comment_id, created_at=NOW)

    page = run(service.list_comments(DOCUMENT_ID, None, None))

    assert len(page.items) == 20
    assert page.next_cursor is not None
    decoded = _decode_cursor(page.next_cursor)
    assert decoded.created_at == NOW
    assert decoded.id == UUID(int=2)


def test_thread_retrieves_visible_off_page_root_and_hides_private_rows(
    service: CommentService, repository: MemoryCommentRepository
) -> None:
    repository.comments[ROOT_ID] = comment(ROOT_ID)
    repository.comments[REPLY_ID] = comment(REPLY_ID, parent_id=ROOT_ID)

    thread = run(service.get_thread(REPLY_ID, None))
    assert thread.root.id == ROOT_ID
    assert thread.target_comment_id == REPLY_ID

    repository.comments[REPLY_ID] = comment(
        REPLY_ID,
        author_id=OTHER_USER_ID,
        parent_id=ROOT_ID,
        status=CommentStatus.PENDING,
    )
    with pytest.raises(CommentNotFound):
        run(service.get_thread(REPLY_ID, USER_ID))

    repository.comments[REPLY_ID] = comment(
        REPLY_ID,
        author_id=OTHER_USER_ID,
        parent_id=ROOT_ID,
        body=None,
        status=CommentStatus.DELETED,
    )
    with pytest.raises(CommentNotFound):
        run(service.get_thread(REPLY_ID, USER_ID))
