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


def test_api_key_middleware_is_disabled_without_key():
    from app.middleware import ApiKeyMiddleware

    application = FastAPI()
    application.add_middleware(ApiKeyMiddleware, api_key=None, required=False)

    @application.get("/")
    def root():
        return {"status": "ok"}

    response = TestClient(application).get("/")

    assert response.status_code == 200


def test_api_key_middleware_rejects_missing_or_invalid_key():
    from app.middleware import ApiKeyMiddleware

    application = FastAPI()
    application.add_middleware(ApiKeyMiddleware, api_key="secret", required=True)

    @application.get("/status")
    def status():
        return {"status": "ok"}

    client = TestClient(application)

    assert client.get("/status").status_code == 401
    assert client.get("/status", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/status", headers={"X-API-Key": "secret"}).status_code == 200


def test_api_key_middleware_keeps_public_paths_open():
    from app.middleware import ApiKeyMiddleware

    application = FastAPI()
    application.add_middleware(
        ApiKeyMiddleware,
        api_key="secret",
        required=True,
        excluded_paths={"/health"},
    )

    @application.get("/health")
    def health():
        return {"status": "ok"}

    response = TestClient(application).get("/health")

    assert response.status_code == 200


def test_api_key_middleware_reports_missing_required_configuration():
    from app.middleware import ApiKeyMiddleware

    application = FastAPI()
    application.add_middleware(ApiKeyMiddleware, api_key=None, required=True)

    @application.get("/status")
    def status():
        return {"status": "ok"}

    response = TestClient(application).get("/status")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "api_key_not_configured"
