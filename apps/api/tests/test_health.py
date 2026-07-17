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


def test_live_returns_ok_without_calling_failing_probe() -> None:
    with TestClient(create_app(settings(), FailingProbe())) as client:
        response = client.get("/api/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok_when_probe_succeeds() -> None:
    with TestClient(create_app(settings(), SuccessfulProbe())) as client:
        response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_safe_unavailable_response_when_probe_fails() -> None:
    with TestClient(create_app(settings(), FailingProbe())) as client:
        response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    response_text = response.text.lower()
    for secret in (
        "postgres",
        "company",
        "secret",
        "runtimeerror",
        "postgresql+psycopg://company:secret@postgres:5432/company",
    ):
        assert secret not in response_text


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
