from ipaddress import ip_address
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email
from pwdlib import PasswordHash
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_CORS_ORIGINS = frozenset(
    {
        "http://localhost:3000",
        "http://localhost:5173",
    }
)


def is_valid_host(value: str) -> bool:
    if not value or any(character.isspace() for character in value):
        return False

    if value.endswith("."):
        value = value[:-1]
    if not value or len(value) > 253:
        return False

    labels = value.split(".")
    return all(
        0 < len(label) <= 63
        and label[0].isalnum()
        and label[-1].isalnum()
        and all(character.isalnum() or character == "-" for character in label)
        for label in labels
    )


def is_valid_https_base_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False

    hostname = parsed.hostname
    if hostname is None:
        return False
    try:
        is_loopback = ip_address(hostname).is_loopback
    except ValueError:
        is_loopback = hostname.lower() == "localhost" or hostname.lower().endswith(".localhost")

    return (
        parsed.scheme == "https"
        and is_valid_host(hostname)
        and not is_loopback
        and parsed.username is None
        and parsed.password is None
        and (port is None or 1 <= port <= 65_535)
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    database_url: str
    admin_username: str = Field(min_length=1, max_length=100)
    admin_password_hash: str
    cors_origins: str = ""
    content_root: Path = Path("/data/content")
    session_cookie_secure: bool = True
    session_lifetime_seconds: int = Field(default=43_200, ge=900, le=604_800)
    login_challenge_lifetime_seconds: int = Field(default=600, ge=60, le=3_600)
    app_environment: Literal["development", "test", "production"] = "development"
    user_registration_enabled: bool = False
    comment_writes_enabled: bool = True
    user_session_lifetime_seconds: int = Field(default=2_592_000, ge=3_600, le=2_592_000)
    user_token_signing_key: SecretStr = SecretStr("local-development-only-signing-key")
    email_backend: Literal["console", "file", "smtp"] = "console"
    email_capture_path: Path | None = None
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65_535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = Field(default=10.0, ge=1.0, le=120.0)
    smtp_sender: str = ""
    public_base_url: str = "http://127.0.0.1:3000"
    email_dispatch_interval_seconds: float = Field(default=2.0, ge=0.1, le=60)
    email_max_attempts: int = Field(default=8, ge=1, le=20)

    @field_validator("admin_password_hash")
    @classmethod
    def validate_admin_password_hash(cls, value: str) -> str:
        if not PasswordHash.recommended().current_hasher.identify(value):
            raise ValueError("Admin password must be an Argon2 hash")
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = {origin.strip() for origin in value.split(",") if origin.strip()}
        if not origins <= ALLOWED_CORS_ORIGINS:
            raise ValueError("CORS origins must use approved local development URLs")
        return value

    @field_validator("smtp_host", "smtp_sender", "public_base_url")
    @classmethod
    def strip_community_connection_settings(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_community_production_settings(self) -> "Settings":
        if self.app_environment != "production":
            return self

        if self.email_backend != "smtp":
            raise ValueError("Production requires an SMTP email backend")
        signing_key = self.user_token_signing_key.get_secret_value()
        if (
            signing_key == "local-development-only-signing-key"
            or not signing_key.strip()
            or len(signing_key) < 32
        ):
            raise ValueError("Production requires a non-local user token signing key")
        if not is_valid_https_base_url(self.public_base_url):
            raise ValueError("Production requires an HTTPS public base URL without a path")
        if self.user_registration_enabled and not self.smtp_configured:
            raise ValueError("Production registration requires SMTP host and sender")

        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def session_cookie_name(self) -> str:
        if self.session_cookie_secure:
            return "__Host-company-admin-session"
        return "company-admin-session"

    @property
    def user_session_cookie_name(self) -> str:
        if self.session_cookie_secure:
            return "__Host-company-user-session"
        return "company-user-session"

    @property
    def smtp_configured(self) -> bool:
        if not is_valid_host(self.smtp_host):
            return False

        try:
            validate_email(self.smtp_sender, check_deliverability=False)
        except EmailNotValidError:
            return False
        return True
