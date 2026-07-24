import logging
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from company_api.config import Settings
from company_api.main import create_app
from company_api.user_auth import (
    AccountSuspended,
    ChallengeInvalid,
    CredentialsInvalid,
    CurrentUser,
    NewUserSession,
    RateLimitExceeded,
    RegistrationClosed,
    TokenInvalid,
    UsernameChangeTooSoon,
    UsernameUnavailable,
    UserSessionRecord,
)

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2026, 8, 23, 8, 0, tzinfo=UTC)
USER_ID = UUID("00000000-0000-0000-0000-000000000501")
ADMIN_HASH = PasswordHash.recommended().hash("correct horse battery staple")


def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://company@postgres/company",
        admin_username="admin",
        admin_password_hash=ADMIN_HASH,
        session_cookie_secure=False,
        user_registration_enabled=True,
    )


class SuccessfulProbe:
    async def check(self) -> None:
        return None


class IdleDispatcher:
    async def run(self, stop: object) -> None:
        await stop.wait()  # type: ignore[attr-defined]


class AnonymousAdminAuth:
    def __init__(self) -> None:
        self.authenticated_tokens: list[str] = []

    async def authenticate(self, session_token: str) -> None:
        self.authenticated_tokens.append(session_token)
        return None


CURRENT_USER = CurrentUser(
    id=USER_ID,
    email="reader@example.com",
    username="价值读者",
    email_verified_at=NOW,
    first_comment_approved_at=None,
    reply_email_enabled=True,
)
SESSION = UserSessionRecord(
    token_hash="stored-user-session-hash",
    user_id=USER_ID,
    csrf_token="session-csrf",
    expires_at=EXPIRES_AT,
    current_user=CURRENT_USER,
)
NEW_SESSION = NewUserSession(
    session_token="new-user-session-token",
    csrf_token="new-session-csrf",
    expires_at=EXPIRES_AT,
    current_user=CURRENT_USER,
)


class FakeUserAuth:
    def __init__(self) -> None:
        self.sessions = {"existing-user-session": SESSION}
        self.calls: list[tuple[object, ...]] = []
        self.error: Exception | None = None

    def _raise_error(self) -> None:
        if self.error is not None:
            raise self.error

    async def issue_challenge(self) -> str:
        self.calls.append(("issue_challenge",))
        return "anonymous-challenge"

    async def register(self, email: str, username: str, password: str, challenge: str) -> None:
        self.calls.append(("register", email, username, password, challenge))
        self._raise_error()

    async def verify_email(self, token: str, challenge: str) -> NewUserSession:
        self.calls.append(("verify_email", token, challenge))
        self._raise_error()
        return NEW_SESSION

    async def login(self, email: str, password: str, challenge: str) -> NewUserSession:
        self.calls.append(("login", email, password, challenge))
        self._raise_error()
        return NEW_SESSION

    async def authenticate(self, session_token: str) -> UserSessionRecord | None:
        self.calls.append(("authenticate", session_token))
        return self.sessions.get(session_token)

    def csrf_is_valid(self, session: UserSessionRecord, submitted_token: str) -> bool:
        self.calls.append(("csrf_is_valid", session, submitted_token))
        return submitted_token == session.csrf_token

    async def logout(self, session: UserSessionRecord) -> None:
        self.calls.append(("logout", session))

    async def request_password_reset(self, email: str, challenge: str) -> None:
        self.calls.append(("request_password_reset", email, challenge))
        self._raise_error()

    async def reset_password(self, token: str, password: str, challenge: str) -> NewUserSession:
        self.calls.append(("reset_password", token, password, challenge))
        self._raise_error()
        return NEW_SESSION

    async def update_username(self, session: UserSessionRecord, username: str) -> CurrentUser:
        self.calls.append(("update_username", session, username))
        self._raise_error()
        return CURRENT_USER

    async def update_password(
        self,
        session: UserSessionRecord,
        current_password: str,
        password: str,
    ) -> NewUserSession:
        self.calls.append(("update_password", session, current_password, password))
        self._raise_error()
        return NEW_SESSION

    async def update_preferences(
        self, session: UserSessionRecord, *, reply_email_enabled: bool
    ) -> CurrentUser:
        self.calls.append(("update_preferences", session, reply_email_enabled))
        self._raise_error()
        return CURRENT_USER

    async def delete_account(self, session: UserSessionRecord, password: str) -> None:
        self.calls.append(("delete_account", session, password))
        self._raise_error()


