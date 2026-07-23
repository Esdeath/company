from pathlib import Path

from company_api.models import Base


def test_company_and_document_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "admin_sessions",
        "companies",
        "documents",
        "login_challenges",
    }
    columns = Base.metadata.tables["documents"].c
    assert set(columns.keys()) == {
        "id",
        "company_id",
        "title",
        "format",
        "source_path",
        "rendered_path",
        "original_filename",
        "uploaded_at",
        "sort_order",
    }

    assert set(Base.metadata.tables["admin_sessions"].c.keys()) == {
        "token_hash",
        "username",
        "credential_fingerprint",
        "csrf_token",
        "created_at",
        "expires_at",
    }


def test_document_sort_order_migration_preserves_current_display_order() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations/versions/20260723_03_document_sort_order.py"
    ).read_text()

    assert 'down_revision: str | Sequence[str] | None = "20260721_02"' in migration
    assert "PARTITION BY company_id" in migration
    assert "ORDER BY uploaded_at DESC, id DESC" in migration
    assert "row_number() OVER" in migration
