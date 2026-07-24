from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from company_api.config import Settings
from company_api.email_outbox import EmailJob
from company_api.email_tokens import EmailTokenSigner
from company_api.main import _message_factory, create_app
from company_api.models import NotificationType, UserToken, UserTokenPurpose
from company_api.notification_service import NotificationNotFound
from company_api.user_auth import CurrentUser, UserSessionRecord
from company_api.user_schemas import NotificationPage, NotificationRead

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
USER_ID = UUID("00000000-0000-0000-0000-000000000811")
NOTIFICATION_ID = UUID("00000000-0000-0000-0000-000000000812")
ADMIN_HASH = PasswordHash.recommended().hash("correct horse battery staple")
CURRENT_USER = CurrentUser(
    id=USER_ID,
    email="reader@example.com",
    username="reader",
    email_verified_at=NOW,
    first_comment_approved_at=NOW,
    reply_email_enabled=True,
)
SESSION = UserSessionRecord(
    token_hash="stored-session",
    user_id=USER_ID,
    csrf_token="session-csrf",
    expires_at=NOW,
    current_user=CURRENT_USER,
)


def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://company@postgres/company",
        admin_username="admin",
        admin_password_hash=ADMIN_HASH,
        session_cookie_secure=False,
    )


class Probe:
    async def check(self) -> None:
        return None


class Dispatcher:
    async def run(self, stop: object) -> None:
        await stop.wait()  # type: ignore[attr-defined]


class UserAuth:
    async def authenticate(self, token: str) -> UserSessionRecord | None:
        return SESSION if token == "session" else None

    def csrf_is_valid(self, session: UserSessionRecord, submitted_token: str) -> bool:
        return session is SESSION and submitted_token == "session-csrf"


def item(*, read_at: datetime | None = None) -> NotificationRead:
    return NotificationRead(
        id=NOTIFICATION_ID,
        type=NotificationType.REPLY,
        company_id=UUID(int=1),
        document_id=UUID(int=2),
        comment_id=UUID(int=3),
        actor_username="writer",
        excerpt="safe excerpt",
        message="writer 回复了你的评论",
        created_at=NOW,
        read_at=read_at,
    )


class Notifications:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.error: Exception | None = None

    async def list(self, user_id: UUID) -> NotificationPage:
        self.calls.append(("list", user_id))
        return NotificationPage(items=[item()], unread_count=1)

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> NotificationRead:
        self.calls.append(("mark_read", notification_id, user_id))
        if self.error is not None:
            raise self.error
        return item(read_at=NOW)

    async def mark_all_read(self, user_id: UUID) -> None:
        self.calls.append(("mark_all_read", user_id))

    async def unsubscribe(self, token: str, *, anonymous_challenge: str | None = None) -> None:
        self.calls.append(("unsubscribe", token, anonymous_challenge))
        if self.error is not None:
            raise self.error


@pytest.fixture
def notifications() -> Notifications:
    return Notifications()


