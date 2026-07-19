from pathlib import Path

import pytest
from pydantic import ValidationError

from company_api.config import Settings


def test_content_root_defaults_to_data_content() -> None:
    settings = Settings(database_url="postgresql+psycopg://company@postgres/company")

    assert settings.content_root == Path("/data/content")


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


def test_wildcard_cors_origin_is_rejected_without_leaking_database_url() -> None:
    database_url = "postgresql+psycopg://company:topsecret@postgres/company"

    with pytest.raises(ValidationError) as error:
        Settings(database_url=database_url, cors_origins="*")

    assert database_url not in str(error.value)
    assert "topsecret" not in str(error.value)


def test_external_cors_origin_is_rejected_without_leaking_database_url() -> None:
    database_url = "postgresql+psycopg://company:topsecret@postgres/company"

    with pytest.raises(ValidationError) as error:
        Settings(database_url=database_url, cors_origins="https://example.com")

    assert database_url not in str(error.value)
    assert "topsecret" not in str(error.value)
