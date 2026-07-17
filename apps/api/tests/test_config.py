import pytest
from pydantic import ValidationError

from company_api.config import Settings


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings()


def test_blank_cors_origins_is_an_empty_list() -> None:
    settings = Settings(database_url="postgresql+psycopg://company@postgres/company")

    assert settings.cors_origin_list == []


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://company@postgres/company",
        cors_origins=" http://localhost:3000, http://localhost:5173 ",
    )

    assert settings.cors_origin_list == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]
