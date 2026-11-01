from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import health
from app.api import v1 as api_v1
from app.config import Settings, get_settings
from app.db.session import init_db
from app.errors import register_error_handlers
from app.logging_config import configure_logging
from app.middleware import REQUEST_ID_HEADER, request_context
from app.monitoring.scheduler import get_monitoring_scheduler
from app.scans.manager import get_scan_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    scheduler = get_monitoring_scheduler()
    scan_mgr = get_scan_manager()
    session_factory = getattr(scan_mgr, "_session_factory", None)
    if session_factory:
        init_db()
        await scheduler.start(session_factory, scan_mgr)
    yield
    scheduler.stop()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Veritor API", version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)

    # The middleware added last runs first, so CORS also covers errors from request_context.
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_context)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.include_router(health.router)
    app.include_router(api_v1.router)
    return app


app = create_app()
