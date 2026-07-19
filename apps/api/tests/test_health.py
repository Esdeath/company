import logging

import pytest
from fastapi.testclient import TestClient

from company_api.config import Settings
from company_api.main import create_app


class SuccessfulProbe:
    async def check(self) -> None:
        return None


class FailingProbe:
    async def check(self) -> None:
        raise RuntimeError("postgresql+psycopg://company:secret@postgres:5432/company")


def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://company:local@postgres:5432/company",
        cors_origins="http://localhost:3000,http://localhost:5173",
    )


def test_live_returns_live_without_calling_failing_probe() -> None:
    with TestClient(create_app(settings(), FailingProbe())) as client:
        response = client.get("/api/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_default_database_probe_disposes_engine_on_shutdown() -> None:
    with TestClient(create_app(settings())):
        pass


def test_injected_probe_is_preserved_when_library_service_is_injected() -> None:
    service = object()
    with TestClient(
        create_app(settings(), SuccessfulProbe(), library_service=service)  # type: ignore[arg-type]
    ) as client:
        response = client.get("/api/health/ready")

    assert response.status_code == 200


def test_ready_returns_ready_when_probe_succeeds() -> None:
    with TestClient(create_app(settings(), SuccessfulProbe())) as client:
        response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_safe_not_ready_response_when_probe_fails() -> None:
    with TestClient(create_app(settings(), FailingProbe())) as client:
        response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    response_text = response.text.lower()
    for secret in (
        "postgres",
        "company",
        "secret",
        "runtimeerror",
        "postgresql+psycopg://company:secret@postgres:5432/company",
    ):
        assert secret not in response_text


def test_ready_logs_only_a_fixed_safe_message_when_probe_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        caplog.at_level(logging.ERROR, logger="company_api.main"),
        TestClient(create_app(settings(), FailingProbe())) as client,
    ):
        response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert caplog.messages == ["Readiness probe failed"]
    logged_text = "\n".join(caplog.messages).lower()
    for secret in (
        "postgres",
        "company",
        "secret",
        "runtimeerror",
        "postgresql+psycopg://company:secret@postgres:5432/company",
    ):
        assert secret not in logged_text
    assert all(record.exc_info is None for record in caplog.records)


def test_cors_allows_configured_origin() -> None:
    with TestClient(create_app(settings(), SuccessfulProbe())) as client:
        response = client.get(
            "/api/health/live",
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_does_not_allow_unconfigured_origin() -> None:
    with TestClient(create_app(settings(), SuccessfulProbe())) as client:
        response = client.get(
            "/api/health/live",
            headers={"Origin": "https://example.com"},
        )

    assert "access-control-allow-origin" not in response.headers
