import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy.dialects import postgresql

from company_api.auth import SessionRecord
from company_api.config import Settings
from company_api.main import create_app
from company_api.models import (
    Comment,
    CommentReport,
    CommentStatus,
    Document,
    EmailOutbox,
    Notification,
    NotificationType,
    ReportStatus,
    User,
    UserStatus,
)
from company_api.moderation_repository import (
    ModerationStateConflictError,
    SqlAlchemyModerationRepository,
)
from company_api.moderation_schemas import (
    ModerationCommentPage,
    ModerationCommentRead,
    ModerationReportPage,
    ModerationReportRead,
    ModerationUserPage,
    ModerationUserRead,
)
from company_api.moderation_service import ModerationConflict

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
COMMENT_ID = UUID("00000000-0000-0000-0000-000000000711")
REPORT_ID = UUID("00000000-0000-0000-0000-000000000712")
USER_ID = UUID("00000000-0000-0000-0000-000000000713")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000714")
ADMIN_SESSION = SessionRecord(
    token_hash="admin-hash",
    username="admin",
    credential_fingerprint="fingerprint",
    csrf_token="admin-csrf",
    expires_at=NOW,
)


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def unsubscribe_token_factory() -> tuple[UUID, str]:
    return UUID(int=999), "unsubscribe-token-digest"


def user(*, status: UserStatus = UserStatus.ACTIVE) -> User:
    return User(
        id=USER_ID,
        email="reader@example.com",
        normalized_email="reader@example.com",
        username="reader",
        normalized_username="reader",
        password_hash="secret-hash",
        status=status,
        email_verified_at=NOW,
        first_comment_approved_at=None,
        reply_email_enabled=True,
        created_at=NOW,
        updated_at=NOW,
    )


def stored_comment(*, status: CommentStatus = CommentStatus.PENDING) -> Comment:
    return Comment(
        id=COMMENT_ID,
        document_id=DOCUMENT_ID,
        author_id=USER_ID,
        parent_id=None,
        body="body",
        status=status,
        created_at=NOW,
    )


class OneRow:
    def __init__(self, row: tuple[object, ...]) -> None:
        self.row = row

    def one(self) -> tuple[object, ...]:
        return self.row


class ReportRows:
    def __init__(self, reports: list[CommentReport]) -> None:
        self.reports = reports

    def all(self) -> list[CommentReport]:
        return self.reports


class TransitionSession:
    def __init__(self, comment: Comment, author: User) -> None:
        self.comment = comment
        self.author = author
        self.other_pending = Comment(
            id=UUID(int=999),
            document_id=DOCUMENT_ID,
            author_id=USER_ID,
            parent_id=None,
            body="other",
            status=CommentStatus.PENDING,
            created_at=NOW,
        )
        self.reports = [
            CommentReport(
                id=REPORT_ID,
                comment_id=comment.id,
                reporter_id=UUID(int=444),
                reason="spam",
                details=None,
                status=ReportStatus.OPEN,
                created_at=NOW,
            )
        ]
        self.scalar_calls = 0
        self.statements: list[object] = []
        self.added: list[object] = []
        self.events: list[str] = []
        self.parent: Comment | None = None
        self.recipient: User | None = None
        self.document: Document | None = None

    async def __aenter__(self) -> "TransitionSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def scalar(self, statement: object) -> object | None:
        self.statements.append(statement)
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return self.comment
        if self.scalar_calls == 2:
            return self.author
        return self.author.username

    async def get(self, model: type[object], key: UUID) -> object | None:
        if model is Comment and self.parent is not None and key == self.parent.id:
            return self.parent
        if model is User and self.recipient is not None and key == self.recipient.id:
            return self.recipient
        if model is Document and self.document is not None and key == self.document.id:
            return self.document
        return None

    async def execute(self, statement: object) -> OneRow:
        self.statements.append(statement)
        return OneRow((self.comment, self.author.username, "Research"))

    async def scalars(self, statement: object) -> ReportRows:
        self.statements.append(statement)
        return ReportRows(self.reports)

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.events.append("flush")

    async def commit(self) -> None:
        self.events.append("commit")


