"""Test application error hierarchy and status codes."""

from app.core.errors import (
    ForbiddenOriginError,
    NotFoundError,
    ProviderUnavailableError,
    RateLimitedError,
    StorageUnavailableError,
    ValidationAppError,
)


def test_error_status_codes() -> None:
    assert ValidationAppError("bad").status_code == 422
    assert NotFoundError("missing").status_code == 404
    assert RateLimitedError().status_code == 429
    assert ProviderUnavailableError().status_code == 503
    assert StorageUnavailableError().status_code == 503
    assert ForbiddenOriginError().status_code == 403
