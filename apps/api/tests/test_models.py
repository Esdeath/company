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
    }

    assert set(Base.metadata.tables["admin_sessions"].c.keys()) == {
        "token_hash",
        "username",
        "credential_fingerprint",
        "csrf_token",
        "created_at",
        "expires_at",
    }
