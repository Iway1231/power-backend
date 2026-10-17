import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import RateLimitMiddleware
from app.redis_store import RedisStore


@pytest.mark.asyncio
async def test_increment_with_window_uses_redis_atomically(monkeypatch):
    store = RedisStore("redis://unused")

    class FakeClient:
        async def incr(self, key):
            assert key == "power-backend:rate:test"
            return 1

        async def expire(self, key, ttl):
            assert ttl == 60
            return True

        async def ttl(self, key):
            return 60

    async def fake_client_or_none():
        return FakeClient()

    monkeypatch.setattr(store, "_client_or_none", fake_client_or_none)

    assert await store.increment_with_window("rate:test", 60) == (1, 60)


@pytest.mark.asyncio
async def test_increment_with_window_returns_none_when_redis_unavailable(
    monkeypatch,
):
    store = RedisStore(None)

    async def fake_client_or_none():
        return None

    monkeypatch.setattr(store, "_client_or_none", fake_client_or_none)

    assert await store.increment_with_window("rate:test", 60) is None


def test_rate_limit_falls_back_when_redis_unavailable(monkeypatch):
    async def unavailable_increment(self, *args, **kwargs):
        return None

    monkeypatch.setattr(
        RedisStore,
        "increment_with_window",
        unavailable_increment,
    )

    application = FastAPI()
    application.add_middleware(
        RateLimitMiddleware,
        requests=1,
        window_seconds=60,
    )

    @application.get("/")
    def root():
        return {"status": "ok"}

    with TestClient(application) as client:
        response_one = client.get("/")
        response_two = client.get("/")

        assert response_one.status_code == 200
        assert response_two.status_code == 429
        assert response_two.json()["error"]["code"] == "rate_limit_exceeded"
