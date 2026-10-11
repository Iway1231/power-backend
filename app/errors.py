import logging

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def error_payload(request: Request, code: str, message: str, details=None) -> dict:
    payload = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        payload["request_id"] = request_id
    return {"error": payload}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(
                request, "validation_error", "Request validation failed", exc.errors()
            ),
        )

    @app.exception_handler(httpx.HTTPError)
    async def upstream_error_handler(
        request: Request,
        exc: httpx.HTTPError,
    ) -> JSONResponse:
        logger.warning("Upstream service request failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content=error_payload(
                request,
                "upstream_unavailable",
                "An upstream data source is temporarily unavailable",
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(request, "http_error", str(exc.detail)),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception("Unhandled application error")
        return JSONResponse(
            status_code=500,
            content=error_payload(request, "internal_server_error", "An unexpected error occurred"),
        )
