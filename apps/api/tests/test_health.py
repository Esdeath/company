import asyncio
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

import company_api.main as main_module
from company_api.config import Settings
from company_api.main import create_app

ADMIN_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "aXR5J2OvFOW7Bb653Nn6mQ$Mjw20TGkSlMBsX4JsoCVfOe1DH6Cedzk01lTosf8YPU"
)


class SuccessfulProbe:
    async def check(self) -> None:
        return None


class FailingProbe:
    async def check(self) -> None:
        raise RuntimeError("postgresql+psycopg://company:secret@postgres:5432/company")


class FakeEngine:
    def __init__(self, events: list[str] | None = None) -> None:
        self.dispose_calls = 0
        self.events = events

    async def dispose(self) -> None:
        self.dispose_calls += 1
        if self.events is not None:
            self.events.append("engine disposed")


class ExternalProbe:
    def __init__(self, engine: FakeEngine) -> None:
        self.engine = engine

    async def check(self) -> None:
        return None


class TrackingDispatcher:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.run_calls = 0

    async def run(self, stop: asyncio.Event) -> None:
        self.run_calls += 1
        self.events.append("dispatcher started")
        await stop.wait()
        self.events.append("dispatcher stopped")


class FailingDispatcher:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def run(self, stop: asyncio.Event) -> None:
        await stop.wait()
        self.events.append("dispatcher failed")
        raise RuntimeError("dispatcher shutdown failed")


def quiet_dispatcher() -> TrackingDispatcher:
    return TrackingDispatcher([])


def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://company:local@postgres:5432/company",
        admin_username="admin",
        admin_password_hash=ADMIN_HASH,
        cors_origins="http://localhost:3000,http://localhost:5173",
    )


def test_live_returns_live_without_calling_failing_probe() -> None:
    with TestClient(
        create_app(settings(), FailingProbe(), email_dispatcher=quiet_dispatcher())  # type: ignore[arg-type]
    ) as client:
        response = client.get("/api/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_app_owned_engine_is_disposed_on_normal_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    monkeypatch.setattr(
        main_module,
        "create_engine_and_session_factory",
        lambda resolved_settings: (engine, object()),
    )

    with TestClient(create_app(settings(), email_dispatcher=quiet_dispatcher())):  # type: ignore[arg-type]
        pass

    assert engine.dispose_calls == 1


def test_app_owned_engine_is_disposed_when_content_store_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    monkeypatch.setattr(
        main_module,
        "create_engine_and_session_factory",
        lambda resolved_settings: (engine, object()),
    )

    def fail_content_store(content_root: Any) -> None:
        del content_root
        raise RuntimeError("content store construction failed")

    monkeypatch.setattr(main_module, "ContentStore", fail_content_store)

    with (
        pytest.raises(RuntimeError, match="content store construction failed"),
        TestClient(create_app(settings(), email_dispatcher=quiet_dispatcher())),  # type: ignore[arg-type]
    ):
        pass

    assert engine.dispose_calls == 1


def test_injected_dependencies_do_not_dispose_external_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external_engine = FakeEngine()
    external_probe = ExternalProbe(external_engine)
    service = object()

    def fail_if_factory_called(resolved_settings: Settings) -> None:
        del resolved_settings
        raise AssertionError("app must not create an engine for injected dependencies")

    monkeypatch.setattr(
        main_module,
        "create_engine_and_session_factory",
        fail_if_factory_called,
    )

    with TestClient(
        create_app(
            settings(),
            external_probe,
            library_service=service,  # type: ignore[arg-type]
            auth_service=object(),  # type: ignore[arg-type]
        )
    ):
        pass

    assert external_engine.dispose_calls == 0


