"""Create community account, comment, and delivery tables.

Revision ID: 20260724_04
Revises: 20260723_03
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260724_04"
down_revision: str | Sequence[str] | None = "20260723_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_status = postgresql.ENUM(
    "PENDING_VERIFICATION",
    "ACTIVE",
    "SUSPENDED",
    name="user_status",
    create_type=False,
)
user_token_purpose = postgresql.ENUM(
    "VERIFY_EMAIL",
    "RESET_PASSWORD",
    "UNSUBSCRIBE",
    name="user_token_purpose",
    create_type=False,
)
comment_status = postgresql.ENUM(
    "PENDING",
    "PUBLISHED",
    "REJECTED",
    "DELETED",
    name="comment_status",
    create_type=False,
)
report_status = postgresql.ENUM(
    "OPEN",
    "KEPT",
    "REMOVED",
    name="report_status",
    create_type=False,
)
notification_type = postgresql.ENUM(
    "REPLY",
    "COMMENT_APPROVED",
    "COMMENT_REJECTED",
    name="notification_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    user_status.create(bind, checkfirst=False)
    user_token_purpose.create(bind, checkfirst=False)
    comment_status.create(bind, checkfirst=False)
    report_status.create(bind, checkfirst=False)
    notification_type.create(bind, checkfirst=False)

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column("username", sa.String(length=30), nullable=False),
        sa.Column("normalized_username", sa.String(length=30), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.Column("status", user_status, nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_comment_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_email_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("username_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("normalized_email", name="uq_users_normalized_email"),
        sa.UniqueConstraint("normalized_username", name="uq_users_normalized_username"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("csrf_token", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash", name="pk_user_sessions"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"], unique=False)
    op.create_table(
        "user_auth_challenges",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash", name="pk_user_auth_challenges"),
    )
    op.create_index(
        "ix_user_auth_challenges_expires_at",
        "user_auth_challenges",
        ["expires_at"],
        unique=False,
    )
    op.create_table(
        "user_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", user_token_purpose, nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_user_tokens_token_hash"),
    )
    op.create_index("ix_user_tokens_user_id", "user_tokens", ["user_id"], unique=False)
    op.create_index("ix_user_tokens_expires_at", "user_tokens", ["expires_at"], unique=False)
    op.create_table(
        "comments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("reply_to_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.String(length=2000), nullable=True),
        sa.Column("status", comment_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderation_reason", sa.String(length=500), nullable=True),
        sa.Column("moderated_by", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            "status = 'DELETED' OR (body IS NOT NULL AND char_length(body) BETWEEN 1 AND 2000)",
            name="ck_comments_body_length",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name="fk_comments_author_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_comments_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["comments.id"],
            name="fk_comments_parent_id_comments",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_id"],
            ["comments.id"],
            name="fk_comments_reply_to_id_comments",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_comments"),
    )
    op.create_index("ix_comments_document_id", "comments", ["document_id"], unique=False)
    op.create_index("ix_comments_author_id", "comments", ["author_id"], unique=False)
    op.create_index("ix_comments_parent_id", "comments", ["parent_id"], unique=False)
    op.create_index("ix_comments_reply_to_id", "comments", ["reply_to_id"], unique=False)
    op.create_index("ix_comments_status", "comments", ["status"], unique=False)
    op.create_index("ix_comments_created_at", "comments", ["created_at"], unique=False)
    op.create_table(
        "comment_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("comment_id", sa.UUID(), nullable=False),
        sa.Column("reporter_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("details", sa.String(length=2000), nullable=True),
        sa.Column("status", report_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["comment_id"],
            ["comments.id"],
            name="fk_comment_reports_comment_id_comments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["users.id"],
            name="fk_comment_reports_reporter_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_comment_reports"),
        sa.UniqueConstraint(
            "comment_id", "reporter_id", name="uq_comment_reports_comment_reporter"
        ),
    )
    op.create_index(
        "ix_comment_reports_comment_id", "comment_reports", ["comment_id"], unique=False
    )
    op.create_index(
        "ix_comment_reports_reporter_id", "comment_reports", ["reporter_id"], unique=False
    )
    op.create_index("ix_comment_reports_status", "comment_reports", ["status"], unique=False)
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("recipient_id", sa.UUID(), nullable=False),
        sa.Column("type", notification_type, nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("comment_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_notifications_actor_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["comment_id"],
            ["comments.id"],
            name="fk_notifications_comment_id_comments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_notifications_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            name="fk_notifications_recipient_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
    )
    op.create_index(
        "ix_notifications_recipient_id", "notifications", ["recipient_id"], unique=False
    )
    op.create_index("ix_notifications_type", "notifications", ["type"], unique=False)
    op.create_index("ix_notifications_actor_id", "notifications", ["actor_id"], unique=False)
    op.create_index("ix_notifications_comment_id", "notifications", ["comment_id"], unique=False)
    op.create_index("ix_notifications_document_id", "notifications", ["document_id"], unique=False)
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"], unique=False)
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("token_id", sa.UUID(), nullable=True),
        sa.Column("template", sa.String(length=100), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_id", sa.UUID(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["token_id"],
            ["user_tokens.id"],
            name="fk_email_outbox_token_id_user_tokens",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_email_outbox"),
    )
    op.create_index("ix_email_outbox_token_id", "email_outbox", ["token_id"], unique=False)
    op.create_index("ix_email_outbox_available_at", "email_outbox", ["available_at"], unique=False)
    op.create_index("ix_email_outbox_lease_id", "email_outbox", ["lease_id"], unique=False)
    op.create_index(
        "ix_email_outbox_lease_expires_at",
        "email_outbox",
        ["lease_expires_at"],
        unique=False,
    )
    op.create_index("ix_email_outbox_sent_at", "email_outbox", ["sent_at"], unique=False)
    op.create_table(
        "rate_limit_buckets",
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "action",
            "subject_hash",
            "window_started_at",
            name="pk_rate_limit_buckets",
        ),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_buckets")
    op.drop_index("ix_email_outbox_sent_at", table_name="email_outbox")
    op.drop_index("ix_email_outbox_lease_expires_at", table_name="email_outbox")
    op.drop_index("ix_email_outbox_lease_id", table_name="email_outbox")
    op.drop_index("ix_email_outbox_available_at", table_name="email_outbox")
    op.drop_index("ix_email_outbox_token_id", table_name="email_outbox")
    op.drop_table("email_outbox")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_document_id", table_name="notifications")
    op.drop_index("ix_notifications_comment_id", table_name="notifications")
    op.drop_index("ix_notifications_actor_id", table_name="notifications")
    op.drop_index("ix_notifications_type", table_name="notifications")
    op.drop_index("ix_notifications_recipient_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_comment_reports_status", table_name="comment_reports")
    op.drop_index("ix_comment_reports_reporter_id", table_name="comment_reports")
    op.drop_index("ix_comment_reports_comment_id", table_name="comment_reports")
    op.drop_table("comment_reports")
    op.drop_index("ix_comments_created_at", table_name="comments")
    op.drop_index("ix_comments_status", table_name="comments")
    op.drop_index("ix_comments_reply_to_id", table_name="comments")
    op.drop_index("ix_comments_parent_id", table_name="comments")
    op.drop_index("ix_comments_author_id", table_name="comments")
    op.drop_index("ix_comments_document_id", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_user_tokens_expires_at", table_name="user_tokens")
    op.drop_index("ix_user_tokens_user_id", table_name="user_tokens")
    op.drop_table("user_tokens")
    op.drop_index("ix_user_auth_challenges_expires_at", table_name="user_auth_challenges")
    op.drop_table("user_auth_challenges")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")

    notification_type.drop(op.get_bind(), checkfirst=False)
    report_status.drop(op.get_bind(), checkfirst=False)
    comment_status.drop(op.get_bind(), checkfirst=False)
    user_token_purpose.drop(op.get_bind(), checkfirst=False)
    user_status.drop(op.get_bind(), checkfirst=False)
