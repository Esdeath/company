import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from company_api.config import Settings
from company_api.content_store import ContentStore
from company_api.db import (
    ReadinessProbe,
    SqlAlchemyReadinessProbe,
    create_engine_and_session_factory,
)
from company_api.library_service import LibraryOperations, LibraryService
from company_api.repository import SqlAlchemyLibraryRepository
from company_api.routes import router as library_router

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["live", "ready", "not_ready"]


def create_app(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
    library_service: LibraryOperations | None = None,
) -> FastAPI:
    # BaseSettings supplies required fields from the environment at runtime.
    resolved_settings = settings if settings is not None else Settings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        session_factory = None
        if readiness_probe is None or library_service is None:
            engine, session_factory = create_engine_and_session_factory(resolved_settings)

        if readiness_probe is not None:
            app.state.readiness_probe = readiness_probe
        else:
            assert engine is not None
            app.state.readiness_probe = SqlAlchemyReadinessProbe(engine)
        app.state.library_service = library_service
        if app.state.library_service is None:
            assert session_factory is not None
            repository = SqlAlchemyLibraryRepository(session_factory)
            app.state.library_service = LibraryService(
                repository,
                ContentStore(resolved_settings.content_root),
            )
        try:
            yield
        finally:
            if engine is not None:
                await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=True,
    )
    app.include_router(library_router)

    @app.get("/api/health/live", response_model=HealthResponse)
    async def live() -> HealthResponse:
        return HealthResponse(status="live")

    @app.get("/api/health/ready", response_model=HealthResponse)
    async def ready(request: Request) -> HealthResponse | JSONResponse:
        probe: ReadinessProbe = request.app.state.readiness_probe
        try:
            await probe.check()
        except Exception:
            logger.error("Readiness probe failed")
            return JSONResponse(
                status_code=503,
                content=HealthResponse(status="not_ready").model_dump(),
            )
        return HealthResponse(status="ready")

    return app
