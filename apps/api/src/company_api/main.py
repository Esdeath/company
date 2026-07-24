import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from company_api.auth import AuthOperations, AuthService
from company_api.auth_repository import SqlAlchemyAuthRepository
from company_api.auth_routes import router as auth_router
from company_api.config import Settings
from company_api.content_store import ContentStore
from company_api.db import (
    ReadinessProbe,
    SqlAlchemyReadinessProbe,
    create_engine_and_session_factory,
)
from company_api.email_outbox import (
    EmailDispatcher,
    EmailJob,
    SqlAlchemyEmailOutboxRepository,
)
from company_api.email_tokens import EmailTokenSigner
from company_api.library_service import LibraryOperations, LibraryService
from company_api.mailer import ConsoleMailer, EmailMessage, FileCaptureMailer, Mailer, SmtpMailer
from company_api.models import UserTokenPurpose
from company_api.rate_limit import SqlAlchemyRateLimiter
from company_api.repository import SqlAlchemyLibraryRepository
from company_api.routes import router as library_router
from company_api.user_auth import UserAuthOperations, UserAuthService
from company_api.user_auth_repository import SqlAlchemyUserAuthRepository
from company_api.user_auth_routes import router as user_auth_router

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["live", "ready", "not_ready"]


def _mailer(settings: Settings) -> Mailer:
    if settings.email_backend == "smtp":
        return SmtpMailer(settings)
    if settings.email_backend == "file":
        return FileCaptureMailer(settings)
    return ConsoleMailer()


def _message_factory(
    signer: EmailTokenSigner, settings: Settings
) -> Callable[[EmailJob], EmailMessage]:
    base_url = settings.public_base_url.rstrip("/")

    def create_message(job: EmailJob) -> EmailMessage:
        if job.token_id is None:
            raise ValueError("token email is missing a token id")
        username = str(job.payload.get("username", "读者"))
        if job.template == "verify_email":
            token = signer.issue(job.token_id, UserTokenPurpose.VERIFY_EMAIL)
            subject = "验证你的研究资料库账号"
            action = "完成邮箱验证"
            url = f"{base_url}/?verify-email={token}"
        elif job.template == "reset_password":
            token = signer.issue(job.token_id, UserTokenPurpose.RESET_PASSWORD)
            subject = "重置你的研究资料库密码"
            action = "重置密码"
            url = f"{base_url}/?password-reset={token}"
        else:
            raise ValueError("unsupported email template")
        return EmailMessage(
            recipient=job.recipient,
            subject=subject,
            text_body=f"{username}，你好。请打开以下链接{action}：\n{url}",
        )

    return create_message


def create_app(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
    library_service: LibraryOperations | None = None,
    auth_service: AuthOperations | None = None,
    user_auth_service: UserAuthOperations | None = None,
    email_dispatcher: EmailDispatcher | None = None,
) -> FastAPI:
    # BaseSettings supplies required fields from the environment at runtime.
    resolved_settings = settings if settings is not None else Settings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        owns_engine = not (
            readiness_probe is not None and library_service is not None and auth_service is not None
        )
        engine = None
        dispatcher = email_dispatcher
        dispatcher_stop: asyncio.Event | None = None
        dispatcher_task: asyncio.Task[None] | None = None

        try:
            if not owns_engine:
                app.state.readiness_probe = readiness_probe
                app.state.library_service = library_service
                app.state.auth_service = auth_service
                app.state.user_auth_service = user_auth_service
            else:
                engine, session_factory = create_engine_and_session_factory(resolved_settings)
                app.state.readiness_probe = (
                    readiness_probe
                    if readiness_probe is not None
                    else SqlAlchemyReadinessProbe(engine)
                )
                app.state.library_service = library_service
                if app.state.library_service is None:
                    repository = SqlAlchemyLibraryRepository(session_factory)
                    app.state.library_service = LibraryService(
                        repository,
                        ContentStore(resolved_settings.content_root),
                    )
                app.state.auth_service = auth_service
                if app.state.auth_service is None:
                    app.state.auth_service = AuthService(
                        SqlAlchemyAuthRepository(session_factory),
                        resolved_settings,
                    )
                app.state.user_auth_service = user_auth_service
                signer = EmailTokenSigner(
                    resolved_settings.user_token_signing_key.get_secret_value()
                )
                if app.state.user_auth_service is None:
                    app.state.user_auth_service = UserAuthService(
                        SqlAlchemyUserAuthRepository(session_factory),
                        SqlAlchemyRateLimiter(session_factory),
                        signer,
                        resolved_settings,
                    )
                if dispatcher is None:
                    dispatcher = EmailDispatcher(
                        SqlAlchemyEmailOutboxRepository(
                            session_factory,
                            max_attempts=resolved_settings.email_max_attempts,
                        ),
                        _mailer(resolved_settings),
                        _message_factory(signer, resolved_settings),
                        interval_seconds=resolved_settings.email_dispatch_interval_seconds,
                    )

            if dispatcher is not None:
                dispatcher_stop = asyncio.Event()
                dispatcher_task = asyncio.create_task(dispatcher.run(dispatcher_stop))
                await asyncio.sleep(0)
            yield
        finally:
            try:
                if dispatcher_stop is not None and dispatcher_task is not None:
                    dispatcher_stop.set()
                    await dispatcher_task
            finally:
                if engine is not None:
                    await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=True,
    )

    @app.middleware("http")
    async def disable_user_account_cache(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        is_user_account_request = (
            path.startswith("/api/v1/user-auth/")
            or path == "/api/v1/users/me"
            or path.startswith("/api/v1/users/me/")
        )
        if not is_user_account_request:
            return await call_next(request)

        try:
            response = await call_next(request)
        except Exception:
            logger.error("User account request failed")
            return JSONResponse(
                status_code=500,
                content={"detail": "服务器暂时无法处理请求，请稍后重试"},
                headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    app.include_router(library_router)
    app.include_router(auth_router)
    app.include_router(user_auth_router)

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
