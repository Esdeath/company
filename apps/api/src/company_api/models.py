import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class DocumentFormat(str, enum.Enum):  # noqa: UP042
    HTML = "html"
    MARKDOWN = "markdown"


class UserStatus(str, enum.Enum):  # noqa: UP042
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class UserTokenPurpose(str, enum.Enum):  # noqa: UP042
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
    UNSUBSCRIBE = "unsubscribe"


class CommentStatus(str, enum.Enum):  # noqa: UP042
    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"
    DELETED = "deleted"


class ReportStatus(str, enum.Enum):  # noqa: UP042
    OPEN = "open"
    KEPT = "kept"
    REMOVED = "removed"


class NotificationType(str, enum.Enum):  # noqa: UP042
    REPLY = "reply"
    COMMENT_APPROVED = "comment_approved"
    COMMENT_REJECTED = "comment_rejected"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    ticker: Mapped[str | None] = mapped_column(String(50))
    market: Mapped[str | None] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500))
    format: Mapped[DocumentFormat] = mapped_column(Enum(DocumentFormat, name="document_format"))
    source_path: Mapped[str] = mapped_column(String(1000), unique=True)
    rendered_path: Mapped[str | None] = mapped_column(String(1000), unique=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(BigInteger)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(100))
    credential_fingerprint: Mapped[str] = mapped_column(String(64))
    csrf_token: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LoginChallenge(Base):
    __tablename__ = "login_challenges"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_users"),
        UniqueConstraint("normalized_email", name="uq_users_normalized_email"),
        UniqueConstraint("normalized_username", name="uq_users_normalized_username"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320))
    normalized_email: Mapped[str] = mapped_column(String(320))
    username: Mapped[str] = mapped_column(String(30))
    normalized_username: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(500))
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"),
        default=UserStatus.PENDING_VERIFICATION,
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_comment_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reply_email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    username_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (PrimaryKeyConstraint("token_hash", name="pk_user_sessions"),)

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_user_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        index=True,
    )
    csrf_token: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class UserAuthChallenge(Base):
    __tablename__ = "user_auth_challenges"
    __table_args__ = (PrimaryKeyConstraint("token_hash", name="pk_user_auth_challenges"),)

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class UserToken(Base):
    __tablename__ = "user_tokens"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_user_tokens"),
        UniqueConstraint("token_hash", name="uq_user_tokens_token_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[UserTokenPurpose] = mapped_column(
        Enum(UserTokenPurpose, name="user_token_purpose")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_user_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_comments"),
        CheckConstraint(
            "status = 'DELETED' OR (body IS NOT NULL AND char_length(body) BETWEEN 1 AND 2000)",
            name="ck_comments_body_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "documents.id",
            name="fk_comments_document_id_documents",
            ondelete="CASCADE",
        ),
        index=True,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_comments_author_id_users",
            ondelete="SET NULL",
        ),
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "comments.id",
            name="fk_comments_parent_id_comments",
            ondelete="SET NULL",
        ),
        index=True,
    )
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "comments.id",
            name="fk_comments_reply_to_id_comments",
            ondelete="SET NULL",
        ),
        index=True,
    )
    body: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[CommentStatus] = mapped_column(
        Enum(CommentStatus, name="comment_status"),
        default=CommentStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moderation_reason: Mapped[str | None] = mapped_column(String(500))
    moderated_by: Mapped[str | None] = mapped_column(String(100))


class CommentReport(Base):
    __tablename__ = "comment_reports"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_comment_reports"),
        UniqueConstraint("comment_id", "reporter_id", name="uq_comment_reports_comment_reporter"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    comment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "comments.id",
            name="fk_comment_reports_comment_id_comments",
            ondelete="CASCADE",
        ),
        index=True,
    )
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_comment_reports_reporter_id_users",
            ondelete="CASCADE",
        ),
        index=True,
    )
    reason: Mapped[str] = mapped_column(String(100))
    details: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status"),
        default=ReportStatus.OPEN,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(100))


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (PrimaryKeyConstraint("id", name="pk_notifications"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_notifications_recipient_id_users",
            ondelete="CASCADE",
        ),
        index=True,
    )
    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notification_type"),
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_notifications_actor_id_users",
            ondelete="SET NULL",
        ),
        index=True,
    )
    comment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "comments.id",
            name="fk_notifications_comment_id_comments",
            ondelete="CASCADE",
        ),
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "documents.id",
            name="fk_notifications_document_id_documents",
            ondelete="CASCADE",
        ),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    __table_args__ = (PrimaryKeyConstraint("id", name="pk_email_outbox"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "user_tokens.id",
            name="fk_email_outbox_token_id_user_tokens",
            ondelete="CASCADE",
        ),
        index=True,
    )
    template: Mapped[str] = mapped_column(String(100))
    recipient: Mapped[str | None] = mapped_column(String(320))
    payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )
    lease_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(String(100))


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    __table_args__ = (
        PrimaryKeyConstraint(
            "action",
            "subject_hash",
            "window_started_at",
            name="pk_rate_limit_buckets",
        ),
    )

    action: Mapped[str] = mapped_column(String(100))
    subject_hash: Mapped[str] = mapped_column(String(64))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