class TransitionFactory:
    def __init__(self, session: TransitionSession) -> None:
        self.session = session

    def __call__(self) -> TransitionSession:
        return self.session


class UserAdminSession:
    def __init__(self, account: User) -> None:
        self.account = account
        self.scalar_calls = 0
        self.statements: list[object] = []
        self.events: list[str] = []

    async def __aenter__(self) -> "UserAdminSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def scalar(self, statement: object) -> object:
        self.statements.append(statement)
        self.scalar_calls += 1
        return self.account if self.scalar_calls == 1 else 2

    async def execute(self, statement: object) -> OneRow:
        self.statements.append(statement)
        self.events.append("delete_sessions")
        return OneRow(())

    async def flush(self) -> None:
        self.events.append("flush")

    async def commit(self) -> None:
        self.events.append("commit")


class UserAdminFactory:
    def __init__(self, session: UserAdminSession) -> None:
        self.session = session

    def __call__(self) -> UserAdminSession:
        return self.session


def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://company@postgres/company",
        admin_username="admin",
        admin_password_hash=PasswordHash.recommended().hash("correct horse battery staple"),
        session_cookie_secure=False,
    )


def moderation_comment() -> ModerationCommentRead:
    return ModerationCommentRead(
        id=COMMENT_ID,
        document_id=DOCUMENT_ID,
        document_title="Research",
        author_id=USER_ID,
        author_username="reader",
        parent_id=None,
        body="body",
        status=CommentStatus.PENDING,
        created_at=NOW,
        edited_at=None,
        moderated_at=None,
        deleted_at=None,
        moderation_reason=None,
        moderated_by=None,
    )


def moderation_report() -> ModerationReportRead:
    return ModerationReportRead(
        id=REPORT_ID,
        comment_id=COMMENT_ID,
        reporter_id=USER_ID,
        reporter_username="reporter",
        reason="spam",
        details=None,
        status=ReportStatus.OPEN,
        created_at=NOW,
        resolved_at=None,
        resolved_by=None,
        comment=moderation_comment(),
    )


def moderation_user() -> ModerationUserRead:
    return ModerationUserRead(
        id=USER_ID,
        email="reader@example.com",
        username="reader",
        status=UserStatus.ACTIVE,
        email_verified_at=NOW,
        first_comment_approved_at=None,
        created_at=NOW,
        comment_count=2,
    )


class FakeModeration:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.error: Exception | None = None

    async def list_comments(
        self, status: CommentStatus | None, cursor: str | None
    ) -> ModerationCommentPage:
        self.calls.append(("list_comments", status, cursor))
        return ModerationCommentPage(items=[moderation_comment()], next_cursor=None)

    async def approve(self, comment_id: UUID, administrator: str) -> ModerationCommentRead:
        self.calls.append(("approve", comment_id, administrator))
        if self.error is not None:
            raise self.error
        return moderation_comment().model_copy(update={"status": CommentStatus.PUBLISHED})

    async def reject(
        self, comment_id: UUID, administrator: str, reason: str
    ) -> ModerationCommentRead:
        self.calls.append(("reject", comment_id, administrator, reason))
        return moderation_comment().model_copy(update={"status": CommentStatus.REJECTED})

    async def remove(self, comment_id: UUID, administrator: str) -> ModerationCommentRead:
        self.calls.append(("remove", comment_id, administrator))
        return moderation_comment().model_copy(update={"status": CommentStatus.DELETED})

    async def list_reports(
        self, status: ReportStatus | None, cursor: str | None
    ) -> ModerationReportPage:
        self.calls.append(("list_reports", status, cursor))
        return ModerationReportPage(items=[moderation_report()], next_cursor=None)

    async def resolve_report(
        self, report_id: UUID, administrator: str, resolution: ReportStatus
    ) -> ModerationReportRead:
        self.calls.append(("resolve_report", report_id, administrator, resolution))
        return moderation_report().model_copy(update={"status": resolution})

    async def list_users(self, query: str, cursor: str | None) -> ModerationUserPage:
        self.calls.append(("list_users", query, cursor))
        return ModerationUserPage(items=[moderation_user()], next_cursor=None)

    async def suspend_user(self, user_id: UUID) -> ModerationUserRead:
        self.calls.append(("suspend", user_id))
        return moderation_user().model_copy(update={"status": UserStatus.SUSPENDED})

    async def restore_user(self, user_id: UUID) -> ModerationUserRead:
        self.calls.append(("restore", user_id))
        return moderation_user()


