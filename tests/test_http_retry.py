import httpx
import pytest

from app.http_retry import get_with_retry


def response(status_code: int) -> httpx.Response:
    request = httpx.Request("GET", "https://example.test")
    return httpx.Response(status_code, request=request, headers={"Retry-After": "0"})


@pytest.mark.asyncio
async def test_retries_transport_error_then_returns_response():
    calls = 0

    async def request():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary failure")
        return response(200)

    result = await get_with_retry(request, retries=2, backoff_seconds=0)

    assert result.status_code == 200
    assert calls == 2


@pytest.mark.asyncio
async def test_retries_retryable_status_and_honors_retry_after():
    calls = 0

    async def request():
        nonlocal calls
        calls += 1
        return response(503 if calls == 1 else 200)

    result = await get_with_retry(request, retries=1, backoff_seconds=10)

    assert result.status_code == 200
    assert calls == 2


@pytest.mark.asyncio
async def test_does_not_retry_non_transient_status():
    calls = 0

    async def request():
        nonlocal calls
        calls += 1
        return response(404)

    with pytest.raises(httpx.HTTPStatusError):
        await get_with_retry(request, retries=2, backoff_seconds=0)

    assert calls == 1
