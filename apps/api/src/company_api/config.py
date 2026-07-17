from pydantic import field_validator
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
    cors_origins: str = ""

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