class FakeAdminAuth:
    async def authenticate(self, token: str) -> SessionRecord | None:
        return ADMIN_SESSION if token == "admin-session" else None

    def csrf_is_valid(self, session: SessionRecord, submitted: str) -> bool:
        return session is ADMIN_SESSION and submitted == "admin-csrf"


class Probe:
    async def check(self) -> None:
        return None


class Dispatcher:
    async def run(self, stop: object) -> None:
        await stop.wait()  # type: ignore[attr-defined]


def make_client(moderation: FakeModeration) -> TestClient:
    app = create_app(
        settings(),
        Probe(),
        library_service=object(),  # type: ignore[arg-type]
        auth_service=FakeAdminAuth(),  # type: ignore[arg-type]
        user_auth_service=object(),  # type: ignore[arg-type]
        comment_service=object(),  # type: ignore[arg-type]
        moderation_service=moderation,
        email_dispatcher=Dispatcher(),  # type: ignore[arg-type]
    )
    return TestClient(app)


def test_admin_reads_require_session_and_use_stable_cursor_parameters() -> None:
    moderation = FakeModeration()
    with make_client(moderation) as client:
        anonymous = client.get("/api/v1/admin/comments")
        client.cookies.set("company-admin-session", "admin-session")
        comments = client.get(
            "/api/v1/admin/comments", params={"status": "pending", "cursor": "next"}
        )
        reports = client.get(
            "/api/v1/admin/comment-reports", params={"status": "open", "cursor": "reports"}
        )
        users = client.get("/api/v1/admin/users", params={"q": "Reader", "cursor": "users"})

    assert anonymous.status_code == 401
    assert comments.status_code == reports.status_code == users.status_code == 200
    assert moderation.calls == [
        ("list_comments", CommentStatus.PENDING, "next"),
        ("list_reports", ReportStatus.OPEN, "reports"),
        ("list_users", "Reader", "users"),
    ]
    prohibited = {"password_hash", "token_hash", "csrf_token"}
    assert not prohibited.intersection(str(users.json()))


def test_admin_mutations_require_admin_csrf_and_validate_rejection_reason() -> None:
    moderation = FakeModeration()
    with make_client(moderation) as client:
        client.cookies.set("company-admin-session", "admin-session")
        missing_csrf = client.post(f"/api/v1/admin/comments/{COMMENT_ID}/approve")
        invalid_reason = client.post(
            f"/api/v1/admin/comments/{COMMENT_ID}/reject",
            headers={"X-CSRF-Token": "admin-csrf"},
            json={"reason": ""},
        )
        approved = client.post(
            f"/api/v1/admin/comments/{COMMENT_ID}/approve",
            headers={"X-CSRF-Token": "admin-csrf"},
        )
        rejected = client.post(
            f"/api/v1/admin/comments/{COMMENT_ID}/reject",
            headers={"X-CSRF-Token": "admin-csrf"},
            json={"reason": "off topic"},
        )
        removed = client.post(
            f"/api/v1/admin/comments/{COMMENT_ID}/remove",
            headers={"X-CSRF-Token": "admin-csrf"},
        )
        resolved = client.post(
            f"/api/v1/admin/comment-reports/{REPORT_ID}/resolve",
            headers={"X-CSRF-Token": "admin-csrf"},
            json={"resolution": "kept"},
        )
        suspended = client.post(
            f"/api/v1/admin/users/{USER_ID}/suspend",
            headers={"X-CSRF-Token": "admin-csrf"},
        )
        restored = client.post(
            f"/api/v1/admin/users/{USER_ID}/restore",
            headers={"X-CSRF-Token": "admin-csrf"},
        )

    assert missing_csrf.status_code == 403
    assert invalid_reason.status_code == 422
    assert [
        response.status_code
        for response in (approved, rejected, removed, resolved, suspended, restored)
    ] == [200] * 6
    assert ("reject", COMMENT_ID, "admin", "off topic") in moderation.calls


