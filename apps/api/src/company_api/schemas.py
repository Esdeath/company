"""Public request and response schemas for the document library."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, computed_field, field_validator

from company_api.models import DocumentFormat


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    ticker: str | None = Field(default=None, max_length=50)
    market: str | None = Field(default=None, max_length=50)


class CompanyRead(BaseModel):
    id: UUID
    name: str
    ticker: str | None
    market: str | None
    created_at: datetime


class ContentLinked(BaseModel):
    id: UUID

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_url(self) -> str:
        return f"/api/v1/documents/{self.id}/content"


class DocumentRead(ContentLinked):
    company_id: UUID
    title: str
    format: DocumentFormat
    original_filename: str
    sort_order: int
    uploaded_at: datetime


class DocumentRename(BaseModel):
    title: str = Field(min_length=1, max_length=500)


class DocumentOrder(BaseModel):
    document_ids: list[UUID]

    @field_validator("document_ids")
    @classmethod
    def unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("资料顺序不能包含重复项")
        return value


class UploadItem(ContentLinked):
    title: str
    format: DocumentFormat


class UploadError(BaseModel):
    filename: str
    message: str


class UploadBatchResponse(BaseModel):
    items: list[UploadItem]
    errors: list[UploadError]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1_000)


class AuthState(BaseModel):
    authenticated: bool
    username: str | None = None
    csrf_token: str
    expires_at: datetime | None = None
