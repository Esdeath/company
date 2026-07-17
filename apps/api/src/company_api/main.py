import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine

from company_api.config import Settings
from company_api.db import ReadinessProbe, SqlAlchemyReadinessProbe

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["live", "ready", "not_ready"]


def create_app(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI:
    # BaseSettings supplies required fields from the environment at runtime.
    resolved_settings = settings if settings is not None else Settings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if readiness_probe is not None:
            app.state.readiness_probe = readiness_probe
            yield
            return

        engine = create_async_engine(resolved_settings.database_url)
        app.state.readiness_probe = SqlAlchemyReadinessProbe(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=True,
    )

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
