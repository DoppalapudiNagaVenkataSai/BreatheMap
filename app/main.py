"""FastAPI main application setup with lifespan and middleware."""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, air, geo, health, pages, reports, routes
from app.config import get_settings
from app.constants import (
    APP_NAME,
    APP_VERSION,
    HTTP_CONNECT_TIMEOUT,
    HTTP_READ_TIMEOUT,
    MAX_JSON_BODY_BYTES,
)
from app.core.errors import (
    AppError,
    app_error_handler,
    validation_exception_handler,
)
from app.core.logging import RequestIDMiddleware, setup_logging
from app.core.security import SecurityHeadersMiddleware
from app.dependencies import create_store


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan managing shared resources."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    # Initialize single shared store per process
    app.state.store = create_store(settings)

    # Shared async HTTP client
    transport = httpx.AsyncHTTPTransport(retries=1)
    timeout = httpx.Timeout(
        connect=HTTP_CONNECT_TIMEOUT, read=HTTP_READ_TIMEOUT, write=5.0, pool=5.0
    )
    async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
        app.state.http_client = client
        yield

    # Teardown
    clear_fn = getattr(app.state.store, "clear", None)
    if callable(clear_fn):
        clear_fn()
    close_fn = getattr(app.state.store, "close", None)
    if callable(close_fn):
        res = close_fn()
        if hasattr(res, "__await__"):
            await res


async def body_size_limit_middleware(
    request: Request, call_next: Callable[[Request], Any]
) -> JSONResponse:
    """Enforce max request body size of 16 KB for JSON payloads."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_JSON_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": (
                        f"Payload exceeds maximum allowed size of {MAX_JSON_BODY_BYTES} bytes"
                    ),
                }
            },
        )
    return await call_next(request)  # type: ignore[no-any-return]


def create_app() -> FastAPI:
    """Application factory for BreatheMap."""
    settings = get_settings()

    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url=None,  # Disabled for security in production/strict mode
        redoc_url=None,
    )

    # Register custom exception handlers
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

    # Middleware order: inner to outer execution -> GZip -> Security -> RequestID
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SecurityHeadersMiddleware, app_env=settings.APP_ENV)
    app.add_middleware(RequestIDMiddleware)
    app.middleware("http")(body_size_limit_middleware)

    # Mount static assets for local dev
    static_path = Path(__file__).resolve().parent.parent / "public" / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # Routers
    app.include_router(health.router)
    app.include_router(geo.router)
    app.include_router(air.router)
    app.include_router(routes.router)
    app.include_router(reports.router)
    app.include_router(admin.router)
    app.include_router(pages.router)

    return app


app = create_app()
