import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from company_api.comment_repository import (
    CommentCursor,
    NewCommentRecord,
    ParentCommentInvalid,
    ParentCommentRecord,
    SqlAlchemyCommentRepository,
)
from company_api.models import (
    Comment,
    CommentStatus,
    Document,
    EmailOutbox,
    Notification,
    User,
    UserStatus,
)

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000601")
COMPANY_ID = UUID("00000000-0000-0000-0000-000000000602")
ACTOR_ID = UUID("00000000-0000-0000-0000-000000000603")
RECIPIENT_ID = UUID("00000000-0000-0000-0000-000000000604")
COMMENT_ID = UUID("00000000-0000-0000-0000-000000000605")
PARENT_ID = UUID("00000000-0000-0000-0000-000000000606")
ROOT_ID = UUID("00000000-0000-0000-0000-000000000607")


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


class Rows:
    def all(self) -> list[object]:
        return []


class FakeSession:
    def __init__(self) -> None:
        self.statements: list[object] = []
        self.added: list[object] = []
        self.events: list[str] = []
        self.recipient = User(
            id=RECIPIENT_ID,
            email="recipient@example.com",
            normalized_email="recipient@example.com",
            username="recipient",
            normalized_username="recipient",
            password_hash="hash",
            status=UserStatus.ACTIVE,
            email_verified_at=NOW,
            first_comment_approved_at=NOW,
            reply_email_enabled=True,
            created_at=NOW,
            updated_at=NOW,
        )
        self.document = Document(
            id=DOCUMENT_ID,
            company_id=COMPANY_ID,
            title="Research",
            format="html",  # type: ignore[arg-type]
            source_path="source",
            rendered_path=None,
            original_filename="research.html",
            uploaded_at=NOW,
        )
        self.locked_comments = {PARENT_ID: stored_comment(PARENT_ID)}

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def execute(self, statement: object) -> Rows:
        self.statements.append(statement)
        return Rows()

    async def scalar(self, statement: object) -> object | None:
        self.statements.append(statement)
        parameters = statement.compile(dialect=postgresql.dialect()).params  # type: ignore[attr-defined]
        comment_id = next(value for value in parameters.values() if isinstance(value, UUID))
        return self.locked_comments.get(comment_id)

    async def get(self, model: type[object], key: UUID) -> object | None:
        if model is User and key == RECIPIENT_ID:
            return self.recipient
        if model is Document and key == DOCUMENT_ID:
            return self.document
        return None

    def add(self, item: object) -> None:
        self.added.append(item)
        self.events.append(type(item).__name__)

    async def flush(self) -> None:
        self.events.append("flush")

    async def commit(self) -> None:
        self.events.append("commit")


class FakeFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSession:
        return self.session


def record(*, status: CommentStatus = CommentStatus.PUBLISHED) -> NewCommentRecord:
    return NewCommentRecord(
        id=COMMENT_ID,
        document_id=DOCUMENT_ID,
        author_id=ACTOR_ID,
        author_username="actor",
        parent_id=PARENT_ID,
        body="reply",
        status=status,
        created_at=NOW,
    )


def stored_comment(
    comment_id: UUID,
    *,
    document_id: UUID = DOCUMENT_ID,
    author_id: UUID = RECIPIENT_ID,
    parent_id: UUID | None = None,
    status: CommentStatus = CommentStatus.PUBLISHED,
) -> Comment:
    return Comment(
        id=comment_id,
        document_id=document_id,
        author_id=author_id,
        parent_id=parent_id,
        body="existing",
        status=status,
        created_at=NOW,
    )


def parent(*, author_id: UUID = RECIPIENT_ID) -> ParentCommentRecord:
    return ParentCommentRecord(
        id=PARENT_ID,
        document_id=DOCUMENT_ID,
        author_id=author_id,
        parent_id=None,
        status=CommentStatus.PUBLISHED,
    )


