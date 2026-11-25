"""Tests to exercise logging, exception mapping, security IP branches, and dependencies."""

import logging
from unittest.mock import MagicMock

import pytest
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from app.config import Settings
from app.core.errors import ForbiddenOriginError, validation_exception_handler
from app.core.logging import JSONLogFormatter, setup_logging
from app.core.security import get_client_ip, verify_same_origin
from app.dependencies import get_app_settings, get_http_client, get_store


def test_json_formatter() -> None:
    formatter = JSONLogFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="test message",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-123"  # type: ignore[attr-defined]
    record.extra_data = {"key": "val"}  # type: ignore[attr-defined]

    output = formatter.format(record)
    assert '"request_id": "req-123"' in output
    assert '"key": "val"' in output


def test_setup_logging() -> None:
    setup_logging("DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG


@pytest.mark.asyncio
async def test_validation_exception_handler() -> None:
    req = Request({"type": "http"})
    exc = RequestValidationError(
        [{"loc": ("body", "field"), "msg": "field required", "type": "missing"}]
    )
    res = await validation_exception_handler(req, exc)
    assert res.status_code == 422
    assert "body -> field: field required" in res.body.decode()


def test_get_client_ip_variants() -> None:
    # Real-IP header
    scope1 = {
        "type": "http",
        "headers": [(b"x-real-ip", b"198.51.100.1")],
        "client": ("127.0.0.1", 1234),
    }
    assert get_client_ip(Request(scope1), is_production=True) == "198.51.100.1"

    # Forwarded-For header
    scope2 = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"198.51.100.2, 10.0.0.1")],
        "client": ("127.0.0.1", 1234),
    }
    assert get_client_ip(Request(scope2), is_production=True) == "198.51.100.2"

    # Production with no proxy headers
    scope3 = {
        "type": "http",
        "headers": [],
        "client": ("198.51.100.3", 1234),
    }
    assert get_client_ip(Request(scope3), is_production=True) == "198.51.100.3"

    # No client info at all
    scope4 = {"type": "http", "headers": [], "client": None}
    assert get_client_ip(Request(scope4), is_production=False) == "127.0.0.1"


def test_verify_same_origin_edge_cases() -> None:
    settings = Settings(APP_ENV="production", APP_SECRET="a" * 32)
    # Origin present but no host header
    scope = {
        "type": "http",
        "headers": [(b"origin", b"https://example.com")],
    }
    with pytest.raises(ForbiddenOriginError):
        verify_same_origin(Request(scope), settings)


def test_dependencies_helpers() -> None:
    settings = get_app_settings()
    assert settings.APP_NAME if hasattr(settings, "APP_NAME") else True

    fake_request = MagicMock()
    fake_request.app.state.http_client = "client"
    fake_request.app.state.store = "store"

    assert get_http_client(fake_request) == "client"
    assert get_store(fake_request) == "store"
