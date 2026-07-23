from pathlib import Path

import pytest
from pydantic import ValidationError

from company_api.config import Settings

ADMIN_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "aXR5J2OvFOW7Bb653Nn6mQ$Mjw20TGkSlMBsX4JsoCVfOe1DH6Cedzk01lTosf8YPU"
)


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://company@postgres/company",
        "admin_username": "admin",
        "admin_password_hash": ADMIN_HASH,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_content_root_defaults_to_data_content() -> None:
    configured = settings()

    assert configured.content_root == Path("/data/content")


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings()


def test_blank_cors_origins_is_an_empty_list() -> None:
    configured = settings()

    assert configured.cors_origin_list == []


def test_cors_origins_are_split_and_trimmed() -> None:
    configured = settings(
        cors_origins=" http://localhost:3000, http://localhost:5173 ",
    )

    assert configured.cors_origin_list == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]


def test_wildcard_cors_origin_is_rejected_without_leaking_database_url() -> None:
    database_url = "postgresql+psycopg://company:topsecret@postgres/company"

    with pytest.raises(ValidationError) as error:
        settings(database_url=database_url, cors_origins="*")

    assert database_url not in str(error.value)
    assert "topsecret" not in str(error.value)


def test_external_cors_origin_is_rejected_without_leaking_database_url() -> None:
    database_url = "postgresql+psycopg://company:topsecret@postgres/company"

    with pytest.raises(ValidationError) as error:
        settings(database_url=database_url, cors_origins="https://example.com")

    assert database_url not in str(error.value)
    assert "topsecret" not in str(error.value)


def test_admin_password_must_be_an_argon2_hash() -> None:
    with pytest.raises(ValidationError, match="Argon2"):
        settings(admin_password_hash="plaintext-password")


def test_cookie_name_uses_host_prefix_only_for_https() -> None:
    assert settings(session_cookie_secure=True).session_cookie_name.startswith("__Host-")
    assert settings(session_cookie_secure=False).session_cookie_name == "company-admin-session"


def test_production_rejects_non_smtp_email_backend() -> None:
    with pytest.raises(ValidationError, match="SMTP"):
        settings(app_environment="production", email_backend="console")


def test_production_registration_requires_complete_smtp_and_public_https_url() -> None:
    with pytest.raises(ValidationError, match="SMTP"):
        settings(
            app_environment="production",
            email_backend="smtp",
            user_token_signing_key="x" * 32,
            user_registration_enabled=True,
        )


def test_production_rejects_the_local_user_token_signing_key() -> None:
    with pytest.raises(ValidationError, match="signing key"):
        settings(
            app_environment="production",
            email_backend="smtp",
            user_token_signing_key="local-development-only-signing-key",
        )


@pytest.mark.parametrize("signing_key", ["", " " * 32, "x" * 31])
def test_production_rejects_blank_or_short_user_token_signing_keys(signing_key: str) -> None:
    with pytest.raises(ValidationError, match="signing key"):
        settings(
            app_environment="production",
            email_backend="smtp",
            user_token_signing_key=signing_key,
        )


def test_smtp_configured_strips_and_validates_host_and_sender() -> None:
    configured = settings(
        smtp_host=" smtp.example.com ",
        smtp_sender=" sender@example.com ",
    )

    assert configured.smtp_host == "smtp.example.com"
    assert configured.smtp_sender == "sender@example.com"
    assert configured.smtp_configured is True


@pytest.mark.parametrize(
    ("smtp_host", "smtp_sender"),
    [
        (" ", "sender@example.com"),
        ("smtp://example.com", "sender@example.com"),
        ("smtp.example.com", "not-an-email"),
    ],
)
def test_smtp_configured_rejects_invalid_host_or_sender(
    smtp_host: str,
    smtp_sender: str,
) -> None:
    configured = settings(smtp_host=smtp_host, smtp_sender=smtp_sender)

    assert configured.smtp_configured is False


@pytest.mark.parametrize("public_base_url", ["https://", "https://:443", "https://example.com:bad"])
def test_production_registration_rejects_malformed_https_base_urls(public_base_url: str) -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        settings(
            app_environment="production",
            email_backend="smtp",
            user_token_signing_key="x" * 32,
            user_registration_enabled=True,
            smtp_host="smtp.example.com",
            smtp_sender="sender@example.com",
            public_base_url=public_base_url,
        )


def test_production_registration_accepts_validated_smtp_and_https_base_url() -> None:
    configured = settings(
        app_environment="production",
        email_backend="smtp",
        user_token_signing_key="x" * 32,
        user_registration_enabled=True,
        smtp_host="smtp.example.com",
        smtp_sender="sender@example.com",
        public_base_url="https://research.example.com",
    )

    assert configured.smtp_configured is True


def test_test_environment_allows_file_email_backend() -> None:
    configured = settings(app_environment="test", email_backend="file")

    assert configured.smtp_configured is False


def test_user_cookie_is_separate_from_admin_cookie() -> None:
    configured = settings(session_cookie_secure=True)

    assert configured.user_session_cookie_name == "__Host-company-user-session"
    assert configured.user_session_cookie_name != configured.session_cookie_name