def test_top_level_cursor_uses_stable_created_at_and_id_predicate() -> None:
    session = FakeSession()
    repository = SqlAlchemyCommentRepository(FakeFactory(session))  # type: ignore[arg-type]

    run(
        repository.list_top_level(
            DOCUMENT_ID,
            cursor=CommentCursor(created_at=NOW, id=COMMENT_ID),
            limit=21,
        )
    )

    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "comments.created_at <" in sql
    assert "comments.created_at =" in sql
    assert "comments.id <" in sql
    assert "ORDER BY comments.created_at DESC, comments.id DESC" in sql
    assert compiled.params["param_1"] == 21


def test_published_reply_notification_and_email_share_comment_commit() -> None:
    session = FakeSession()
    repository = SqlAlchemyCommentRepository(FakeFactory(session))  # type: ignore[arg-type]

    saved = run(repository.create_comment(record(), reply_target=parent()))

    assert saved.id == COMMENT_ID
    created = session.added[0]
    assert isinstance(created, Comment)
    assert created.parent_id == PARENT_ID
    assert created.reply_to_id == PARENT_ID
    assert [type(item) for item in session.added] == [Comment, Notification, EmailOutbox]
    outbox = session.added[-1]
    assert isinstance(outbox, EmailOutbox)
    assert outbox.recipient == "recipient@example.com"
    assert outbox.payload is not None
    assert outbox.payload["company_id"] == str(COMPANY_ID)
    assert session.events == ["Comment", "Notification", "EmailOutbox", "flush", "commit"]


def test_pending_or_self_reply_does_not_notify() -> None:
    pending_session = FakeSession()
    pending_repository = SqlAlchemyCommentRepository(FakeFactory(pending_session))  # type: ignore[arg-type]
    run(
        pending_repository.create_comment(
            record(status=CommentStatus.PENDING), reply_target=parent()
        )
    )

    self_session = FakeSession()
    self_session.locked_comments[PARENT_ID].author_id = ACTOR_ID
    self_repository = SqlAlchemyCommentRepository(FakeFactory(self_session))  # type: ignore[arg-type]
    run(self_repository.create_comment(record(), reply_target=parent(author_id=ACTOR_ID)))

    assert [type(item) for item in pending_session.added] == [Comment]
    assert [type(item) for item in self_session.added] == [Comment]


@pytest.mark.parametrize(
    "changed_status",
    [None, CommentStatus.PENDING, CommentStatus.REJECTED, CommentStatus.DELETED],
)
def test_create_relocks_direct_parent_and_rejects_change_after_precheck(
    changed_status: CommentStatus | None,
) -> None:
    session = FakeSession()
    if changed_status is None:
        session.locked_comments.pop(PARENT_ID)
    else:
        session.locked_comments[PARENT_ID].status = changed_status
    repository = SqlAlchemyCommentRepository(FakeFactory(session))  # type: ignore[arg-type]

    with pytest.raises(ParentCommentInvalid):
        run(repository.create_comment(record(), reply_target=parent()))

    lock = session.statements[0].compile(dialect=postgresql.dialect())  # type: ignore[attr-defined]
    assert "FOR UPDATE" in str(lock)
    assert session.added == []
    assert "commit" not in session.events


def test_reply_to_reply_locks_and_validates_direct_target_then_root() -> None:
    root_author_id = UUID(int=888)
    session = FakeSession()
    session.locked_comments = {
        PARENT_ID: stored_comment(PARENT_ID, parent_id=ROOT_ID),
        ROOT_ID: stored_comment(ROOT_ID, author_id=root_author_id),
    }
    repository = SqlAlchemyCommentRepository(FakeFactory(session))  # type: ignore[arg-type]
    nested_record = record()
    nested_record = NewCommentRecord(
        id=nested_record.id,
        document_id=nested_record.document_id,
        author_id=nested_record.author_id,
        author_username=nested_record.author_username,
        parent_id=ROOT_ID,
        body=nested_record.body,
        status=nested_record.status,
        created_at=nested_record.created_at,
    )

    saved = run(
        repository.create_comment(
            nested_record,
            reply_target=parent_record(PARENT_ID, parent_id=ROOT_ID),
        )
    )

    locks = [
        statement.compile(dialect=postgresql.dialect())  # type: ignore[attr-defined]
        for statement in session.statements[:2]
    ]
    assert all("FOR UPDATE" in str(lock) for lock in locks)
    locked_ids = [
        next(value for value in lock.params.values() if isinstance(value, UUID)) for lock in locks
    ]
    assert locked_ids == [
        PARENT_ID,
        ROOT_ID,
    ]
    assert saved.parent_id == ROOT_ID
    created = session.added[0]
    assert isinstance(created, Comment)
    assert created.reply_to_id == PARENT_ID
    notification = next(item for item in session.added if isinstance(item, Notification))
    assert notification.recipient_id == RECIPIENT_ID
    assert notification.recipient_id != root_author_id


