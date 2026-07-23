from company_api.models import Base


def test_company_and_document_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "admin_sessions",
        "companies",
        "comment_reports",
        "comments",
        "documents",
        "email_outbox",
        "login_challenges",
        "notifications",
        "rate_limit_buckets",
        "user_auth_challenges",
        "user_sessions",
        "user_tokens",
        "users",
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


def test_community_foreign_keys_preserve_lifecycle_rules() -> None:
    foreign_keys = {
        table_name: {
            foreign_key.parent.name: (foreign_key.target_fullname, foreign_key.ondelete)
            for foreign_key in table.foreign_keys
        }
        for table_name, table in Base.metadata.tables.items()
    }

    assert foreign_keys["user_sessions"] == {"user_id": ("users.id", "CASCADE")}
    assert foreign_keys["user_auth_challenges"] == {}
    assert foreign_keys["user_tokens"] == {"user_id": ("users.id", "CASCADE")}
    assert foreign_keys["comments"] == {
        "author_id": ("users.id", "SET NULL"),
        "document_id": ("documents.id", "CASCADE"),
        "parent_id": ("comments.id", "SET NULL"),
    }
    assert foreign_keys["comment_reports"] == {
        "comment_id": ("comments.id", "CASCADE"),
        "reporter_id": ("users.id", "CASCADE"),
    }
    assert foreign_keys["notifications"] == {
        "actor_id": ("users.id", "SET NULL"),
        "comment_id": ("comments.id", "CASCADE"),
        "document_id": ("documents.id", "CASCADE"),
        "recipient_id": ("users.id", "CASCADE"),
    }
    assert foreign_keys["email_outbox"] == {"token_id": ("user_tokens.id", "CASCADE")}


def test_community_constraints_protect_normalized_identity_and_comments() -> None:
    users = Base.metadata.tables["users"]
    reports = Base.metadata.tables["comment_reports"]
    comments = Base.metadata.tables["comments"]

    assert {constraint.name for constraint in users.constraints if constraint.name is not None} >= {
        "uq_users_normalized_email",
        "uq_users_normalized_username",
    }
    assert any(
        constraint.name == "uq_comment_reports_comment_reporter"
        for constraint in reports.constraints
    )
    assert any(constraint.name == "ck_comments_body_length" for constraint in comments.constraints)


def test_rate_limit_bucket_uses_a_composite_primary_key() -> None:
    rate_limit_buckets = Base.metadata.tables["rate_limit_buckets"]

    assert tuple(rate_limit_buckets.primary_key.columns.keys()) == (
        "action",
        "subject_hash",
        "window_started_at",
    )
