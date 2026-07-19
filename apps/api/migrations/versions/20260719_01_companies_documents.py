"""Create companies and documents.

Revision ID: 20260719_01
Revises:
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260719_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

document_format = postgresql.ENUM(
    "HTML",
    "MARKDOWN",
    name="document_format",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("ticker", sa.String(length=50), nullable=True),
        sa.Column("market", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_companies_name", "companies", ["name"], unique=False)

    document_format.create(op.get_bind(), checkfirst=False)
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("format", document_format, nullable=False),
        sa.Column("source_path", sa.String(length=1000), nullable=False),
        sa.Column("rendered_path", sa.String(length=1000), nullable=True),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rendered_path"),
        sa.UniqueConstraint("source_path"),
    )
    op.create_index(
        "ix_documents_company_id",
        "documents",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_documents_uploaded_at",
        "documents",
        ["uploaded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_uploaded_at", table_name="documents")
    op.drop_index("ix_documents_company_id", table_name="documents")
    op.drop_table("documents")
    document_format.drop(op.get_bind(), checkfirst=False)
    op.drop_index("ix_companies_name", table_name="companies")
    op.drop_table("companies")
