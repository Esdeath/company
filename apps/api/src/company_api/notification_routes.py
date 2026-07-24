"""HTTP routes for private site-user notifications and email unsubscribe."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from company_api.notification_service import (
    NotificationNotFound,
    NotificationOperations,
    UnsubscribeTokenInvalid,
)
from company_api.user_auth_routes import (
    OptionalUserSession,
    UserAuthServiceDependency,
    UserCsrfDependency,
    UserSessionDependency,
)
from company_api.user_schemas import (
    MessageResponse,
    NotificationPage,
    NotificationRead,
    UnsubscribeRequest,
)

router = APIRouter(tags=["site user notifications"])
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def get_notification_service(request: Request) -> NotificationOperations:
    return request.app.state.notification_service  # type: ignore[no-any-return]


NotificationServiceDependency = Annotated[NotificationOperations, Depends(get_notification_service)]


@router.get("/api/v1/users/me/notifications", response_model=NotificationPage)
async def list_notifications(
    response: Response,
    session: UserSessionDependency,
    service: NotificationServiceDependency,
) -> NotificationPage:
    response.headers.update(NO_STORE_HEADERS)
    return await service.list(session.user_id)


@router.patch("/api/v1/users/me/notifications/{notification_id}", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: UUID,
    response: Response,
    session: UserCsrfDependency,
    service: NotificationServiceDependency,
) -> NotificationRead:
    response.headers.update(NO_STORE_HEADERS)
    try:
        return await service.mark_read(notification_id, session.user_id)
    except NotificationNotFound as error:
        raise HTTPException(
            status_code=404,
            detail="通知不存在",
            headers=NO_STORE_HEADERS,
        ) from error


@router.post("/api/v1/users/me/notifications/read-all", status_code=204)
async def mark_all_notifications_read(
    response: Response,
    session: UserCsrfDependency,
    service: NotificationServiceDependency,
) -> Response:
    await service.mark_all_read(session.user_id)
    response.headers.update(NO_STORE_HEADERS)
    response.status_code = 204
    return response


@router.post("/api/v1/user-auth/unsubscribe", response_model=MessageResponse)
async def unsubscribe(
    data: UnsubscribeRequest,
    response: Response,
    service: NotificationServiceDependency,
    session: OptionalUserSession,
    auth: UserAuthServiceDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> MessageResponse:
    response.headers.update(NO_STORE_HEADERS)
    if session is not None and session.current_user is not None:
        if not auth.csrf_is_valid(session, csrf_token or ""):
            raise HTTPException(
                status_code=403,
                detail="CSRF 校验失败，请刷新页面后重试",
                headers=NO_STORE_HEADERS,
            )
        anonymous_challenge = None
    else:
        if not csrf_token:
            raise HTTPException(
                status_code=422,
                detail="请求校验已失效，请刷新页面后重试",
                headers=NO_STORE_HEADERS,
            )
        anonymous_challenge = csrf_token
    try:
        await service.unsubscribe(data.token, anonymous_challenge=anonymous_challenge)
    except UnsubscribeTokenInvalid as error:
        raise HTTPException(
            status_code=422,
            detail="链接无效或已过期",
            headers=NO_STORE_HEADERS,
        ) from error
    return MessageResponse(message="已停止接收评论回复邮件")
