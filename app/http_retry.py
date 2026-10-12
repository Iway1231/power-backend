"""Small retry helper for transient upstream HTTP failures."""

import asyncio
import email.utils
import time
from collections.abc import Awaitable, Callable

import httpx

RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, email.utils.parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return None


async def get_with_retry(
    request: Callable[[], Awaitable[httpx.Response]],
    *,
    retries: int,
    backoff_seconds: float,
) -> httpx.Response:
    """Retry transient failures while preserving normal HTTP error semantics."""
    for attempt in range(retries + 1):
        try:
            response = await request()
        except httpx.TransportError:
            if attempt >= retries:
                raise
            await asyncio.sleep(backoff_seconds * (2**attempt))
            continue

        if response.status_code not in RETRYABLE_STATUS_CODES or attempt >= retries:
            response.raise_for_status()
            return response

        delay = _retry_after_seconds(response)
        await asyncio.sleep(delay if delay is not None else backoff_seconds * (2**attempt))

    raise RuntimeError("Retry loop ended unexpectedly")