@pytest.fixture
def auth() -> FakeUserAuth:
    return FakeUserAuth()


@pytest.fixture
def admin_auth() -> AnonymousAdminAuth:
    return AnonymousAdminAuth()


@pytest.fixture
def client(auth: FakeUserAuth, admin_auth: AnonymousAdminAuth) -> TestClient:
    application = create_app(
        settings(),
        SuccessfulProbe(),
        library_service=object(),  # type: ignore[arg-type]
        auth_service=admin_auth,  # type: ignore[arg-type]
        user_auth_service=auth,
        email_dispatcher=IdleDispatcher(),  # type: ignore[arg-type]
    )
    with TestClient(application) as test_client:
        yield test_client


def authenticate(client: TestClient) -> None:
    client.cookies.set("company-user-session", "existing-user-session")


def assert_no_store(response: object) -> None:
    assert response.headers["cache-control"] == "no-store"  # type: ignore[attr-defined]


def test_anonymous_session_returns_one_time_challenge_and_registration_state(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/user-auth/session")

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": False,
        "user": None,
        "csrf_token": "anonymous-challenge",
        "expires_at": None,
        "registration_enabled": True,
    }
    assert_no_store(response)


def test_authenticated_session_and_me_return_the_private_account(client: TestClient) -> None:
    authenticate(client)

    session_response = client.get("/api/v1/user-auth/session")
    me_response = client.get("/api/v1/users/me")

    expected_user = {
        "id": str(USER_ID),
        "email": "reader@example.com",
        "username": "价值读者",
        "email_verified_at": NOW.isoformat().replace("+00:00", "Z"),
        "first_comment_approved_at": None,
        "reply_email_enabled": True,
    }
    assert session_response.json() == {
        "authenticated": True,
        "user": expected_user,
        "csrf_token": "session-csrf",
        "expires_at": EXPIRES_AT.isoformat().replace("+00:00", "Z"),
        "registration_enabled": True,
    }
    assert me_response.json() == expected_user
    assert_no_store(session_response)
    assert_no_store(me_response)


def test_registration_and_password_reset_request_use_generic_responses(
    client: TestClient, auth: FakeUserAuth
) -> None:
    registered = client.post(
        "/api/v1/user-auth/register",
        headers={"X-CSRF-Token": "anonymous-challenge"},
        json={"email": "reader@example.com", "username": "reader_01", "password": "password1"},
    )
    reset = client.post(
        "/api/v1/user-auth/password-reset/request",
        headers={"X-CSRF-Token": "second-challenge"},
        json={"email": "unknown@example.com"},
    )

    assert registered.status_code == 202
    assert registered.json() == {"message": "请检查邮箱以完成注册"}
    assert reset.status_code == 202
    assert reset.json() == {"message": "如果该邮箱已注册，我们已发送密码重置邮件"}
    assert (
        "register",
        "reader@example.com",
        "reader_01",
        "password1",
        "anonymous-challenge",
    ) in auth.calls
    assert ("request_password_reset", "unknown@example.com", "second-challenge") in auth.calls
    assert_no_store(registered)
    assert_no_store(reset)