def test_pending_nested_reply_persists_direct_target_without_publication_side_effects() -> None:
    session = FakeSession()
    session.locked_comments = {
        PARENT_ID: stored_comment(PARENT_ID, parent_id=ROOT_ID),
        ROOT_ID: stored_comment(ROOT_ID, author_id=UUID(int=888)),
    }
    repository = SqlAlchemyCommentRepository(FakeFactory(session))  # type: ignore[arg-type]
    nested = record(status=CommentStatus.PENDING)
    nested = NewCommentRecord(
        id=nested.id,
        document_id=nested.document_id,
        author_id=nested.author_id,
        author_username=nested.author_username,
        parent_id=ROOT_ID,
        body=nested.body,
        status=nested.status,
        created_at=nested.created_at,
    )

    run(
        repository.create_comment(
            nested,
            reply_target=parent_record(PARENT_ID, parent_id=ROOT_ID),
        )
    )

    assert [type(item) for item in session.added] == [Comment]
    created = session.added[0]
    assert isinstance(created, Comment)
    assert created.parent_id == ROOT_ID
    assert created.reply_to_id == PARENT_ID


@pytest.mark.parametrize("changed_id", [PARENT_ID, ROOT_ID])
def test_locked_direct_target_and_root_must_still_match_document(changed_id: UUID) -> None:
    session = FakeSession()
    session.locked_comments = {
        PARENT_ID: stored_comment(PARENT_ID, parent_id=ROOT_ID),
        ROOT_ID: stored_comment(ROOT_ID),
    }
    changed = session.locked_comments[changed_id]
    changed.document_id = UUID(int=999)
    repository = SqlAlchemyCommentRepository(FakeFactory(session))  # type: ignore[arg-type]

    with pytest.raises(ParentCommentInvalid):
        run(
            repository.create_comment(
                record(),
                reply_target=parent_record(PARENT_ID, parent_id=ROOT_ID),
            )
        )

    assert session.added == []
    assert "commit" not in session.events


def parent_record(comment_id: UUID, *, parent_id: UUID | None) -> ParentCommentRecord:
    return ParentCommentRecord(
        id=comment_id,
        document_id=DOCUMENT_ID,
        author_id=RECIPIENT_ID,
        parent_id=parent_id,
        status=CommentStatus.PUBLISHED,
    )


@pytest.mark.parametrize(
    "changed_status",
    [None, CommentStatus.PENDING, CommentStatus.REJECTED, CommentStatus.DELETED],
)
def test_reply_to_reply_rejects_nonpublished_locked_root(
    changed_status: CommentStatus | None,
) -> None:
    session = FakeSession()
    session.locked_comments = {
        PARENT_ID: stored_comment(PARENT_ID, parent_id=ROOT_ID),
    }
    if changed_status is not None:
        session.locked_comments[ROOT_ID] = stored_comment(ROOT_ID, status=changed_status)
    repository = SqlAlchemyCommentRepository(FakeFactory(session))  # type: ignore[arg-type]

    with pytest.raises(ParentCommentInvalid):
        run(
            repository.create_comment(
                record(),
                reply_target=parent_record(PARENT_ID, parent_id=ROOT_ID),
            )
        )

    assert session.added == []
    assert "commit" not in session.events
