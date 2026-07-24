"""Administrator-facing comment moderation request and response models."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from company_api.models import CommentStatus, ReportStatus, UserStatus


class ModerationCommentRead(BaseModel):
    id: UUID
    document_id: UUID
    document_title: str
    author_id: UUID | None
    author_username: str | None
    parent_id: UUID | None
    body: str | None
    status: CommentStatus
    created_at: datetime
    edited_at: datetime | None
    moderated_at: datetime | None
    deleted_at: datetime | None
    moderation_reason: str | None
    moderated_by: str | None


class ModerationCommentPage(BaseModel):
    items: list[ModerationCommentRead]
    next_cursor: str | None


class ModerationReportRead(BaseModel):
    id: UUID
    comment_id: UUID
    reporter_id: UUID
    reporter_username: str
    reason: str
    details: str | None
    status: ReportStatus
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None
    comment: ModerationCommentRead


class ModerationReportPage(BaseModel):
    items: list[ModerationReportRead]
    next_cursor: str | None


class ModerationUserRead(BaseModel):
    id: UUID
    email: str
    username: str
    status: UserStatus
    email_verified_at: datetime | None
    first_comment_approved_at: datetime | None
    created_at: datetime
    comment_count: int


class ModerationUserPage(BaseModel):
    items: list[ModerationUserRead]
    next_cursor: str | None


class CommentRejectionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ReportResolutionRequest(BaseModel):
    resolution: Literal[ReportStatus.KEPT, ReportStatus.REMOVED]
