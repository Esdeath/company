from pathlib import Path
from typing import Literal

from pwdlib import PasswordHash
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_CORS_ORIGINS = frozenset(
    {
        "http://localhost:3000",
        "http://localhost:5173",
    }
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

    @model_validator(mode="after")
    def validate_community_production_settings(self) -> "Settings":
        if self.app_environment != "production":
            return self

        if self.email_backend != "smtp":
            raise ValueError("Production requires an SMTP email backend")
        if self.user_token_signing_key.get_secret_value() == "local-development-only-signing-key":
            raise ValueError("Production requires a non-local user token signing key")
        if self.user_registration_enabled:
            if not self.smtp_configured:
                raise ValueError("Production registration requires SMTP host and sender")
            if not self.public_base_url.startswith("https://"):
                raise ValueError("Production registration requires an HTTPS public base URL")

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
        return bool(self.smtp_host and self.smtp_sender)
