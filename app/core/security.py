"""Security headers middleware, origin checks, client IP extraction, HMAC subject hashing."""

import hashlib
import hmac
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.config import Settings
from app.core.errors import ForbiddenOriginError


def get_client_ip(request: Request, is_production: bool = False) -> str:
    """Extract client IP according to trusted proxies rule."""
    if is_production:
        vercel_ip = request.headers.get("x-vercel-forwarded-for")
        if vercel_ip:
            return vercel_ip.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()

    if request.client:
        return request.client.host
    return "127.0.0.1"


def hash_subject(ip: str, secret: str, date: str | None = None) -> str:
    """Create anonymized daily reporter hash HMAC-SHA256(secret, ip + UTC date)."""
    if date is None:
        date = datetime.now(UTC).strftime("%Y-%m-%d")
    message = f"{ip}:{date}".encode()
    key = secret.encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()[:32]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces WCAG / OWASP CSP and browser security headers."""

    def __init__(self, app: ASGIApp, app_env: str = "development") -> None:
        super().__init__(app)
        self.app_env = app_env

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response: Response = await call_next(request)

        csp = (
            "default-src 'self'; "
            "img-src 'self' data: https://tile.openstreetmap.org; "
            "script-src 'self'; "
            "style-src 'self'; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )

        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

        if self.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


def verify_same_origin(request: Request, settings: Settings) -> None:
    """Enforce same origin for state-changing POST requests."""
    origin = request.headers.get("origin")
    if not origin:
        if settings.APP_ENV == "test":
            return
        return

    host = request.headers.get("host")
    if not host:
        raise ForbiddenOriginError()

    clean_origin = origin.replace("https://", "").replace("http://", "").split("/")[0]
    if clean_origin != host:
        raise ForbiddenOriginError()
