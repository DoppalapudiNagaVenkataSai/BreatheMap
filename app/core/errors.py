"""Application error types and standard error envelopes."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error producing standard envelope."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ValidationAppError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=422)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(code="NOT_FOUND", message=message, status_code=404)


class RateLimitedError(AppError):
    def __init__(self, message: str = "Rate limit exceeded. Please try again later.") -> None:
        super().__init__(code="RATE_LIMITED", message=message, status_code=429)


class ProviderUnavailableError(AppError):
    def __init__(self, message: str = "Upstream provider temporarily unavailable.") -> None:
        super().__init__(code="PROVIDER_UNAVAILABLE", message=message, status_code=503)


class StorageUnavailableError(AppError):
    def __init__(self, message: str = "Storage service temporarily unavailable.") -> None:
        super().__init__(code="STORAGE_UNAVAILABLE", message=message, status_code=503)


class ForbiddenOriginError(AppError):
    def __init__(self, message: str = "Forbidden request origin.") -> None:
        super().__init__(code="FORBIDDEN_ORIGIN", message=message, status_code=403)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handler for all domain AppError instances."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Format FastAPI validation error into standard envelope with first readable message."""
    errors = exc.errors()
    first_msg = errors[0]["msg"] if errors else "Invalid request body or query parameter"
    first_loc = " -> ".join(str(loc) for loc in errors[0].get("loc", [])) if errors else ""
    formatted_message = f"{first_loc}: {first_msg}" if first_loc else first_msg

    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": formatted_message}},
    )