@pytest.mark.parametrize(
    ("path", "body", "expected_call"),
    [
        (
            "/api/v1/user-auth/verify-email",
            {"token": "verification-token"},
            ("verify_email", "verification-token", "anonymous-challenge"),
        ),
        (
            "/api/v1/user-auth/login",
            {"email": "reader@example.com", "password": "password1"},
            ("login", "reader@example.com", "password1", "anonymous-challenge"),
        ),
        (
            "/api/v1/user-auth/password-reset/confirm",
            {"token": "reset-token", "password": "replacement1"},
            ("reset_password", "reset-token", "replacement1", "anonymous-challenge"),
        ),
    ],
)
def test_session_creating_routes_set_the_separate_user_cookie(
    client: TestClient,
    auth: FakeUserAuth,
    path: str,
    body: dict[str, str],
    expected_call: tuple[object, ...],
) -> None:
    response = client.post(path, headers={"X-CSRF-Token": "anonymous-challenge"}, json=body)

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("company-user-session=new-user-session-token;")
    assert "HttpOnly" in cookie
    assert "Max-Age=2592000" in cookie
    assert "Path=/" in cookie
    assert "SameSite=strict" in cookie
    assert "Secure" not in cookie
    assert "company-admin-session" not in cookie
    assert expected_call in auth.calls
    assert_no_store(response)


def test_logout_revokes_session_and_deletes_only_the_user_cookie(
    client: TestClient, auth: FakeUserAuth
) -> None:
    authenticate(client)
    response = client.post("/api/v1/user-auth/logout", headers={"X-CSRF-Token": "session-csrf"})

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert cookie.startswith('company-user-session="";')
    assert "Max-Age=0" in cookie
    assert "company-admin-session" not in cookie
    assert ("logout", SESSION) in auth.calls
    assert_no_store(response)


def test_account_mutations_update_profile_password_preferences_and_delete(
    client: TestClient, auth: FakeUserAuth
) -> None:
    authenticate(client)
    headers = {"X-CSRF-Token": "session-csrf"}

    profile = client.patch(
        "/api/v1/users/me/profile", headers=headers, json={"username": "new_reader"}
    )
    preferences = client.patch(
        "/api/v1/users/me/preferences",
        headers=headers,
        json={"reply_email_enabled": False},
    )
    deleted = client.request(
        "DELETE", "/api/v1/users/me", headers=headers, json={"password": "replacement1"}
    )
    authenticate(client)
    password = client.patch(
        "/api/v1/users/me/password",
        headers=headers,
        json={"current_password": "password1", "password": "replacement1"},
    )

    assert profile.status_code == 200
    assert profile.json()["username"] == "价值读者"
    assert password.status_code == 200
    assert password.json()["csrf_token"] == "new-session-csrf"
    assert "new-user-session-token" in password.headers["set-cookie"]
    assert preferences.status_code == 200
    assert preferences.json()["reply_email_enabled"] is True
    assert deleted.status_code == 204
    assert 'company-user-session=""' in deleted.headers["set-cookie"]
    assert ("update_username", SESSION, "new_reader") in auth.calls
    assert ("update_password", SESSION, "password1", "replacement1") in auth.calls
    assert ("update_preferences", SESSION, False) in auth.calls
    assert ("delete_account", SESSION, "replacement1") in auth.calls
    for response in (profile, password, preferences, deleted):
        assert_no_store(response)


def test_authenticated_mutation_distinguishes_missing_session_from_bad_csrf(
    client: TestClient,
) -> None:
    anonymous = client.patch(
        "/api/v1/users/me/profile",
        headers={"X-CSRF-Token": "session-csrf"},
        json={"username": "new_reader"},
    )
    authenticate(client)
    bad_csrf = client.patch(
        "/api/v1/users/me/profile",
        headers={"X-CSRF-Token": "wrong-token"},
        json={"username": "new_reader"},
    )

    assert anonymous.status_code == 401
    assert anonymous.json() == {"detail": "用户会话已失效，请重新登录"}
    assert bad_csrf.status_code == 403
    assert bad_csrf.json() == {"detail": "CSRF 校验失败，请刷新页面后重试"}


