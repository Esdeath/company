import asyncio
from collections.abc import Coroutine
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from company_api.comment_repository import (
    CommentRecord,
    DuplicateCommentReportError,
    InvalidCommentReportError,
    NewCommentReportRecord,
)
from company_api.comment_schemas import CommentAuthorRead, CommentRead
from company_api.comment_service import (
    CommentNotFound,
    CommentReportNotAllowed,
    CommentService,
    DuplicateCommentReport,
)
from company_api.config import Settings
from company_api.main import create_app
from company_api.models import CommentStatus
from company_api.user_auth import CurrentUser, UserSessionRecord

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000701")
COMMENT_ID = UUID("00000000-0000-0000-0000-000000000702")
USER_ID = UUID("00000000-0000-0000-0000-000000000703")
ADMIN_HASH = PasswordHash.recommended().hash("correct horse battery staple")


def settings(*, writes_enabled: bool = True) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://company@postgres/company",
        admin_username="admin",
        admin_password_hash=ADMIN_HASH,
        session_cookie_secure=False,
        comment_writes_enabled=writes_enabled,
    )


CURRENT_USER = CurrentUser(
    id=USER_ID,
    email="reader@example.com",
    username="reader",
    email_verified_at=NOW,
    first_comment_approved_at=NOW,
    reply_email_enabled=True,
)
SESSION = UserSessionRecord(
    token_hash="user-hash",
    user_id=USER_ID,
    csrf_token="user-csrf",
    expires_at=NOW,
    current_user=CURRENT_USER,
)


def comment(
    *, body: str | None = "published", status: CommentStatus = CommentStatus.PUBLISHED
) -> CommentRead:
    return CommentRead(
        id=COMMENT_ID,
        document_id=DOCUMENT_ID,
        parent_id=None,
        body=body,
        status=status,
        author=CommentAuthorRead(id=USER_ID, username="reader"),
        created_at=NOW,
        edited_at=NOW if body == "edited" else None,
        can_edit=status in {CommentStatus.PENDING, CommentStatus.PUBLISHED},
        can_delete=status in {CommentStatus.PENDING, CommentStatus.PUBLISHED},
        can_report=False,
    )


class FakeComments:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.error: Exception | None = None

    async def update_comment(self, comment_id: UUID, actor: CurrentUser, body: str) -> CommentRead:
        self.calls.append(("update", comment_id, actor, body))
        if self.error is not None:
            raise self.error
        return comment(body="edited")

    async def delete_comment(self, comment_id: UUID, actor: CurrentUser) -> CommentRead:
        self.calls.append(("delete", comment_id, actor))
        if self.error is not None:
            raise self.error
        return comment(body=None, status=CommentStatus.DELETED)

    async def report_comment(
        self,
        comment_id: UUID,
        actor: CurrentUser,
        reason: str,
        details: str | None,
    ) -> None:
        self.calls.append(("report", comment_id, actor, reason, details))
        if self.error is not None:
            raise self.error


class FakeUserAuth:
    async def authenticate(self, token: str) -> UserSessionRecord | None:
        return SESSION if token == "user-session" else None

    def csrf_is_valid(self, session: UserSessionRecord, submitted: str) -> bool:
        return session is SESSION and submitted == "user-csrf"


class Probe:
    async def check(self) -> None:
        return None


class Dispatcher:
    async def run(self, stop: object) -> None:
        await stop.wait()  # type: ignore[attr-defined]


