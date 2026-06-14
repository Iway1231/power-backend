import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator


def load_local_env(path: str = ".env") -> None:
    """Load simple KEY=VALUE entries without overriding process variables."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class Settings(BaseModel):
    app_name: str = "Power Schedule API"
    app_version: str = "1.0.0"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    channel_url: str = "https://t.me/s/nya_merezhi"
    water_channel_url: str = "https://t.me/s/vodocanal_nya"
    city_id: str = "novoyavorivsk"
    city_name: str = "Новояворівськ"
    region: str = "Львівська область"
    operator: str = "Нафтогаз Тепло"
    timezone: str = "Europe/Kyiv"

    status_cache_ttl_seconds: int = Field(default=90, ge=1, le=3600)
    loe_cache_ttl_seconds: int = Field(default=300, ge=1, le=86400)
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    rate_limit_requests: int = Field(default=120, ge=1, le=10000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    cors_origins: list[str] = Field(default_factory=list)
    allowed_hosts: list[str] = Field(default_factory=lambda: ["*"])
    data_dir: Path = Path("data")

    @field_validator("channel_url", "water_channel_url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an absolute HTTP(S) URL")
        return value.rstrip("/")

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z_+-]+(?:/[A-Za-z0-9_+-]+)+|UTC", value):
            raise ValueError("must be an IANA timezone name such as Europe/Kyiv")
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            # Minimal Windows Python installations may not include the IANA
            # database. The production dependencies install tzdata.
            pass
        return value

    @field_validator("data_dir")
    @classmethod
    def normalize_data_dir(cls, value: Path) -> Path:
        return value.expanduser()


def load_settings() -> Settings:
    load_local_env()
    return Settings(
        app_name=os.getenv("APP_NAME", "Power Schedule API"),
        app_version=os.getenv("APP_VERSION", "1.0.0"),
        environment=os.getenv("ENVIRONMENT", "development").lower(),
        debug=_env_bool("DEBUG", False),
        host=os.getenv("HOST", "0.0.0.0"),
        port=os.getenv("PORT", "8000"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        log_format=os.getenv("LOG_FORMAT", "console").lower(),
        channel_url=os.getenv("CHANNEL_URL", "https://t.me/s/nya_merezhi"),
        water_channel_url=os.getenv(
            "WATER_CHANNEL_URL",
            "https://t.me/s/vodocanal_nya",
        ),
        city_id=os.getenv("CITY_ID", "novoyavorivsk"),
        city_name=os.getenv("CITY_NAME", "Новояворівськ"),
        region=os.getenv("REGION", "Львівська область"),
        operator=os.getenv("OPERATOR", "Нафтогаз Тепло"),
        timezone=os.getenv("TIMEZONE", "Europe/Kyiv"),
        status_cache_ttl_seconds=os.getenv("STATUS_CACHE_TTL_SECONDS", "90"),
        loe_cache_ttl_seconds=os.getenv("LOE_CACHE_TTL_SECONDS", "300"),
        request_timeout_seconds=os.getenv("REQUEST_TIMEOUT_SECONDS", "30"),
        rate_limit_requests=os.getenv("RATE_LIMIT_REQUESTS", "120"),
        rate_limit_window_seconds=os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"),
        cors_origins=_env_list("CORS_ORIGINS", ""),
        allowed_hosts=_env_list("ALLOWED_HOSTS", "*"),
        data_dir=Path(os.getenv("DATA_DIR", "data")),
    )


SETTINGS = load_settings()

# Compatibility aliases keep the parsing modules small and stable.
CHANNEL_URL = SETTINGS.channel_url
WATER_CHANNEL_URL = SETTINGS.water_channel_url
CITY_ID = SETTINGS.city_id
CITY_NAME = SETTINGS.city_name
REGION = SETTINGS.region
OPERATOR = SETTINGS.operator
TIMEZONE = SETTINGS.timezone
STATUS_CACHE_TTL_SECONDS = SETTINGS.status_cache_ttl_seconds
LOE_CACHE_TTL_SECONDS = SETTINGS.loe_cache_ttl_seconds
REQUEST_TIMEOUT_SECONDS = SETTINGS.request_timeout_seconds
DATA_DIR = SETTINGS.data_dir

GROUP_ORDER = [
    "1.1", "1.2",
    "2.1", "2.2",
    "3.1", "3.2",
    "4.1", "4.2",
    "5.1", "5.2",
    "6.1", "6.2",
]
