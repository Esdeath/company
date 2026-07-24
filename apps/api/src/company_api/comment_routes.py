"""Public HTTP routes for article comment reading and posting."""

from typing import Annotated, Never
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from company_api.comment_schemas import CommentCreate, CommentPage, CommentRead, CommentThreadRead
from company_api.comment_service import (
    CommentNotFound,
    CommentOperations,
    CommentReportNotAllowed,
    DocumentNotFound,
    DuplicateCommentReport,
    ParentCommentInvalid,
)
from company_api.config import Settings
from company_api.user_auth_routes import OptionalUserSession, UserCsrfDependency

router = APIRouter(tags=["article comments"])
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def get_comment_service(request: Request) -> CommentOperations:
    return request.app.state.comment_service  # type: ignore[no-any-return]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


CommentServiceDependency = Annotated[CommentOperations, Depends(get_comment_service)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


class CommentUpdateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2_000)


class CommentReportRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=100)
    details: str | None = Field(default=None, max_length=2_000)


def _raise_comment_error(error: Exception) -> Never:
    if isinstance(error, (DocumentNotFound, CommentNotFound)):
        status_code, detail = 404, "评论或资料不存在"
    elif isinstance(error, ParentCommentInvalid):
        status_code, detail = 422, "无法回复该评论"
    else:
        status_code, detail = 422, str(error) or "评论数据无效"
    raise HTTPException(status_code=status_code, detail=detail, headers=NO_STORE_HEADERS) from error


@router.get(
    "/api/v1/documents/{document_id}/comments",
    response_model=CommentPage,
)
async def list_comments(
    document_id: UUID,
    response: Response,
    session: OptionalUserSession,
    service: CommentServiceDependency,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
) -> CommentPage:
    response.headers.update(NO_STORE_HEADERS)
    viewer_id = session.current_user.id if session is not None and session.current_user else None
    try:
        return await service.list_comments(document_id, viewer_id, cursor)
    except (DocumentNotFound, ValueError) as error:
        _raise_comment_error(error)


@router.post(
    "/api/v1/documents/{document_id}/comments",
    response_model=CommentRead,
    status_code=201,
)
async def create_comment(
    document_id: UUID,
    data: CommentCreate,
    session: UserCsrfDependency,
    service: CommentServiceDependency,
    settings: SettingsDependency,
) -> CommentRead:
    if not settings.comment_writes_enabled:
        raise HTTPException(status_code=503, detail="评论区暂时只读")
    actor = session.current_user
    if actor is None:
        raise HTTPException(status_code=401, detail="用户会话已失效，请重新登录")
    try:
        return await service.create_comment(document_id, actor, data.body, data.parent_id)
    except (DocumentNotFound, ParentCommentInvalid, ValueError) as error:
        _raise_comment_error(error)


@router.get(
    "/api/v1/comments/{comment_id}/thread",
    response_model=CommentThreadRead,
)
async def get_thread(
    comment_id: UUID,
    response: Response,
    session: OptionalUserSession,
    service: CommentServiceDependency,
) -> CommentThreadRead:
    response.headers.update(NO_STORE_HEADERS)
    viewer_id = session.current_user.id if session is not None and session.current_user else None
    try:
        return await service.get_thread(comment_id, viewer_id)
    except CommentNotFound as error:
        _raise_comment_error(error)


def _require_comment_writes(settings: Settings) -> None:
    if not settings.comment_writes_enabled:
        raise HTTPException(status_code=503, detail="评论区暂时只读")


@router.patch("/api/v1/comments/{comment_id}", response_model=CommentRead)
async def update_comment(
    comment_id: UUID,
    data: CommentUpdateRequest,
    session: UserCsrfDependency,
    service: CommentServiceDependency,
    settings: SettingsDependency,
) -> CommentRead:
    _require_comment_writes(settings)
    actor = session.current_user
    if actor is None:
        raise HTTPException(status_code=401, detail="用户会话已失效，请重新登录")
    try:
        return await service.update_comment(comment_id, actor, data.body)
    except (CommentNotFound, ValueError) as error:
        _raise_comment_error(error)


@router.delete("/api/v1/comments/{comment_id}", response_model=CommentRead)
async def delete_comment(
    comment_id: UUID,
    session: UserCsrfDependency,
    service: CommentServiceDependency,
    settings: SettingsDependency,
) -> CommentRead:
    _require_comment_writes(settings)
    actor = session.current_user
    if actor is None:
        raise HTTPException(status_code=401, detail="用户会话已失效，请重新登录")
    try:
        return await service.delete_comment(comment_id, actor)
    except CommentNotFound as error:
        _raise_comment_error(error)


@router.post("/api/v1/comments/{comment_id}/reports", status_code=201)
async def report_comment(
    comment_id: UUID,
    data: CommentReportRequest,
    session: UserCsrfDependency,
    service: CommentServiceDependency,
    settings: SettingsDependency,
) -> None:
    _require_comment_writes(settings)
    actor = session.current_user
    if actor is None:
        raise HTTPException(status_code=401, detail="用户会话已失效，请重新登录")
    try:
        await service.report_comment(comment_id, actor, data.reason, data.details)
    except DuplicateCommentReport as error:
        raise HTTPException(status_code=409, detail="你已经举报过这条评论") from error
    except CommentReportNotAllowed as error:
        raise HTTPException(status_code=422, detail="无法举报该评论") from error
    except ValueError as error:
        _raise_comment_error(error)
