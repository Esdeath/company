"""Add explicit company order.

Revision ID: 20260728_05
Revises: 20260724_04
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_05"
down_revision: str | Sequence[str] | None = "20260724_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("sort_order", sa.BigInteger(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    row_number() OVER (
                        ORDER BY lower(trim(name)), id
                    ) - 1 AS position
                FROM companies
            )
            UPDATE companies
            SET sort_order = ranked.position
            FROM ranked
            WHERE companies.id = ranked.id
            """
        )
    )
    op.alter_column("companies", "sort_order", nullable=False)
    op.create_check_constraint(
        "ck_companies_sort_order_nonnegative",
        "companies",
        "sort_order >= 0",
    )
    op.create_index(
        "ix_companies_sort_order",
        "companies",
        ["sort_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_companies_sort_order", table_name="companies")
    op.drop_constraint(
        "ck_companies_sort_order_nonnegative",
        "companies",
        type_="check",
    )
    op.drop_column("companies", "sort_order")
