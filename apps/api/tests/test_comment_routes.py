from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from company_api.comment_schemas import (
    CommentAuthorRead,
    CommentPage,
    CommentRead,
    CommentThreadRead,
)
from company_api.comment_service import CommentNotFound
from company_api.config import Settings
from company_api.email_outbox import EmailJob
from company_api.email_tokens import EmailTokenSigner
from company_api.main import _message_factory, create_app
from company_api.models import CommentStatus
from company_api.user_auth import CurrentUser, UserSessionRecord

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000601")
COMMENT_ID = UUID("00000000-0000-0000-0000-000000000602")
USER_ID = UUID("00000000-0000-0000-0000-000000000603")
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
    email="private@example.com",
    username="reader",
    email_verified_at=NOW,
    first_comment_approved_at=NOW,
    reply_email_enabled=True,
)
SESSION = UserSessionRecord(
    token_hash="hash",
    user_id=USER_ID,
    csrf_token="csrf",
    expires_at=NOW,
    current_user=CURRENT_USER,
)


def item(*, status: CommentStatus = CommentStatus.PUBLISHED) -> CommentRead:
    return CommentRead(
        id=COMMENT_ID,
        document_id=DOCUMENT_ID,
        parent_id=None,
        body="public body",
        status=status,
        author=CommentAuthorRead(id=USER_ID, username="reader"),
        created_at=NOW,
        edited_at=None,
        can_edit=True,
        can_delete=True,
        can_report=False,
    )


class FakeComments:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.thread_error: Exception | None = None

    async def list_comments(
        self, document_id: UUID, viewer_id: UUID | None, cursor: str | None
    ) -> CommentPage:
        self.calls.append(("list", document_id, viewer_id, cursor))
        return CommentPage(items=[item()], viewer_pending=[], next_cursor=None, total_count=1)

    async def create_comment(
        self,
        document_id: UUID,
        actor: CurrentUser,
        body: str,
        parent_id: UUID | None,
    ) -> CommentRead:
        self.calls.append(("create", document_id, actor, body, parent_id))
        return item(status=CommentStatus.PUBLISHED)

    async def get_thread(self, comment_id: UUID, viewer_id: UUID | None) -> CommentThreadRead:
        self.calls.append(("thread", comment_id, viewer_id))
        if self.thread_error is not None:
            raise self.thread_error
        return CommentThreadRead(root=item(), target_comment_id=comment_id)


class FakeAuth:
    async def authenticate(self, token: str) -> UserSessionRecord | None:
        return SESSION if token == "session" else None

    def csrf_is_valid(self, session: UserSessionRecord, submitted: str) -> bool:
        return session is SESSION and submitted == "csrf"


class Probe:
    async def check(self) -> None:
        return None


class Dispatcher:
    async def run(self, stop: object) -> None:
        await stop.wait()  # type: ignore[attr-defined]


@pytest.fixture
def comments() -> FakeComments:
    return FakeComments()


def make_client(comments: FakeComments, *, writes_enabled: bool = True) -> TestClient:
    application = create_app(
        settings(writes_enabled=writes_enabled),
        Probe(),
        library_service=object(),  # type: ignore[arg-type]
        auth_service=object(),  # type: ignore[arg-type]
        user_auth_service=FakeAuth(),  # type: ignore[arg-type]
        comment_service=comments,
        email_dispatcher=Dispatcher(),  # type: ignore[arg-type]
    )
    return TestClient(application)


def test_public_list_uses_optional_viewer_and_omits_private_fields(
    comments: FakeComments,
) -> None:
    with make_client(comments) as client:
        anonymous = client.get(f"/api/v1/documents/{DOCUMENT_ID}/comments")
        client.cookies.set("company-user-session", "session")
        signed_in = client.get(
            f"/api/v1/documents/{DOCUMENT_ID}/comments", params={"cursor": "next"}
        )

    assert anonymous.status_code == 200
    assert signed_in.status_code == 200
    assert comments.calls[:2] == [
        ("list", DOCUMENT_ID, None, None),
        ("list", DOCUMENT_ID, USER_ID, "next"),
    ]
    prohibited = {"email", "password_hash", "token_hash", "source_path", "rendered_path"}
    assert not prohibited.intersection(str(signed_in.json()))


def test_post_requires_user_csrf_and_returns_201(comments: FakeComments) -> None:
    with make_client(comments) as client:
        anonymous = client.post(f"/api/v1/documents/{DOCUMENT_ID}/comments", json={"body": "hello"})
        client.cookies.set("company-user-session", "session")
        missing_csrf = client.post(
            f"/api/v1/documents/{DOCUMENT_ID}/comments", json={"body": "hello"}
        )
        created = client.post(
            f"/api/v1/documents/{DOCUMENT_ID}/comments",
            headers={"X-CSRF-Token": "csrf"},
            json={"body": "hello"},
        )

    assert anonymous.status_code == 401
    assert missing_csrf.status_code == 403
    assert created.status_code == 201
    assert comments.calls[-1][:3] == ("create", DOCUMENT_ID, CURRENT_USER)


def test_read_only_flag_rejects_writes_but_keeps_reads(comments: FakeComments) -> None:
    with make_client(comments, writes_enabled=False) as client:
        read = client.get(f"/api/v1/documents/{DOCUMENT_ID}/comments")
        client.cookies.set("company-user-session", "session")
        write = client.post(
            f"/api/v1/documents/{DOCUMENT_ID}/comments",
            headers={"X-CSRF-Token": "csrf"},
            json={"body": "hello"},
        )

    assert read.status_code == 200
    assert write.status_code == 503
    assert write.json() == {"detail": "评论区暂时只读"}


def test_private_thread_is_404(comments: FakeComments) -> None:
    comments.thread_error = CommentNotFound()
    with make_client(comments) as client:
        response = client.get(f"/api/v1/comments/{COMMENT_ID}/thread")

    assert response.status_code == 404


def test_reply_email_message_supports_tokenless_deep_links() -> None:
    job = EmailJob(
        id=COMMENT_ID,
        token_id=None,
        template="comment_reply",
        recipient="recipient@example.com",
        payload={
            "username": "recipient",
            "actor_username": "reader",
            "company_id": str(UUID(int=700)),
            "document_id": str(DOCUMENT_ID),
            "comment_id": str(COMMENT_ID),
        },
        attempts=1,
    )

    message = _message_factory(EmailTokenSigner("test-signing-key"), settings())(job)

    assert message.recipient == "recipient@example.com"
    assert "reader 回复了你的评论" in message.text_body
    assert (
        f"/?company={UUID(int=700)}&document={DOCUMENT_ID}&comment={COMMENT_ID}"
        in message.text_body
    )
