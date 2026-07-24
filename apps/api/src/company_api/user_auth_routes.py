"""Ordinary-user authentication, account routes, and CSRF dependencies."""

from datetime import datetime
from typing import Annotated, Never

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from company_api.config import Settings
from company_api.user_auth import (
    AccountSuspended,
    ChallengeInvalid,
    CredentialsInvalid,
    NewUserSession,
    RateLimitExceeded,
    RegistrationClosed,
    TokenInvalid,
    UserAuthOperations,
    UsernameChangeTooSoon,
    UsernameUnavailable,
    UserSessionRecord,
)
from company_api.user_schemas import (
    AccountDeleteRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordUpdateRequest,
    PreferencesUpdateRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    UserAuthState,
    UserLoginRequest,
    UserResponse,
    VerifyEmailRequest,
)

router = APIRouter(tags=["site user authentication"])

NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
DOMAIN_ERRORS = (
    AccountSuspended,
    ChallengeInvalid,
    CredentialsInvalid,
    RateLimitExceeded,
    RegistrationClosed,
    TokenInvalid,
    UsernameChangeTooSoon,
    UsernameUnavailable,
    ValueError,
)


def get_user_auth_service(request: Request) -> UserAuthOperations:
    return request.app.state.user_auth_service  # type: ignore[no-any-return]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


