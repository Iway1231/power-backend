from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api import API_V1_PREFIX, router
from app.config import SETTINGS, Settings
from app.errors import register_exception_handlers
from app.logging_config import configure_logging
from app.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.water import router as water_router


OPENAPI_TAGS = [
    {"name": "service", "description": "Service health and runtime metadata."},
    {"name": "outages", "description": "Electricity outage schedules and status."},
    {"name": "addresses", "description": "Address and operator lookup endpoints."},
    {"name": "water", "description": "Water supply interruption notices."},
]


def create_app(settings: Settings = SETTINGS) -> FastAPI:
    configure_logging(settings.log_level, settings.log_format)

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "API for electricity and water outage information in the "
            "Novoyavorivsk community."
        ),
        contact={
            "name": "Power Backend maintainers",
            "url": "https://github.com/Iway1231/power-backend",
        },
        license_info={
            "name": "MIT",
            "identifier": "MIT",
        },
        openapi_tags=OPENAPI_TAGS,
        debug=settings.debug,
    )

    application.add_middleware(GZipMiddleware, minimum_size=1000)
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
    )
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["Accept", "Content-Type", "X-Request-ID"],
        )
    application.add_middleware(
        RateLimitMiddleware,
        requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
        excluded_paths={"/health", f"{API_V1_PREFIX}/health"},
    )
    application.add_middleware(
        SecurityHeadersMiddleware,
        production=settings.environment == "production",
    )
    application.add_middleware(RequestContextMiddleware)

    register_exception_handlers(application)

    @application.get("/", tags=["service"])
    def root():
        return {
            "message": f"{settings.app_name} is running",
            "version": settings.app_version,
            "status_url": f"{API_V1_PREFIX}/status",
            "app_config_url": f"{API_V1_PREFIX}/app/config",
            "docs_url": "/docs",
        }

    application.include_router(router)
    application.include_router(router, prefix=API_V1_PREFIX)
    application.include_router(water_router)
    application.include_router(water_router, prefix=API_V1_PREFIX)
    return application


app = create_app()