def test_stale_moderation_transition_returns_conflict() -> None:
    moderation = FakeModeration()
    moderation.error = ModerationConflict()
    with make_client(moderation) as client:
        client.cookies.set("company-admin-session", "admin-session")
        response = client.post(
            f"/api/v1/admin/comments/{COMMENT_ID}/approve",
            headers={"X-CSRF-Token": "admin-csrf"},
        )

    assert response.status_code == 409


def test_approve_locks_comment_and_author_publishes_only_target_and_trusts_active_author() -> None:
    session = TransitionSession(stored_comment(), user())
    repository = SqlAlchemyModerationRepository(
        TransitionFactory(session), unsubscribe_token_factory=unsubscribe_token_factory
    )  # type: ignore[arg-type]

    approved = run(repository.approve(COMMENT_ID, "admin", now=NOW))

    assert approved.status == CommentStatus.PUBLISHED
    assert session.comment.status == CommentStatus.PUBLISHED
    assert session.author.first_comment_approved_at == NOW
    assert session.other_pending.status == CommentStatus.PENDING
    notifications = [item for item in session.added if isinstance(item, Notification)]
    assert [item.type for item in notifications] == [NotificationType.COMMENT_APPROVED]
    locks = [
        str(statement.compile(dialect=postgresql.dialect()))
        for statement in session.statements[:2]  # type: ignore[attr-defined]
    ]
    assert all("FOR UPDATE" in statement for statement in locks)
    assert session.events == ["flush", "commit"]


def test_reject_requires_pending_state_records_reason_and_notifies_once() -> None:
    session = TransitionSession(stored_comment(), user())
    repository = SqlAlchemyModerationRepository(
        TransitionFactory(session), unsubscribe_token_factory=unsubscribe_token_factory
    )  # type: ignore[arg-type]

    rejected = run(repository.reject(COMMENT_ID, "admin", "off topic", now=NOW))

    assert rejected.status == CommentStatus.REJECTED
    assert session.comment.moderation_reason == "off topic"
    notifications = [item for item in session.added if isinstance(item, Notification)]
    assert [item.type for item in notifications] == [NotificationType.COMMENT_REJECTED]

    stale_session = TransitionSession(stored_comment(status=CommentStatus.PUBLISHED), user())
    stale_repository = SqlAlchemyModerationRepository(
        TransitionFactory(stale_session),  # type: ignore[arg-type]
        unsubscribe_token_factory=unsubscribe_token_factory,
    )
    with pytest.raises(ModerationStateConflictError):
        run(stale_repository.reject(COMMENT_ID, "admin", "late", now=NOW))
    assert stale_session.events == []


