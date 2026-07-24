"""Public request and response models for article comments."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from company_api.models import CommentStatus


class CommentAuthorRead(BaseModel):
    id: UUID | None
    username: str


class CommentRead(BaseModel):
    id: UUID
    document_id: UUID
    parent_id: UUID | None
    body: str | None
    status: CommentStatus
    author: CommentAuthorRead
    created_at: datetime
    edited_at: datetime | None
    replies: list["CommentRead"] = Field(default_factory=list)
    can_edit: bool
    can_delete: bool
    can_report: bool


class CommentPage(BaseModel):
    items: list[CommentRead]
    viewer_pending: list[CommentRead]
    next_cursor: str | None
    total_count: int


class CommentThreadRead(BaseModel):
    root: CommentRead
    target_comment_id: UUID
    viewer_pending: list[CommentRead] = Field(default_factory=list)


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2_000)
    parent_id: UUID | None = None
