import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.dialects import postgresql

from company_api.comment_repository import (
    CommentCursor,
    NewCommentRecord,
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

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def execute(self, statement: object) -> Rows:
        self.statements.append(statement)
        return Rows()

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
    self_repository = SqlAlchemyCommentRepository(FakeFactory(self_session))  # type: ignore[arg-type]
    run(self_repository.create_comment(record(), reply_target=parent(author_id=ACTOR_ID)))

    assert [type(item) for item in pending_session.added] == [Comment]
    assert [type(item) for item in self_session.added] == [Comment]
