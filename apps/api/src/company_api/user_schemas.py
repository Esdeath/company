"""HTTP request and response schemas for ordinary site accounts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from company_api.models import NotificationType
from company_api.user_auth import CurrentUser


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    username: str = Field(min_length=3, max_length=30)
    email_verified_at: datetime | None
    first_comment_approved_at: datetime | None
    reply_email_enabled: bool

    @classmethod
    def from_current_user(cls, user: CurrentUser) -> "UserResponse":
        return cls.model_validate(user)


class UserAuthState(BaseModel):
    authenticated: bool
    user: UserResponse | None = None
    csrf_token: str | None = None
    expires_at: datetime | None = None
    registration_enabled: bool


class MessageResponse(BaseModel):
    message: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    email: EmailStr = Field(max_length=320)
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=8, max_length=200)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=1_000)


class UserLoginRequest(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=8, max_length=200)


class PasswordResetRequest(BaseModel):
    email: EmailStr = Field(max_length=320)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=1, max_length=1_000)
    password: str = Field(min_length=8, max_length=200)


class ProfileUpdateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)


class PasswordUpdateRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class PreferencesUpdateRequest(BaseModel):
    reply_email_enabled: bool


class NotificationRead(BaseModel):
    id: UUID
    type: NotificationType
    company_id: UUID
    document_id: UUID
    comment_id: UUID
    actor_username: str | None
    excerpt: str
    message: str
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    unread_count: int = Field(ge=0)


class UnsubscribeRequest(BaseModel):
    token: str = Field(min_length=1, max_length=1_000)


class AccountDeleteRequest(BaseModel):
    password: str = Field(min_length=8, max_length=200)
