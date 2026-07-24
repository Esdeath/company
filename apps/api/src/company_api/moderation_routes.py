"""Administrator routes for comment moderation and site-user administration."""

from typing import Annotated, Never
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from company_api.auth_routes import AdminCsrfDependency, AdminSessionDependency
from company_api.models import CommentStatus, ReportStatus
from company_api.moderation_schemas import (
    CommentRejectionRequest,
    ModerationCommentPage,
    ModerationCommentRead,
    ModerationReportPage,
    ModerationReportRead,
    ModerationUserPage,
    ModerationUserRead,
    ReportResolutionRequest,
)
from company_api.moderation_service import (
    ModerationConflict,
    ModerationNotFound,
    ModerationOperations,
)

router = APIRouter(prefix="/api/v1/admin", tags=["comment moderation"])
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def get_moderation_service(request: Request) -> ModerationOperations:
    return request.app.state.moderation_service  # type: ignore[no-any-return]


ModerationServiceDependency = Annotated[ModerationOperations, Depends(get_moderation_service)]


def _raise_moderation_error(error: Exception) -> Never:
    if isinstance(error, ModerationNotFound):
        status_code, detail = 404, "审核对象不存在"
    elif isinstance(error, ModerationConflict):
        status_code, detail = 409, "内容状态已被其他操作修改"
    else:
        status_code, detail = 422, str(error) or "提交的数据无效"
    raise HTTPException(status_code=status_code, detail=detail) from error


@router.get("/comments", response_model=ModerationCommentPage)
async def list_comments(
    response: Response,
    session: AdminSessionDependency,
    service: ModerationServiceDependency,
    status: CommentStatus | None = None,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
) -> ModerationCommentPage:
    del session
    response.headers.update(NO_STORE_HEADERS)
    try:
        return await service.list_comments(status, cursor)
    except ValueError as error:
        _raise_moderation_error(error)


@router.post("/comments/{comment_id}/approve", response_model=ModerationCommentRead)
async def approve_comment(
    comment_id: UUID,
    session: AdminCsrfDependency,
    service: ModerationServiceDependency,
) -> ModerationCommentRead:
    try:
        return await service.approve(comment_id, session.username)
    except (ModerationNotFound, ModerationConflict) as error:
        _raise_moderation_error(error)


@router.post("/comments/{comment_id}/reject", response_model=ModerationCommentRead)
async def reject_comment(
    comment_id: UUID,
    data: CommentRejectionRequest,
    session: AdminCsrfDependency,
    service: ModerationServiceDependency,
) -> ModerationCommentRead:
    try:
        return await service.reject(comment_id, session.username, data.reason)
    except (ModerationNotFound, ModerationConflict, ValueError) as error:
        _raise_moderation_error(error)


@router.post("/comments/{comment_id}/remove", response_model=ModerationCommentRead)
async def remove_comment(
    comment_id: UUID,
    session: AdminCsrfDependency,
    service: ModerationServiceDependency,
) -> ModerationCommentRead:
    try:
        return await service.remove(comment_id, session.username)
    except (ModerationNotFound, ModerationConflict) as error:
        _raise_moderation_error(error)


@router.get("/comment-reports", response_model=ModerationReportPage)
async def list_reports(
    response: Response,
    session: AdminSessionDependency,
    service: ModerationServiceDependency,
    status: ReportStatus | None = None,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
) -> ModerationReportPage:
    del session
    response.headers.update(NO_STORE_HEADERS)
    try:
        return await service.list_reports(status, cursor)
    except ValueError as error:
        _raise_moderation_error(error)


@router.post("/comment-reports/{report_id}/resolve", response_model=ModerationReportRead)
async def resolve_report(
    report_id: UUID,
    data: ReportResolutionRequest,
    session: AdminCsrfDependency,
    service: ModerationServiceDependency,
) -> ModerationReportRead:
    try:
        return await service.resolve_report(report_id, session.username, data.resolution)
    except (ModerationNotFound, ModerationConflict, ValueError) as error:
        _raise_moderation_error(error)


@router.get("/users", response_model=ModerationUserPage)
async def list_users(
    response: Response,
    session: AdminSessionDependency,
    service: ModerationServiceDependency,
    query: Annotated[str, Query(alias="q", min_length=1, max_length=100)],
    cursor: Annotated[str | None, Query(max_length=500)] = None,
) -> ModerationUserPage:
    del session
    response.headers.update(NO_STORE_HEADERS)
    try:
        return await service.list_users(query, cursor)
    except ValueError as error:
        _raise_moderation_error(error)


@router.post("/users/{user_id}/suspend", response_model=ModerationUserRead)
async def suspend_user(
    user_id: UUID,
    session: AdminCsrfDependency,
    service: ModerationServiceDependency,
) -> ModerationUserRead:
    del session
    try:
        return await service.suspend_user(user_id)
    except ModerationNotFound as error:
        _raise_moderation_error(error)


@router.post("/users/{user_id}/restore", response_model=ModerationUserRead)
async def restore_user(
    user_id: UUID,
    session: AdminCsrfDependency,
    service: ModerationServiceDependency,
) -> ModerationUserRead:
    del session
    try:
        return await service.restore_user(user_id)
    except (ModerationNotFound, ModerationConflict) as error:
        _raise_moderation_error(error)