def test_current_password_errors_do_not_invalidate_an_authenticated_session(
    client: TestClient, auth: FakeUserAuth
) -> None:
    authenticate(client)
    auth.error = CredentialsInvalid()
    headers = {"X-CSRF-Token": "session-csrf"}

    password = client.patch(
        "/api/v1/users/me/password",
        headers=headers,
        json={"current_password": "wrong-pass", "password": "replacement1"},
    )
    deleted = client.request(
        "DELETE", "/api/v1/users/me", headers=headers, json={"password": "wrong-pass"}
    )

    for response in (password, deleted):
        assert response.status_code == 422
        assert response.json() == {"detail": "当前密码错误"}
        assert "set-cookie" not in response.headers
        assert_no_store(response)


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (ChallengeInvalid(), 403, "请求校验已失效，请刷新页面后重试"),
        (CredentialsInvalid(), 401, "邮箱或密码错误"),
        (RegistrationClosed(), 503, "注册暂未开放"),
        (UsernameUnavailable(), 409, "用户名已被使用"),
        (TokenInvalid(), 422, "链接无效或已过期"),
        (AccountSuspended(), 403, "账号已停用"),
        (UsernameChangeTooSoon(), 409, "用户名每 30 天只能修改一次"),
        (RateLimitExceeded(), 429, "操作过于频繁，请稍后重试"),
        (ValueError(), 422, "提交的数据无效"),
    ],
)
def test_domain_errors_have_fixed_safe_http_responses(
    client: TestClient,
    auth: FakeUserAuth,
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    auth.error = error

    response = client.post(
        "/api/v1/user-auth/login",
        headers={"X-CSRF-Token": "anonymous-challenge"},
        json={"email": "reader@example.com", "password": "password1"},
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert type(error).__name__ not in response.text
    assert_no_store(response)


def test_user_cookie_never_authenticates_the_administrator_route(
    client: TestClient, admin_auth: AnonymousAdminAuth
) -> None:
    client.cookies.set("company-user-session", "existing-user-session")

    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "session-csrf"})

    assert response.status_code == 401
    assert admin_auth.authenticated_tokens == [""]


def test_secure_configuration_sets_host_prefixed_secure_user_cookie(
    auth: FakeUserAuth, admin_auth: AnonymousAdminAuth
) -> None:
    secure_settings = settings().model_copy(update={"session_cookie_secure": True})
    application = create_app(
        secure_settings,
        SuccessfulProbe(),
        library_service=object(),  # type: ignore[arg-type]
        auth_service=admin_auth,  # type: ignore[arg-type]
        user_auth_service=auth,
        email_dispatcher=IdleDispatcher(),  # type: ignore[arg-type]
    )

    with TestClient(application) as secure_client:
        response = secure_client.post(
            "/api/v1/user-auth/login",
            headers={"X-CSRF-Token": "anonymous-challenge"},
            json={"email": "reader@example.com", "password": "password1"},
        )

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-company-user-session=new-user-session-token;")
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/" in cookie


def test_unhandled_account_error_returns_safe_non_cacheable_response(
    client: TestClient,
    auth: FakeUserAuth,
    caplog: pytest.LogCaptureFixture,
) -> None:
    auth.error = RuntimeError("reader@example.com password1 anonymous-challenge")

    with caplog.at_level(logging.ERROR, logger="company_api.main"):
        response = client.post(
            "/api/v1/user-auth/login",
            headers={"X-CSRF-Token": "anonymous-challenge"},
            json={"email": "reader@example.com", "password": "password1"},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "服务器暂时无法处理请求，请稍后重试"}
    assert_no_store(response)
    assert response.headers["pragma"] == "no-cache"
    assert caplog.messages == ["User account request failed"]
    assert all(record.exc_info is None for record in caplog.records)
    logged = " ".join(caplog.messages)
    assert "reader@example.com" not in logged
    assert "password1" not in logged
    assert "anonymous-challenge" not in logged


def test_schema_bounds_are_explicit_and_rejected_before_the_service(
    client: TestClient, auth: FakeUserAuth
) -> None:
    response = client.post(
        "/api/v1/user-auth/register",
        headers={"X-CSRF-Token": "anonymous-challenge"},
        json={"email": "not-an-email", "username": "ab", "password": "short"},
    )

    assert response.status_code == 422
    assert not any(call[0] == "register" for call in auth.calls)
    assert_no_store(response)
