"""HTTP client factory and resilient request execution."""

import asyncio
from typing import Any

import httpx

from app.constants import APP_NAME, APP_VERSION, HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT
from app.core.errors import ProviderUnavailableError


def create_http_client(contact_email: str) -> httpx.AsyncClient:
    """Create shared httpx.AsyncClient with identifying User-Agent."""
    headers = {
        "User-Agent": f"{APP_NAME}/{APP_VERSION} (+contact: {contact_email})",
        "Accept": "application/json",
    }
    timeout = httpx.Timeout(
        connect=HTTP_CONNECT_TIMEOUT,
        read=HTTP_READ_TIMEOUT,
        write=5.0,
        pool=5.0,
    )
    return httpx.AsyncClient(headers=headers, timeout=timeout)


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retries: int = 1,
    backoff_s: float = 0.3,
) -> httpx.Response:
    """Perform request with 1 retry on timeout or 5xx server errors."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            res = await client.request(method, url, params=params, headers=headers)
            if res.status_code >= 500:
                if attempt < retries:
                    await asyncio.sleep(backoff_s)
                    continue
                raise ProviderUnavailableError(f"Provider returned HTTP {res.status_code}")
            return res
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e
            if attempt < retries:
                await asyncio.sleep(backoff_s)
                continue
            raise ProviderUnavailableError("Provider connection timed out or failed") from e
    raise ProviderUnavailableError("Provider request failed after retries") from last_exc
