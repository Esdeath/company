from pathlib import Path

from pwdlib import PasswordHash
from pydantic import Field, field_validator
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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def session_cookie_name(self) -> str:
        if self.session_cookie_secure:
            return "__Host-company-admin-session"
        return "company-admin-session"
