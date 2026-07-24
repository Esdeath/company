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
        "reply_to_id": ("comments.id", "SET NULL"),
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

    assert {
        foreign_key.constraint.name
        for table in Base.metadata.tables.values()
        for foreign_key in table.foreign_keys
        if table.name
        in {
            "user_sessions",
            "user_tokens",
            "comments",
            "comment_reports",
            "notifications",
            "email_outbox",
        }
    } == {
        "fk_comment_reports_comment_id_comments",
        "fk_comment_reports_reporter_id_users",
        "fk_comments_author_id_users",
        "fk_comments_document_id_documents",
        "fk_comments_parent_id_comments",
        "fk_comments_reply_to_id_comments",
        "fk_email_outbox_token_id_user_tokens",
        "fk_notifications_actor_id_users",
        "fk_notifications_comment_id_comments",
        "fk_notifications_document_id_documents",
        "fk_notifications_recipient_id_users",
        "fk_user_sessions_user_id_users",
        "fk_user_tokens_user_id_users",
    }


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
    body_length_constraint = next(
        constraint
        for constraint in comments.constraints
        if constraint.name == "ck_comments_body_length"
    )
    assert comments.c.body.nullable is True
    assert str(body_length_constraint.sqltext) == (
        "status = 'DELETED' OR (body IS NOT NULL AND char_length(body) BETWEEN 1 AND 2000)"
    )
    assert "ix_comments_reply_to_id" in {index.name for index in comments.indexes}


def test_new_tables_use_stable_primary_key_constraint_names() -> None:
    primary_key_names = {
        table_name: table.primary_key.name
        for table_name, table in Base.metadata.tables.items()
        if table_name
        in {
            "users",
            "user_sessions",
            "user_auth_challenges",
            "user_tokens",
            "comments",
            "comment_reports",
            "notifications",
            "email_outbox",
            "rate_limit_buckets",
        }
    }

    assert primary_key_names == {
        "users": "pk_users",
        "user_sessions": "pk_user_sessions",
        "user_auth_challenges": "pk_user_auth_challenges",
        "user_tokens": "pk_user_tokens",
        "comments": "pk_comments",
        "comment_reports": "pk_comment_reports",
        "notifications": "pk_notifications",
        "email_outbox": "pk_email_outbox",
        "rate_limit_buckets": "pk_rate_limit_buckets",
    }


def test_rate_limit_bucket_uses_a_composite_primary_key() -> None:
    rate_limit_buckets = Base.metadata.tables["rate_limit_buckets"]

    assert tuple(rate_limit_buckets.primary_key.columns.keys()) == (
        "action",
        "subject_hash",
        "window_started_at",
    )
