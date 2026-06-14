from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import RateLimitMiddleware, SecurityHeadersMiddleware


def test_security_headers_are_added():
    application = FastAPI()
    application.add_middleware(SecurityHeadersMiddleware, production=True)

    @application.get("/")
    def root():
        return {"status": "ok"}

    response = TestClient(application).get("/")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "max-age=31536000" in response.headers["strict-transport-security"]


def test_rate_limit_returns_429():
    application = FastAPI()
    application.add_middleware(
        RateLimitMiddleware,
        requests=1,
        window_seconds=60,
    )

    @application.get("/")
    def root():
        return {"status": "ok"}

    client = TestClient(application)
    assert client.get("/").status_code == 200

    response = client.get("/")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    assert response.headers["retry-after"]