def test_pending_reply_notification_is_created_only_when_approval_publishes() -> None:
    reply = stored_comment()
    root_id = UUID(int=332)
    direct_reply_id = UUID(int=333)
    recipient_id = UUID(int=334)
    root_author_id = UUID(int=336)
    reply.parent_id = root_id
    reply.reply_to_id = direct_reply_id
    session = TransitionSession(reply, user())
    session.parent = Comment(
        id=direct_reply_id,
        document_id=DOCUMENT_ID,
        author_id=recipient_id,
        parent_id=root_id,
        reply_to_id=root_id,
        body="direct reply",
        status=CommentStatus.PUBLISHED,
        created_at=NOW,
    )
    session.root = Comment(
        id=root_id,
        document_id=DOCUMENT_ID,
        author_id=root_author_id,
        parent_id=None,
        reply_to_id=None,
        body="root",
        status=CommentStatus.PUBLISHED,
        created_at=NOW,
    )
    session.recipient = User(
        id=recipient_id,
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
    session.document = Document(
        id=DOCUMENT_ID,
        company_id=UUID(int=335),
        title="Research",
        format="html",  # type: ignore[arg-type]
        source_path="source",
        rendered_path=None,
        original_filename="research.html",
        uploaded_at=NOW,
    )
    assert session.added == []
    repository = SqlAlchemyModerationRepository(
        TransitionFactory(session), unsubscribe_token_factory=unsubscribe_token_factory
    )  # type: ignore[arg-type]

    run(repository.approve(COMMENT_ID, "admin", now=NOW))

    notifications = [item for item in session.added if isinstance(item, Notification)]
    assert [item.type for item in notifications] == [
        NotificationType.COMMENT_APPROVED,
        NotificationType.REPLY,
    ]
    reply_notification = notifications[1]
    assert reply_notification.recipient_id == recipient_id
    assert reply_notification.recipient_id != root_author_id
    outboxes = [item for item in session.added if isinstance(item, EmailOutbox)]
    assert len(outboxes) == 1
    assert outboxes[0].recipient == "recipient@example.com"


def test_remove_soft_deletes_comment_and_resolves_all_open_reports() -> None:
    session = TransitionSession(stored_comment(status=CommentStatus.PUBLISHED), user())
    repository = SqlAlchemyModerationRepository(
        TransitionFactory(session), unsubscribe_token_factory=unsubscribe_token_factory
    )  # type: ignore[arg-type]

    removed = run(repository.remove(COMMENT_ID, "admin", now=NOW))

    assert removed.status == CommentStatus.DELETED
    assert session.comment.body is None
    assert session.comment.deleted_at == NOW
    assert session.reports[0].status == ReportStatus.REMOVED
    assert session.reports[0].resolved_by == "admin"
    assert session.events == ["flush", "commit"]


def test_suspend_revokes_sessions_atomically_and_restore_preserves_trust() -> None:
    account = user()
    account.first_comment_approved_at = NOW
    suspend_session = UserAdminSession(account)
    suspend_repository = SqlAlchemyModerationRepository(
        UserAdminFactory(suspend_session),  # type: ignore[arg-type]
        unsubscribe_token_factory=unsubscribe_token_factory,
    )

    suspended = run(suspend_repository.suspend_user(USER_ID, now=NOW))

    assert suspended.status == UserStatus.SUSPENDED
    assert suspended.first_comment_approved_at == NOW
    deletion = suspend_session.statements[1].compile(dialect=postgresql.dialect())  # type: ignore[attr-defined]
    assert "DELETE FROM user_sessions" in str(deletion)
    assert suspend_session.events == ["delete_sessions", "flush", "commit"]

    restore_session = UserAdminSession(account)
    restore_repository = SqlAlchemyModerationRepository(
        UserAdminFactory(restore_session),  # type: ignore[arg-type]
        unsubscribe_token_factory=unsubscribe_token_factory,
    )
    restored = run(restore_repository.restore_user(USER_ID, now=NOW))

    assert restored.status == UserStatus.ACTIVE
    assert restored.first_comment_approved_at == NOW


def test_suspend_then_restore_returns_unverified_account_to_pending_verification() -> None:
    account = user(status=UserStatus.PENDING_VERIFICATION)
    account.email_verified_at = None
    suspend_session = UserAdminSession(account)
    suspend_repository = SqlAlchemyModerationRepository(
        UserAdminFactory(suspend_session),  # type: ignore[arg-type]
        unsubscribe_token_factory=unsubscribe_token_factory,
    )

    suspended = run(suspend_repository.suspend_user(USER_ID, now=NOW))

    assert suspended.status == UserStatus.SUSPENDED
    restore_session = UserAdminSession(account)
    restore_repository = SqlAlchemyModerationRepository(
        UserAdminFactory(restore_session),  # type: ignore[arg-type]
        unsubscribe_token_factory=unsubscribe_token_factory,
    )

    restored = run(restore_repository.restore_user(USER_ID, now=NOW))

    assert restored.status == UserStatus.PENDING_VERIFICATION
    assert restored.email_verified_at is None