UserAuthServiceDependency = Annotated[UserAuthOperations, Depends(get_user_auth_service)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


async def optional_user_session(
    request: Request,
    service: UserAuthServiceDependency,
    settings: SettingsDependency,
) -> UserSessionRecord | None:
    return await service.authenticate(request.cookies.get(settings.user_session_cookie_name, ""))


OptionalUserSession = Annotated[UserSessionRecord | None, Depends(optional_user_session)]


async def require_user_session(session: OptionalUserSession) -> UserSessionRecord:
    if session is None or session.current_user is None:
        raise HTTPException(
            status_code=401,
            detail="用户会话已失效，请重新登录",
            headers=NO_STORE_HEADERS,
        )
    return session


UserSessionDependency = Annotated[UserSessionRecord, Depends(require_user_session)]


async def require_user_csrf(
    session: UserSessionDependency,
    service: UserAuthServiceDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> UserSessionRecord:
    if not service.csrf_is_valid(session, csrf_token or ""):
        raise HTTPException(
            status_code=403,
            detail="CSRF 校验失败，请刷新页面后重试",
            headers=NO_STORE_HEADERS,
        )
    return session


UserCsrfDependency = Annotated[UserSessionRecord, Depends(require_user_csrf)]


def _disable_cache(response: Response) -> None:
    response.headers.update(NO_STORE_HEADERS)


def _set_session_cookie(response: Response, settings: Settings, session_token: str) -> None:
    response.set_cookie(
        key=settings.user_session_cookie_name,
        value=session_token,
        max_age=settings.user_session_lifetime_seconds,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _delete_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.user_session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _authenticated_state(
    user: UserResponse,
    csrf_token: str,
    expires_at: datetime,
    settings: Settings,
) -> UserAuthState:
    return UserAuthState(
        authenticated=True,
        user=user,
        csrf_token=csrf_token,
        expires_at=expires_at,
        registration_enabled=settings.user_registration_enabled,
    )


def _raise_domain_error(error: Exception) -> Never:
    if isinstance(error, ChallengeInvalid):
        status_code, detail = 403, "请求校验已失效，请刷新页面后重试"
    elif isinstance(error, CredentialsInvalid):
        status_code, detail = 401, "邮箱或密码错误"
    elif isinstance(error, RegistrationClosed):
        status_code, detail = 503, "注册暂未开放"
    elif isinstance(error, UsernameUnavailable):
        status_code, detail = 409, "用户名已被使用"
    elif isinstance(error, TokenInvalid):
        status_code, detail = 422, "链接无效或已过期"
    elif isinstance(error, AccountSuspended):
        status_code, detail = 403, "账号已停用"
    elif isinstance(error, UsernameChangeTooSoon):
        status_code, detail = 409, "用户名每 30 天只能修改一次"
    elif isinstance(error, RateLimitExceeded):
        status_code, detail = 429, "操作过于频繁，请稍后重试"
    else:
        status_code, detail = 422, "提交的数据无效"
    raise HTTPException(status_code=status_code, detail=detail, headers=NO_STORE_HEADERS) from error


def _raise_current_password_error(error: CredentialsInvalid) -> Never:
    raise HTTPException(
        status_code=422,
        detail="当前密码错误",
        headers=NO_STORE_HEADERS,
    ) from error


@router.get("/api/v1/user-auth/session", response_model=UserAuthState)
async def read_session(
    response: Response,
    session: OptionalUserSession,
    service: UserAuthServiceDependency,
    settings: SettingsDependency,
) -> UserAuthState:
    _disable_cache(response)
    if session is None or session.current_user is None:
        return UserAuthState(
            authenticated=False,
            csrf_token=await service.issue_challenge(),
            registration_enabled=settings.user_registration_enabled,
        )
    return _authenticated_state(
        UserResponse.from_current_user(session.current_user),
        session.csrf_token,
        session.expires_at,
        settings,
    )


@router.post("/api/v1/user-auth/register", response_model=MessageResponse, status_code=202)
async def register(
    data: RegisterRequest,
    response: Response,
    service: UserAuthServiceDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> MessageResponse:
    _disable_cache(response)
    try:
        await service.register(data.email, data.username, data.password, csrf_token or "")
    except DOMAIN_ERRORS as error:
        _raise_domain_error(error)
    return MessageResponse(message="请检查邮箱以完成注册")


def _create_session_response(
    response: Response,
    settings: Settings,
    session: NewUserSession,
) -> UserAuthState:
    _set_session_cookie(response, settings, session.session_token)
    return _authenticated_state(
        UserResponse.from_current_user(session.current_user),
        session.csrf_token,
        session.expires_at,
        settings,
    )


@router.post("/api/v1/user-auth/verify-email", response_model=UserAuthState)
async def verify_email(
    data: VerifyEmailRequest,
    response: Response,
    service: UserAuthServiceDependency,
    settings: SettingsDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> UserAuthState:
    _disable_cache(response)
    try:
        session = await service.verify_email(data.token, csrf_token or "")
    except DOMAIN_ERRORS as error:
        _raise_domain_error(error)
    return _create_session_response(response, settings, session)


@router.post("/api/v1/user-auth/login", response_model=UserAuthState)
async def login(
    data: UserLoginRequest,
    response: Response,
    service: UserAuthServiceDependency,
    settings: SettingsDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> UserAuthState:
    _disable_cache(response)
    try:
        session = await service.login(data.email, data.password, csrf_token or "")
    except DOMAIN_ERRORS as error:
        _raise_domain_error(error)
    return _create_session_response(response, settings, session)


@router.post("/api/v1/user-auth/logout", status_code=204)
async def logout(
    response: Response,
    session: UserCsrfDependency,
    service: UserAuthServiceDependency,
    settings: SettingsDependency,
) -> Response:
    await service.logout(session)
    _delete_session_cookie(response, settings)
    _disable_cache(response)
    response.status_code = 204
    return response


@router.post(
    "/api/v1/user-auth/password-reset/request",
    response_model=MessageResponse,
    status_code=202,
)
async def request_password_reset(
    data: PasswordResetRequest,
    response: Response,
    service: UserAuthServiceDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> MessageResponse:
    _disable_cache(response)
    try:
        await service.request_password_reset(data.email, csrf_token or "")
    except DOMAIN_ERRORS as error:
        _raise_domain_error(error)
    return MessageResponse(message="如果该邮箱已注册，我们已发送密码重置邮件")


@router.post("/api/v1/user-auth/password-reset/confirm", response_model=UserAuthState)
async def confirm_password_reset(
    data: PasswordResetConfirmRequest,
    response: Response,
    service: UserAuthServiceDependency,
    settings: SettingsDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> UserAuthState:
    _disable_cache(response)
    try:
        session = await service.reset_password(data.token, data.password, csrf_token or "")
    except DOMAIN_ERRORS as error:
        _raise_domain_error(error)
    return _create_session_response(response, settings, session)


@router.get("/api/v1/users/me", response_model=UserResponse)
async def read_current_user(response: Response, session: UserSessionDependency) -> UserResponse:
    _disable_cache(response)
    assert session.current_user is not None
    return UserResponse.from_current_user(session.current_user)


@router.patch("/api/v1/users/me/profile", response_model=UserResponse)
async def update_profile(
    data: ProfileUpdateRequest,
    response: Response,
    session: UserCsrfDependency,
    service: UserAuthServiceDependency,
) -> UserResponse:
    _disable_cache(response)
    try:
        user = await service.update_username(session, data.username)
    except DOMAIN_ERRORS as error:
        _raise_domain_error(error)
    return UserResponse.from_current_user(user)


@router.patch("/api/v1/users/me/password", response_model=UserAuthState)
async def update_password(
    data: PasswordUpdateRequest,
    response: Response,
    session: UserCsrfDependency,
    service: UserAuthServiceDependency,
    settings: SettingsDependency,
) -> UserAuthState:
    _disable_cache(response)
    try:
        updated = await service.update_password(session, data.current_password, data.password)
    except CredentialsInvalid as error:
        _raise_current_password_error(error)
    except DOMAIN_ERRORS as error:
        _raise_domain_error(error)
    _set_session_cookie(response, settings, updated.session_token)
    return _authenticated_state(
        UserResponse.from_current_user(updated.current_user),
        updated.csrf_token,
        updated.expires_at,
        settings,
    )


@router.patch("/api/v1/users/me/preferences", response_model=UserResponse)
async def update_preferences(
    data: PreferencesUpdateRequest,
    response: Response,
    session: UserCsrfDependency,
    service: UserAuthServiceDependency,
) -> UserResponse:
    _disable_cache(response)
    try:
        user = await service.update_preferences(
            session, reply_email_enabled=data.reply_email_enabled
        )
    except DOMAIN_ERRORS as error:
        _raise_domain_error(error)
    return UserResponse.from_current_user(user)


@router.delete("/api/v1/users/me", status_code=204)
async def delete_account(
    data: AccountDeleteRequest,
    response: Response,
    session: UserCsrfDependency,
    service: UserAuthServiceDependency,
    settings: SettingsDependency,
) -> Response:
    _disable_cache(response)
    try:
        await service.delete_account(session, data.password)
    except CredentialsInvalid as error:
        _raise_current_password_error(error)
    except DOMAIN_ERRORS as error:
        _raise_domain_error(error)
    _delete_session_cookie(response, settings)
    response.status_code = 204
    return response
