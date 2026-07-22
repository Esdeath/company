"""Public request and response schemas for the document library."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, computed_field

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
    uploaded_at: datetime


class DocumentRename(BaseModel):
    title: str = Field(min_length=1, max_length=500)


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
