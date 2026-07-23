"""Add explicit per-company document order.

Revision ID: 20260723_03
Revises: 20260721_02
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_03"
down_revision: str | Sequence[str] | None = "20260721_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("sort_order", sa.BigInteger(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY company_id
                        ORDER BY uploaded_at DESC, id DESC
                    ) - 1 AS position
                FROM documents
            )
            UPDATE documents
            SET sort_order = ranked.position
            FROM ranked
            WHERE documents.id = ranked.id
            """
        )
    )
    op.alter_column("documents", "sort_order", nullable=False)
    op.create_check_constraint(
        "ck_documents_sort_order_nonnegative",
        "documents",
        "sort_order >= 0",
    )
    op.create_index(
        "ix_documents_company_sort_order",
        "documents",
        ["company_id", "sort_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_company_sort_order", table_name="documents")
    op.drop_constraint(
        "ck_documents_sort_order_nonnegative",
        "documents",
        type_="check",
    )
    op.drop_column("documents", "sort_order")
