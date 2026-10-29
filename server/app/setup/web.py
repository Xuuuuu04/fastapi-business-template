import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.clock import ClockMiddleware
from app.api.errors import add_error_handlers
from app.api.middleware import RequestLimits, RequestMiddleware
from app.api.routers import routers_for
from app.setup.application import application as declared_application
from app.setup.build import Services, build
from shared.application.spec import ApplicationSpec
from shared.config.settings import Settings
from shared.logs.setup import setup_logs

MULTIPART_ALLOWANCE = 64 * 1024

log = logging.getLogger("server.setup")


def create_app(
    settings: Settings | None = None,
    services: Services | None = None,
    *,
    application: ApplicationSpec | None = None,
) -> FastAPI:
    specification = application or declared_application()
    settings = settings or (services.settings if services else specification.settings())
    settings = specification.prepare(settings)
    setup_logs(json_lines=settings.env == "production")
    services = services or build(settings, application=specification)
    app = FastAPI(
        title=settings.name,
        version=specification.version,
        description="按模块组织的单体后端。每个接口背后是一个登记过的操作，可以按运行编号查看执行过程。",
        docs_url="/docs" if settings.docs else None,
        redoc_url="/redoc" if settings.docs else None,
        openapi_url="/openapi.json" if settings.docs else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.services = services
    app.state.application = specification
    configure_http(app, settings)
    app.add_middleware(ClockMiddleware, clock=services.runtime.clock)
    for router in routers_for(services.catalog.modules):
        app.include_router(router)
    for router in specification.routers:
        app.include_router(router)
    if specification.api_setup is not None:
        specification.api_setup(app)
    return app


def configure_http(app: FastAPI, settings: Settings) -> None:
    app.state.limits = RequestLimits(
        settings.max_body_bytes,
        settings.max_inflight,
        settings.upload_max_bytes + MULTIPART_ALLOWANCE,
        tuple(settings.upload_paths),
        settings.body_timeout_seconds,
        settings.upload_timeout_seconds,
    )
    add_error_handlers(app)
    app.add_middleware(
        RequestMiddleware, limits=app.state.limits, hsts_seconds=settings.hsts_seconds
    )
    if settings.cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=[
                "Content-Type",
                "Authorization",
                "X-API-Key",
                "Idempotency-Key",
                "X-Request-ID",
            ],
            expose_headers=["X-Request-ID", "X-Run-ID"],
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    services: Services = app.state.services
    flushing = None
    if not services.recorder.store.immediate:
        flushing = asyncio.create_task(services.recorder.run_forever())
    log.info(
        "server_started env=%s modules=%s code=%s",
        settings.env,
        ",".join(services.catalog.modules),
        settings.code_version,
    )
    try:
        yield
    finally:
        if flushing is not None:
            await services.recorder.stop(flushing)
        await services.close()
        log.info("server_stopped")