@pytest.fixture
def client(notifications: Notifications) -> TestClient:
    app = create_app(
        settings(),
        Probe(),
        library_service=object(),  # type: ignore[arg-type]
        auth_service=object(),  # type: ignore[arg-type]
        user_auth_service=UserAuth(),  # type: ignore[arg-type]
        notification_service=notifications,  # type: ignore[arg-type]
        email_dispatcher=Dispatcher(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client


def authenticate(client: TestClient) -> None:
    client.cookies.set("company-user-session", "session")


def test_notifications_are_private_and_read_mutations_require_csrf(
    client: TestClient, notifications: Notifications
) -> None:
    anonymous = client.get("/api/v1/users/me/notifications")
    authenticate(client)
    listed = client.get("/api/v1/users/me/notifications")
    missing_csrf = client.patch(f"/api/v1/users/me/notifications/{NOTIFICATION_ID}")
    marked = client.patch(
        f"/api/v1/users/me/notifications/{NOTIFICATION_ID}",
        headers={"X-CSRF-Token": "session-csrf"},
    )
    all_read = client.post(
        "/api/v1/users/me/notifications/read-all",
        headers={"X-CSRF-Token": "session-csrf"},
    )

    assert anonymous.status_code == 401
    assert listed.status_code == 200
    assert listed.json()["items"][0]["excerpt"] == "safe excerpt"
    assert missing_csrf.status_code == 403
    assert marked.status_code == 200
    assert marked.json()["read_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert all_read.status_code == 204
    assert notifications.calls == [
        ("list", USER_ID),
        ("mark_read", NOTIFICATION_ID, USER_ID),
        ("mark_all_read", USER_ID),
    ]
    for response in (listed, marked, all_read):
        assert response.headers["cache-control"] == "no-store"


def test_notification_ownership_is_a_safe_not_found_response(
    client: TestClient, notifications: Notifications
) -> None:
    authenticate(client)
    notifications.error = NotificationNotFound()

    response = client.patch(
        f"/api/v1/users/me/notifications/{NOTIFICATION_ID}",
        headers={"X-CSRF-Token": "session-csrf"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "通知不存在"}


def test_unsubscribe_accepts_an_authenticated_session_or_anonymous_challenge(
    client: TestClient, notifications: Notifications
) -> None:
    missing_challenge = client.post("/api/v1/user-auth/unsubscribe", json={"token": "email-token"})
    anonymous = client.post(
        "/api/v1/user-auth/unsubscribe",
        headers={"X-CSRF-Token": "anonymous-challenge"},
        json={"token": "email-token"},
    )
    authenticate(client)
    bad_session_csrf = client.post(
        "/api/v1/user-auth/unsubscribe",
        headers={"X-CSRF-Token": "wrong-token"},
        json={"token": "email-token"},
    )
    authenticated = client.post(
        "/api/v1/user-auth/unsubscribe",
        headers={"X-CSRF-Token": "session-csrf"},
        json={"token": "email-token"},
    )

    assert missing_challenge.status_code == 422
    assert anonymous.status_code == 200
    assert anonymous.json() == {"message": "已停止接收评论回复邮件"}
    assert bad_session_csrf.status_code == 403
    assert bad_session_csrf.json() == {"detail": "CSRF 校验失败，请刷新页面后重试"}
    assert authenticated.status_code == 200
    assert notifications.calls == [
        ("unsubscribe", "email-token", "anonymous-challenge"),
        ("unsubscribe", "email-token", None),
    ]


def test_unsubscribe_hides_unexpected_delivery_failures(
    client: TestClient, notifications: Notifications
) -> None:
    notifications.error = RuntimeError("SMTP password leaked")

    response = client.post(
        "/api/v1/user-auth/unsubscribe",
        headers={"X-CSRF-Token": "anonymous-challenge"},
        json={"token": "email-token"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "服务器暂时无法处理请求，请稍后重试"}
    assert "SMTP" not in response.text


def test_reply_email_escapes_content_and_reconstructs_its_stored_unsubscribe_token() -> None:
    token_id = UUID(int=99)
    signer = EmailTokenSigner("x" * 32)
    message = _message_factory(signer, settings())(
        EmailJob(
            id=NOTIFICATION_ID,
            token_id=token_id,
            template="comment_reply",
            recipient="reader@example.com",
            payload={
                "username": "<reader>",
                "actor_username": "<writer>",
                "company_id": str(UUID(int=1)),
                "document_id": str(UUID(int=2)),
                "comment_id": str(UUID(int=3)),
            },
            attempts=1,
        )
    )

    token = signer.issue(token_id, UserTokenPurpose.UNSUBSCRIBE)
    stored = UserToken(
        id=token_id,
        token_hash=signer.digest(token),
        purpose=UserTokenPurpose.UNSUBSCRIBE,
        user_id=USER_ID,
        created_at=NOW,
        expires_at=NOW,
    )
    assert "&lt;reader&gt;" in message.text_body
    assert "&lt;writer&gt;" in message.text_body
    assert f"/?unsubscribe={token}" in message.text_body
    assert signer.matches(stored.id, stored.purpose, stored.token_hash, token)


def test_reply_email_without_an_unsubscribe_token_is_rejected_before_delivery() -> None:
    job = EmailJob(
        id=NOTIFICATION_ID,
        token_id=None,
        template="comment_reply",
        recipient="reader@example.com",
        payload={
            "username": "reader",
            "actor_username": "writer",
            "company_id": str(UUID(int=1)),
            "document_id": str(UUID(int=2)),
            "comment_id": str(UUID(int=3)),
        },
        attempts=1,
    )

    with pytest.raises(ValueError, match="unsubscribe token"):
        _message_factory(EmailTokenSigner("x" * 32), settings())(job)
