"""Administrator login, session restoration, logout, and CSRF dependencies."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from company_api.auth import (
    AuthOperations,
    InvalidCredentials,
    InvalidLoginChallenge,
    SessionRecord,
)
from company_api.config import Settings
from company_api.schemas import AuthState, LoginRequest

router = APIRouter(prefix="/api/v1/auth", tags=["administrator authentication"])


def get_auth_service(request: Request) -> AuthOperations:
    return request.app.state.auth_service  # type: ignore[no-any-return]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


AuthServiceDependency = Annotated[AuthOperations, Depends(get_auth_service)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


async def require_admin_session(
    request: Request,
    service: AuthServiceDependency,
    settings: SettingsDependency,
) -> SessionRecord:
    session = await service.authenticate(request.cookies.get(settings.session_cookie_name, ""))
    if session is None:
        raise HTTPException(status_code=401, detail="管理员会话已失效，请重新登录")
    return session


AdminSessionDependency = Annotated[SessionRecord, Depends(require_admin_session)]


async def require_admin_csrf(
    session: AdminSessionDependency,
    service: AuthServiceDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> SessionRecord:
    if not service.csrf_is_valid(session, csrf_token or ""):
        raise HTTPException(status_code=403, detail="CSRF 校验失败，请刷新页面后重试")
    return session


AdminCsrfDependency = Annotated[SessionRecord, Depends(require_admin_csrf)]


def _disable_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.get("/session", response_model=AuthState)
async def read_session(
    request: Request,
    response: Response,
    service: AuthServiceDependency,
    settings: SettingsDependency,
) -> AuthState:
    _disable_cache(response)
    session = await service.authenticate(request.cookies.get(settings.session_cookie_name, ""))
    if session is not None:
        return AuthState(
            authenticated=True,
            username=session.username,
            csrf_token=session.csrf_token,
            expires_at=session.expires_at,
        )
    return AuthState(
        authenticated=False,
        csrf_token=await service.issue_login_challenge(),
    )


@router.post("/login", response_model=AuthState)
async def login(
    data: LoginRequest,
    response: Response,
    service: AuthServiceDependency,
    settings: SettingsDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthState:
    _disable_cache(response)
    try:
        session = await service.login(data.username, data.password, csrf_token or "")
    except InvalidLoginChallenge as error:
        raise HTTPException(status_code=403, detail="登录校验已失效，请重试") from error
    except InvalidCredentials as error:
        raise HTTPException(status_code=401, detail="用户名或密码错误") from error

    response.set_cookie(
        key=settings.session_cookie_name,
        value=session.session_token,
        max_age=settings.session_lifetime_seconds,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return AuthState(
        authenticated=True,
        username=session.username,
        csrf_token=session.csrf_token,
        expires_at=session.expires_at,
    )


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    session: AdminCsrfDependency,
    service: AuthServiceDependency,
    settings: SettingsDependency,
) -> Response:
    await service.logout(session)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    _disable_cache(response)
    response.status_code = 204
    return response
