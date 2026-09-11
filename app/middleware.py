import logging
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("app.requests")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started_at = time.perf_counter()

        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, production: bool = False):
        super().__init__(app)
        self.production = production

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
            "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none'"
        )
        if self.production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        api_key: str | None,
        required: bool = False,
        excluded_paths: set[str] | None = None,
    ):
        super().__init__(app)
        self.api_key = api_key
        self.required = required
        self.excluded_paths = excluded_paths or set()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.url.path in self.excluded_paths:
            return await call_next(request)
        if not self.api_key and not self.required:
            return await call_next(request)
        if not self.api_key:
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "api_key_not_configured",
                        "message": "API key protection is enabled but no API key is configured",
                    }
                },
            )

        provided_key = request.headers.get("X-API-Key")
        if not provided_key or not secrets.compare_digest(provided_key, self.api_key):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "invalid_api_key",
                        "message": "A valid X-API-Key header is required",
                    }
                },
                headers={"WWW-Authenticate": "ApiKey"},
            )

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests: int,
        window_seconds: int,
        excluded_paths: set[str] | None = None,
    ):
        super().__init__(app)
        self.requests = requests
        self.window_seconds = window_seconds
        self.excluded_paths = excluded_paths or set()
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        client_host = request.client.host if request.client else "unknown"
        key = f"{client_host}:{request.url.path}"
        now = time.monotonic()

        with self._lock:
            hits = self._hits[key]
            cutoff = now - self.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()

            remaining = max(0, self.requests - len(hits))
            if len(hits) >= self.requests:
                retry_after = max(1, int(self.window_seconds - (now - hits[0])))
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limit_exceeded",
                            "message": "Too many requests",
                        }
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(self.requests),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            hits.append(now)
            remaining = max(0, self.requests - len(hits))

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
