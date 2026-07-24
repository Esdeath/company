"""Public HTTP routes for article comment reading and posting."""

from typing import Annotated, Never
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from company_api.comment_schemas import CommentCreate, CommentPage, CommentRead, CommentThreadRead
from company_api.comment_service import (
    CommentNotFound,
    CommentOperations,
    DocumentNotFound,
    ParentCommentInvalid,
)
from company_api.config import Settings
from company_api.user_auth_routes import OptionalUserSession, UserCsrfDependency

router = APIRouter(tags=["article comments"])


def get_comment_service(request: Request) -> CommentOperations:
    return request.app.state.comment_service  # type: ignore[no-any-return]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


CommentServiceDependency = Annotated[CommentOperations, Depends(get_comment_service)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def _raise_comment_error(error: Exception) -> Never:
    if isinstance(error, (DocumentNotFound, CommentNotFound)):
        status_code, detail = 404, "评论或资料不存在"
    elif isinstance(error, ParentCommentInvalid):
        status_code, detail = 422, "无法回复该评论"
    else:
        status_code, detail = 422, str(error) or "评论数据无效"
    raise HTTPException(status_code=status_code, detail=detail) from error


@router.get(
    "/api/v1/documents/{document_id}/comments",
    response_model=CommentPage,
)
async def list_comments(
    document_id: UUID,
    session: OptionalUserSession,
    service: CommentServiceDependency,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
) -> CommentPage:
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
    session: OptionalUserSession,
    service: CommentServiceDependency,
) -> CommentThreadRead:
    viewer_id = session.current_user.id if session is not None and session.current_user else None
    try:
        return await service.get_thread(comment_id, viewer_id)
    except CommentNotFound as error:
        _raise_comment_error(error)