def test_injected_user_auth_and_dispatcher_do_not_create_an_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    dispatcher = TrackingDispatcher(events)

    def fail_if_factory_called(resolved_settings: Settings) -> None:
        del resolved_settings
        raise AssertionError("app must not create an engine for injected dependencies")

    monkeypatch.setattr(
        main_module,
        "create_engine_and_session_factory",
        fail_if_factory_called,
    )

    with TestClient(
        create_app(
            settings(),
            SuccessfulProbe(),
            library_service=object(),  # type: ignore[arg-type]
            auth_service=object(),  # type: ignore[arg-type]
            user_auth_service=object(),  # type: ignore[arg-type]
            email_dispatcher=dispatcher,  # type: ignore[arg-type]
        )
    ):
        assert events == ["dispatcher started"]

    assert events == ["dispatcher started", "dispatcher stopped"]
    assert dispatcher.run_calls == 1


def test_dispatcher_stops_before_app_owned_engine_is_disposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    engine = FakeEngine(events)
    dispatcher = TrackingDispatcher(events)
    monkeypatch.setattr(
        main_module,
        "create_engine_and_session_factory",
        lambda resolved_settings: (engine, object()),
    )

    with TestClient(create_app(settings(), email_dispatcher=dispatcher)):  # type: ignore[arg-type]
        assert events == ["dispatcher started"]

    assert events == ["dispatcher started", "dispatcher stopped", "engine disposed"]
    assert dispatcher.run_calls == 1


def test_dispatcher_failure_does_not_skip_app_owned_engine_disposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    engine = FakeEngine(events)
    monkeypatch.setattr(
        main_module,
        "create_engine_and_session_factory",
        lambda resolved_settings: (engine, object()),
    )

    with (
        pytest.raises(RuntimeError, match="dispatcher shutdown failed"),
        TestClient(
            create_app(settings(), email_dispatcher=FailingDispatcher(events))  # type: ignore[arg-type]
        ),
    ):
        pass

    assert events == ["dispatcher failed", "engine disposed"]


def test_user_account_error_boundary_does_not_swallow_unrelated_route_errors() -> None:
    application = create_app(
        settings(),
        SuccessfulProbe(),
        library_service=object(),  # type: ignore[arg-type]
        auth_service=object(),  # type: ignore[arg-type]
        user_auth_service=object(),  # type: ignore[arg-type]
        email_dispatcher=quiet_dispatcher(),  # type: ignore[arg-type]
    )

    @application.get("/unrelated-error")
    async def unrelated_error() -> None:
        raise RuntimeError("unrelated route failed")

    with (
        TestClient(application) as client,
        pytest.raises(RuntimeError, match="unrelated route failed"),
    ):
        client.get("/unrelated-error")


def test_injected_probe_is_preserved_when_library_service_is_injected() -> None:
    service = object()
    with TestClient(
        create_app(
            settings(),
            SuccessfulProbe(),
            library_service=service,  # type: ignore[arg-type]
            email_dispatcher=quiet_dispatcher(),  # type: ignore[arg-type]
        )
    ) as client:
        response = client.get("/api/health/ready")

    assert response.status_code == 200


def test_ready_returns_ready_when_probe_succeeds() -> None:
    with TestClient(
        create_app(settings(), SuccessfulProbe(), email_dispatcher=quiet_dispatcher())  # type: ignore[arg-type]
    ) as client:
        response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_safe_not_ready_response_when_probe_fails() -> None:
    with TestClient(
        create_app(settings(), FailingProbe(), email_dispatcher=quiet_dispatcher())  # type: ignore[arg-type]
    ) as client:
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
        TestClient(
            create_app(settings(), FailingProbe(), email_dispatcher=quiet_dispatcher())  # type: ignore[arg-type]
        ) as client,
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
    with TestClient(
        create_app(settings(), SuccessfulProbe(), email_dispatcher=quiet_dispatcher())  # type: ignore[arg-type]
    ) as client:
        response = client.get(
            "/api/health/live",
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_does_not_allow_unconfigured_origin() -> None:
    with TestClient(
        create_app(settings(), SuccessfulProbe(), email_dispatcher=quiet_dispatcher())  # type: ignore[arg-type]
    ) as client:
        response = client.get(
            "/api/health/live",
            headers={"Origin": "https://example.com"},
        )

    assert "access-control-allow-origin" not in response.headers