def make_client(comments: FakeComments, *, writes_enabled: bool = True) -> TestClient:
    app = create_app(
        settings(writes_enabled=writes_enabled),
        Probe(),
        library_service=object(),  # type: ignore[arg-type]
        auth_service=object(),  # type: ignore[arg-type]
        user_auth_service=FakeUserAuth(),  # type: ignore[arg-type]
        comment_service=comments,  # type: ignore[arg-type]
        email_dispatcher=Dispatcher(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def authenticated(client: TestClient) -> None:
    client.cookies.set("company-user-session", "user-session")


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


class MemoryActions:
    def __init__(self, stored: CommentRecord) -> None:
        self.stored = stored
        self.reports: set[tuple[UUID, UUID]] = set()

    async def update_owned_comment(
        self, comment_id: UUID, author_id: UUID, body: str, *, now: datetime
    ) -> CommentRecord | None:
        if (
            self.stored.id != comment_id
            or self.stored.author_id != author_id
            or self.stored.status not in {CommentStatus.PENDING, CommentStatus.PUBLISHED}
        ):
            return None
        self.stored = replace(self.stored, body=body, edited_at=now)
        return self.stored

    async def delete_owned_comment(
        self, comment_id: UUID, author_id: UUID, *, now: datetime
    ) -> CommentRecord | None:
        if (
            self.stored.id != comment_id
            or self.stored.author_id != author_id
            or self.stored.status not in {CommentStatus.PENDING, CommentStatus.PUBLISHED}
        ):
            return None
        self.stored = replace(self.stored, body=None, status=CommentStatus.DELETED)
        return self.stored

    async def create_report(self, record: NewCommentReportRecord) -> None:
        if (
            self.stored.status != CommentStatus.PUBLISHED
            or self.stored.author_id == record.reporter_id
        ):
            raise InvalidCommentReportError
        key = (record.comment_id, record.reporter_id)
        if key in self.reports:
            raise DuplicateCommentReportError
        self.reports.add(key)


def stored_comment(*, status: CommentStatus, author_id: UUID = USER_ID) -> CommentRecord:
    return CommentRecord(
        id=COMMENT_ID,
        document_id=DOCUMENT_ID,
        author_id=author_id,
        author_username="reader",
        parent_id=None,
        body="original",
        status=status,
        created_at=NOW,
        edited_at=None,
    )


def test_edit_delete_and_report_require_author_user_csrf() -> None:
    comments = FakeComments()
    with make_client(comments) as client:
        unauthenticated = client.patch(f"/api/v1/comments/{COMMENT_ID}", json={"body": "edited"})
        authenticated(client)
        missing_csrf = client.delete(f"/api/v1/comments/{COMMENT_ID}")
        edited = client.patch(
            f"/api/v1/comments/{COMMENT_ID}",
            headers={"X-CSRF-Token": "user-csrf"},
            json={"body": "edited"},
        )
        deleted = client.delete(
            f"/api/v1/comments/{COMMENT_ID}", headers={"X-CSRF-Token": "user-csrf"}
        )
        reported = client.post(
            f"/api/v1/comments/{COMMENT_ID}/reports",
            headers={"X-CSRF-Token": "user-csrf"},
            json={"reason": "spam", "details": "repeated links"},
        )

    assert unauthenticated.status_code == 401
    assert missing_csrf.status_code == 403
    assert edited.status_code == 200
    assert edited.json()["edited_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert deleted.status_code == 200
    assert deleted.json()["body"] is None
    assert deleted.json()["status"] == "deleted"
    assert reported.status_code == 201
    assert comments.calls == [
        ("update", COMMENT_ID, CURRENT_USER, "edited"),
        ("delete", COMMENT_ID, CURRENT_USER),
        ("report", COMMENT_ID, CURRENT_USER, "spam", "repeated links"),
    ]


def test_author_action_errors_hide_ownership_and_duplicate_reports_conflict() -> None:
    comments = FakeComments()
    with make_client(comments) as client:
        authenticated(client)
        comments.error = CommentNotFound()
        edit = client.patch(
            f"/api/v1/comments/{COMMENT_ID}",
            headers={"X-CSRF-Token": "user-csrf"},
            json={"body": "edited"},
        )
        comments.error = DuplicateCommentReport()
        report = client.post(
            f"/api/v1/comments/{COMMENT_ID}/reports",
            headers={"X-CSRF-Token": "user-csrf"},
            json={"reason": "spam"},
        )

    assert edit.status_code == 404
    assert report.status_code == 409


def test_write_switch_blocks_edit_delete_and_report() -> None:
    comments = FakeComments()
    with make_client(comments, writes_enabled=False) as client:
        authenticated(client)
        responses = [
            client.patch(
                f"/api/v1/comments/{COMMENT_ID}",
                headers={"X-CSRF-Token": "user-csrf"},
                json={"body": "edited"},
            ),
            client.delete(
                f"/api/v1/comments/{COMMENT_ID}",
                headers={"X-CSRF-Token": "user-csrf"},
            ),
            client.post(
                f"/api/v1/comments/{COMMENT_ID}/reports",
                headers={"X-CSRF-Token": "user-csrf"},
                json={"reason": "spam"},
            ),
        ]

    assert [response.status_code for response in responses] == [503, 503, 503]
    assert comments.calls == []


def test_author_edits_preserve_pending_or_published_state_and_set_edited_at() -> None:
    for status in (CommentStatus.PENDING, CommentStatus.PUBLISHED):
        repository = MemoryActions(stored_comment(status=status))
        service = CommentService(repository, clock=lambda: NOW)  # type: ignore[arg-type]

        edited = run(service.update_comment(COMMENT_ID, CURRENT_USER, "changed"))

        assert edited.status == status
        assert edited.body == "changed"
        assert edited.edited_at == NOW


def test_author_only_delete_soft_deletes_and_scrubs_body() -> None:
    repository = MemoryActions(stored_comment(status=CommentStatus.PUBLISHED))
    service = CommentService(repository, clock=lambda: NOW)  # type: ignore[arg-type]
    other = CURRENT_USER.__class__(
        id=UUID(int=999),
        email="other@example.com",
        username="other",
        email_verified_at=NOW,
        first_comment_approved_at=NOW,
        reply_email_enabled=True,
    )

    with pytest.raises(CommentNotFound):
        run(service.delete_comment(COMMENT_ID, other))
    deleted = run(service.delete_comment(COMMENT_ID, CURRENT_USER))

    assert deleted.status == CommentStatus.DELETED
    assert deleted.body is None
    assert repository.stored.body is None


def test_self_report_is_rejected_duplicate_conflicts_and_report_does_not_hide() -> None:
    author_id = UUID(int=888)
    repository = MemoryActions(stored_comment(status=CommentStatus.PUBLISHED, author_id=author_id))
    service = CommentService(
        repository,
        clock=lambda: NOW,
        uuid_factory=lambda: UUID(int=777),
    )  # type: ignore[arg-type]

    run(service.report_comment(COMMENT_ID, CURRENT_USER, "spam", None))
    with pytest.raises(DuplicateCommentReport):
        run(service.report_comment(COMMENT_ID, CURRENT_USER, "spam", None))
    assert repository.stored.status == CommentStatus.PUBLISHED

    repository.stored = replace(repository.stored, author_id=USER_ID)
    with pytest.raises(CommentReportNotAllowed):
        run(service.report_comment(COMMENT_ID, CURRENT_USER, "spam", None))
