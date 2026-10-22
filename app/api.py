# app/api.py

import asyncio
import json
import logging
import os
import tempfile
import threading
import time
import weakref
from datetime import date, datetime, timedelta
from typing import Annotated, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, HTTPException, Query

from app import config
from app.address_matching import address_matches
from app.config import GROUP_ORDER
from app.group_directory import (
    infer_groups_for_address,
    list_naftogaz_addresses,
    list_naftogaz_groups,
)
from app.image_loader import download_image
from app.loe_api import (
    LOE_CACHE_TTL_SECONDS,
    available_buildings,
    fetch_loe_accounts,
    fetch_loe_cities,
    fetch_loe_streets,
    find_named_item,
    get_loe_cache_status,
    item_names,
    lookup_loe_address,
)
from app.loe_schedule import fetch_loe_schedule, is_loe_schedule_current
from app.models import PowerStatus
from app.ocr import extract_schedule_from_image
from app.parser import parse_power_text
from app.redis_store import RedisStore
from app.telegram_html import fetch_latest_posts
from app.water import get_water_status

logger = logging.getLogger(__name__)

router = APIRouter()
_redis_store = RedisStore(config.SETTINGS.redis_url, config.SETTINGS.redis_key_prefix)

config.DATA_DIR.mkdir(parents=True, exist_ok=True)
FALLBACK_FILE = config.DATA_DIR / "last_status.json"
HISTORY_DIR = config.DATA_DIR / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

API_V1_PREFIX = "/api/v1"

_status_cache: Optional[dict] = None
_status_cache_time: float = 0
_status_locks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_status_locks_guard = threading.Lock()
_ocr_gate = threading.Lock()
STATUS_REFRESH_INTERVAL_SECONDS = 300
STATUS_MAX_AGE_SECONDS = (
    STATUS_REFRESH_INTERVAL_SECONDS + config.SETTINGS.status_refresh_timeout_seconds
)
POWER_SCHEDULE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


class StatusRefreshUnavailable(RuntimeError):
    pass


def is_status_current(status: dict | PowerStatus) -> bool:
    """Return whether a cached status is fresh and schedule-valid."""
    payload = status.model_dump() if isinstance(status, PowerStatus) else status
    return is_status_fresh(payload) and is_planned_outage_active(payload)


def current_status_date(now: Optional[datetime] = None) -> str:
    try:
        timezone = ZoneInfo(config.TIMEZONE)
    except ZoneInfoNotFoundError:
        timezone = None
    current = now or (datetime.now(timezone) if timezone else datetime.now())
    return current.date().isoformat()


def _valid_status_date(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _is_current_dated_status(status: dict | PowerStatus) -> bool:
    payload = status.model_dump() if isinstance(status, PowerStatus) else status
    if _valid_status_date(payload.get("date")) != current_status_date():
        return False
    try:
        PowerStatus(**payload)
    except (TypeError, ValueError):
        return False
    return True


def _is_current_legacy_status(status: dict | PowerStatus) -> bool:
    payload = status.model_dump() if isinstance(status, PowerStatus) else status
    return _valid_status_date(payload.get("date")) == current_status_date() and is_status_current(
        payload
    )


def is_status_fresh(status: dict | PowerStatus, now: Optional[datetime] = None) -> bool:
    payload = status.model_dump() if isinstance(status, PowerStatus) else status
    updated_at = payload.get("updatedAt")
    if not updated_at:
        return False

    try:
        recorded_at = datetime.fromisoformat(updated_at)
    except (TypeError, ValueError):
        return False

    current = now or datetime.now(recorded_at.tzinfo)
    if current.tzinfo is not None and recorded_at.tzinfo is None:
        current = current.replace(tzinfo=None)
    elif current.tzinfo is None and recorded_at.tzinfo is not None:
        recorded_at = recorded_at.replace(tzinfo=None)
    age = (current - recorded_at).total_seconds()
    return 0 <= age <= STATUS_MAX_AGE_SECONDS


def get_status_refresh_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    with _status_locks_guard:
        lock = _status_locks.get(loop)
        if lock is None:
            lock = asyncio.Lock()
            _status_locks[loop] = lock
        return lock


def _remove_ocr_image(image_path: str) -> None:
    try:
        os.unlink(image_path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("Failed to remove OCR image after processing")


def _run_ocr_job(image_path: str) -> Optional[dict]:
    """Run one already-admitted OCR job and own its resource lifecycle."""
    started = time.perf_counter()
    try:
        return extract_schedule_from_image(image_path)
    finally:
        _ocr_gate.release()
        _remove_ocr_image(image_path)
        logger.info("OCR finished in %.3fs", time.perf_counter() - started)


def _consume_ocr_worker_result(worker: asyncio.Task) -> None:
    if worker.cancelled():
        return
    worker.exception()


async def extract_schedule_with_gate(image_path: str) -> Optional[dict]:
    """Run at most one OCR process while keeping cancellation safe.

    The synchronous worker owns the lock and cleanup. If the awaiting
    coroutine is cancelled, the worker still releases both resources only
    after Tesseract and image processing have actually finished.
    """
    if not _ocr_gate.acquire(blocking=False):
        logger.warning("Skipping OCR while another OCR task is running")
        _remove_ocr_image(image_path)
        return None

    try:
        worker = asyncio.create_task(asyncio.to_thread(_run_ocr_job, image_path))
    except BaseException:
        _ocr_gate.release()
        _remove_ocr_image(image_path)
        raise

    worker.add_done_callback(_consume_ocr_worker_result)
    return await asyncio.shield(worker)


@router.get("/loe/cities", tags=["addresses"])
async def get_loe_cities():
    cities = await fetch_loe_cities(config.SETTINGS.loe_otg_id)
    return item_names(cities)


@router.get("/loe/streets", tags=["addresses"])
async def get_loe_streets(
    city: Annotated[str, Query(min_length=1, max_length=120)],
):
    cities = await fetch_loe_cities(config.SETTINGS.loe_otg_id)
    city_item = find_named_item(cities, city)
    if not city_item:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "city_not_found",
                "query": city,
                "available": item_names(cities),
            },
        )

    streets = await fetch_loe_streets(city_item["id"])
    return item_names(streets)


@router.get("/loe/buildings", tags=["addresses"])
async def get_loe_buildings(
    city: Annotated[str, Query(min_length=1, max_length=120)],
    street: Annotated[str, Query(min_length=1, max_length=160)],
):
    cities = await fetch_loe_cities(config.SETTINGS.loe_otg_id)
    city_item = find_named_item(cities, city)
    if not city_item:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "city_not_found",
                "query": city,
                "available": item_names(cities),
            },
        )

    streets = await fetch_loe_streets(city_item["id"])
    street_item = find_named_item(streets, street)
    if not street_item:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "street_not_found",
                "city": city,
                "query": street,
                "available": item_names(streets),
            },
        )

    accounts = await fetch_loe_accounts(city_item["id"], street_item["id"])
    return available_buildings(accounts)


@router.get("/loe/lookup", tags=["addresses"])
async def get_loe_lookup(
    city: Annotated[str, Query(min_length=1, max_length=120)],
    street: Annotated[str, Query(min_length=1, max_length=160)],
    building: Annotated[str, Query(min_length=1, max_length=40)],
):
    return await lookup_loe_address(city, street, building, debug=True)


@router.get("/naftogaz/addresses", tags=["addresses"])
def get_naftogaz_addresses(
    group: Annotated[Optional[str], Query(pattern=r"^[1-6]\.[12]$")] = None,
):
    return list_naftogaz_addresses(group)


@router.get("/operators", tags=["service"])
def get_operators():
    return [
        {
            "id": "naftogaz",
            "name": "Нафтогаз Тепло",
            "status_url": f"{API_V1_PREFIX}/my-status?operator=naftogaz&group={{group}}",
            "selection": "group",
        },
        {
            "id": "loe",
            "name": "Львівобленерго",
            "status_url": f"{API_V1_PREFIX}/my-status?operator=loe&city={{city}}&street={{street}}&building={{building}}",
            "selection": "address",
        },
    ]


@router.get("/naftogaz/groups", tags=["addresses"])
def get_naftogaz_groups():
    return list_naftogaz_groups(GROUP_ORDER)


@router.get("/health", tags=["service"])
def get_health():
    return {
        "status": "ok",
        "service": "power-backend",
        "version": config.SETTINGS.app_version,
        "environment": config.SETTINGS.environment,
        "time": datetime.now().isoformat(),
    }


@router.get("/cache/status", tags=["service"])
def get_cache_status():
    return {
        "loe": get_loe_cache_status(),
    }


@router.get("/app/config", tags=["service"])
def get_app_config():
    return {
        "app": {
            "name": "Power Monitor",
            "api_version": "1",
        },
        "operators": get_operators(),
        "endpoints": {
            "operators": f"{API_V1_PREFIX}/operators",
            "app_bootstrap": f"{API_V1_PREFIX}/app/bootstrap",
            "personal_status": f"{API_V1_PREFIX}/my-status",
            "mobile_home": f"{API_V1_PREFIX}/mobile/home",
            "naftogaz_groups": f"{API_V1_PREFIX}/naftogaz/groups",
            "naftogaz_addresses": f"{API_V1_PREFIX}/naftogaz/addresses",
            "loe_cities": f"{API_V1_PREFIX}/loe/cities",
            "loe_streets": f"{API_V1_PREFIX}/loe/streets",
            "loe_buildings": f"{API_V1_PREFIX}/loe/buildings",
            "loe_lookup": f"{API_V1_PREFIX}/loe/lookup",
            "health": f"{API_V1_PREFIX}/health",
        },
        "cache": {
            "loe_ttl_seconds": LOE_CACHE_TTL_SECONDS,
        },
        "auth": {
            "type": "api_key",
            "header": "X-API-Key",
            "required": config.SETTINGS.api_key_required,
        },
        "network": {
            "timeout_seconds": config.SETTINGS.request_timeout_seconds,
            "retryable_statuses": [429, 502, 503, 504],
        },
    }


@router.get("/app/bootstrap", tags=["service"])
def get_app_bootstrap():
    return {
        "config": get_app_config(),
        "naftogaz_groups": get_naftogaz_groups(),
    }


def build_group_state(groups: Dict[str, List[str]]) -> Dict[str, dict]:
    result = {}
    for g in GROUP_ORDER:
        outages = sorted(set(groups.get(g, [])))
        result[g] = {
            "status": "OFF" if outages else "ON",
            "outages": outages,
        }
    return result


def merge_date(ocr_date: Optional[str], _post_date: Optional[str]) -> Optional[str]:
    return ocr_date if _valid_status_date(ocr_date) is not None else None


def is_planned_outage_active(parsed: dict, now: Optional[datetime] = None) -> bool:
    if parsed.get("type") != "PLANNED_OUTAGE":
        return True

    date = parsed.get("date")
    intervals = parsed.get("intervals") or []
    if _valid_status_date(date) is None or not intervals:
        return False

    now = now or datetime.now()
    latest_end = None

    for interval in intervals:
        to_time = interval.get("to_time")
        if not to_time:
            continue

        try:
            end_at = datetime.fromisoformat(f"{date}T{to_time}:00")
        except ValueError:
            continue

        if latest_end is None or end_at > latest_end:
            latest_end = end_at

    if latest_end is None:
        return False

    return latest_end >= now


def is_schedule_interval_active(
    date: Optional[str], interval: str, now: Optional[datetime] = None
) -> bool:
    if _valid_status_date(date) is None:
        return False

    try:
        to_time = interval.split("-", 1)[1]
        end_at = datetime.fromisoformat(f"{date}T{to_time}:00")
    except (IndexError, ValueError):
        return False

    now = now or datetime.now()
    return end_at >= now


def active_schedule_intervals(
    date: Optional[str], intervals: List[str], now: Optional[datetime] = None
) -> List[str]:
    return [
        interval for interval in intervals if is_schedule_interval_active(date, interval, now=now)
    ]


def is_group_schedule_active(parsed: dict, now: Optional[datetime] = None) -> bool:
    if parsed.get("type") != "GROUP_SCHEDULE":
        return True

    groups = parsed.get("groups") or {}
    all_outages = []
    for group_status in groups.values():
        all_outages.extend(group_status.get("outages") or [])

    if not all_outages:
        return False

    return bool(active_schedule_intervals(parsed.get("date"), all_outages, now=now))


def _overall_confidence(conf) -> float:
    if isinstance(conf, dict):
        values = [v for v in conf.values() if isinstance(v, (int, float))]
        return min(values) if values else 0.8
    if isinstance(conf, (int, float)):
        return float(conf)
    return 0.8


def build_status_from_ocr(ocr: dict, post_date: Optional[str]) -> Optional[dict]:
    if ocr.get("type") == "NO_OUTAGES":
        date = merge_date(ocr.get("date"), post_date)
        return {
            "type": "DAILY_STATUS",
            "message": "Відключень не заплановано",
            "date": date,
            "confidence": _overall_confidence(ocr.get("confidence", 0.9)),
        }

    raw_groups = ocr.get("groups", {})
    if not raw_groups:
        return None

    return {
        "type": "GROUP_SCHEDULE",
        "groups": build_group_state(raw_groups),
        "date": merge_date(ocr.get("date"), post_date),
        "confidence": _overall_confidence(ocr.get("confidence", 0.8)),
    }


def build_detail(label: str, value) -> dict:
    return {
        "label": label,
        "value": value,
    }


def format_loe_subtitle(loe: Optional[dict]) -> str:
    if not loe:
        return "Групи адреси не знайдено"

    labels = {
        "gpv": "ГПВ",
        "gav": "ГАВ",
        "sgav": "СГАВ",
        "achr": "АЧР",
        "gvsp": "ГВСП",
    }
    parts = [f"{label} {loe[key]}" for key, label in labels.items() if loe.get(key)]
    return ", ".join(parts) if parts else "Групи адреси не знайдено"


def build_loe_details(loe: Optional[dict]) -> List[dict]:
    if not loe:
        return []

    labels = {
        "gpv": "ГПВ",
        "gav": "ГАВ",
        "sgav": "СГАВ",
        "achr": "АЧР",
        "gvsp": "ГВСП",
    }
    return [build_detail(label, loe[key]) for key, label in labels.items() if loe.get(key)]


def build_personal_status_error(
    operator: str, message: str, title: str, subtitle: str, details: Optional[List[dict]] = None
) -> dict:
    return {
        "operator": operator,
        "has_outage": None,
        "status": "UNKNOWN",
        "title": title,
        "subtitle": subtitle,
        "details": details or [],
        "message": message,
    }


def infer_status(has_outage) -> str:
    if has_outage is True:
        return "OFF"
    if has_outage is False:
        return "ON"
    return "UNKNOWN"


def build_mobile_section(
    section_id: str,
    label: str,
    status: dict,
    operator: str,
) -> dict:
    has_outage = status.get("has_outage")
    normalized_status = status.get("status") or infer_status(has_outage)
    source_available = status.get("source_available", True)

    return {
        "id": section_id,
        "label": label,
        "operator": operator,
        "has_outage": has_outage,
        "status": normalized_status,
        "title": status.get("title") or status.get("message") or label,
        "subtitle": status.get("subtitle") or status.get("message") or "",
        "details": status.get("details") or [],
        "date": status.get("date"),
        "outages": status.get("outages") or [],
        "intervals": status.get("intervals") or [],
        "active_intervals": status.get("active_intervals") or [],
        "source_available": source_available,
        "source": status,
    }


def build_water_mobile_section(status: dict) -> dict:
    is_outage = status.get("type") == "WATER_OUTAGE"
    has_outage = status.get("has_outage")
    if has_outage is None and "has_outage" not in status:
        has_outage = is_outage

    normalized = {
        **status,
        "has_outage": has_outage,
        "status": infer_status(has_outage),
        "title": (
            "Є відключення води"
            if has_outage is True
            else "Заплановане відключення води"
            if is_outage and has_outage is False
            else "Стан водопостачання уточнюється"
            if is_outage
            else "Вода є"
        ),
        "subtitle": status.get("message") or "",
        "details": [
            build_detail("Дата", status.get("date")),
            build_detail("Початок", status.get("from_time")),
            build_detail("Відновлення", status.get("to_time")),
            build_detail("Адреси", status.get("locations") or []),
        ],
    }
    return build_mobile_section(
        "water",
        "Вода",
        normalized,
        "Новояворівськводоканал",
    )


def build_mobile_home_response(electricity: dict, water: Optional[dict] = None) -> dict:
    electricity_section = build_mobile_section(
        "electricity",
        "Електроенергія",
        electricity,
        electricity.get("operator") or config.OPERATOR,
    )
    sections = [electricity_section]

    if water is not None:
        sections.append(build_water_mobile_section(water))

    if any(section["has_outage"] is True for section in sections):
        overall_status = "OFF"
    elif any(section["has_outage"] is None for section in sections):
        overall_status = "UNKNOWN"
    else:
        overall_status = "ON"

    return {
        "schema_version": "1.0",
        "updated_at": datetime.now().isoformat(),
        "overall_status": overall_status,
        "sections": sections,
        "primary": electricity_section,
    }


def build_my_naftogaz_status(
    status: dict,
    group: str,
    now: Optional[datetime] = None,
    city: Optional[str] = None,
    street: Optional[str] = None,
    building: Optional[str] = None,
) -> dict:
    if group not in GROUP_ORDER:
        return {
            "operator": "naftogaz",
            "group": group,
            "has_outage": None,
            "title": "Невідома група",
            "subtitle": "Перевірте вибрану групу Нафтогазу",
            "details": [build_detail("Група", group)],
            "message": "Невідома група Нафтогазу",
            "source": status,
        }

    if status.get("type") == "GROUP_SCHEDULE":
        group_status = (status.get("groups") or {}).get(group, {})
        outages = active_schedule_intervals(
            status.get("date"), group_status.get("outages") or [], now=now
        )
        has_outage = bool(outages)
        return {
            "operator": "naftogaz",
            "group": group,
            "has_outage": has_outage,
            "status": "OFF" if has_outage else "ON",
            "outages": outages,
            "title": "Зараз є відключення" if has_outage else "Світло має бути",
            "subtitle": f"Група {group}: {', '.join(outages)}"
            if has_outage
            else f"Для групи {group} відключень не заплановано",
            "details": [
                build_detail("Група", group),
                build_detail("Дата", status.get("date")),
                build_detail("Інтервали", outages),
            ],
            "message": "Є відключення" if has_outage else "Відключень не заплановано",
            "date": status.get("date"),
            "source_type": status.get("type"),
        }

    if status.get("type") == "PLANNED_OUTAGE":
        matching_intervals = []
        for interval in status.get("intervals") or []:
            naftogaz = interval.get("naftogaz") or {}
            group_match = naftogaz.get("group") == group or group in (naftogaz.get("groups") or [])
            if not group_match:
                group_match = any(
                    (settlement.get("naftogaz") or {}).get("group") == group
                    for settlement in interval.get("settlements") or []
                )
            address_targets = interval.get("addresses") or []
            if address_targets and city and street and building:
                if any(
                    address_matches(target, city, street, building) for target in address_targets
                ):
                    matching_intervals.append(interval)
                continue
            if group_match:
                matching_intervals.append(interval)

        has_outage = bool(matching_intervals)
        return {
            "operator": "naftogaz",
            "group": group,
            "has_outage": has_outage,
            "status": "OFF" if has_outage else "ON",
            "intervals": matching_intervals,
            "title": "Є планове відключення" if has_outage else "Світло має бути",
            "subtitle": f"Для групи {group} знайдено планове відключення"
            if has_outage
            else f"Для групи {group} планового відключення не знайдено",
            "details": [
                build_detail("Група", group),
                build_detail("Дата", status.get("date")),
                build_detail("Інтервали", matching_intervals),
            ],
            "message": "Є планове відключення"
            if has_outage
            else "Для цієї групи планового відключення не знайдено",
            "date": status.get("date"),
            "source_type": status.get("type"),
        }

    return {
        "operator": "naftogaz",
        "group": group,
        "has_outage": False,
        "status": "ON",
        "outages": [],
        "title": "Світло має бути",
        "subtitle": status.get("message") or "Відключень не заплановано",
        "details": [
            build_detail("Група", group),
            build_detail("Дата", status.get("date")),
        ],
        "message": status.get("message") or "Відключень не заплановано",
        "date": status.get("date"),
        "source_type": status.get("type"),
    }


def build_my_loe_status(lookup: Optional[dict]) -> dict:
    if not lookup:
        return {
            "operator": "loe",
            "has_outage": None,
            "title": "Адресу не знайдено",
            "subtitle": "Перевірте населений пункт, вулицю і будинок",
            "details": [],
            "message": "Адресу Львівобленерго не знайдено",
        }

    if lookup.get("error"):
        return {
            "operator": "loe",
            "has_outage": None,
            "title": "Адресу не знайдено",
            "subtitle": "Перевірте населений пункт, вулицю і будинок",
            "details": [],
            "message": "Адресу Львівобленерго не знайдено",
            "error": lookup.get("error"),
            "error_details": lookup,
        }

    has_outage = bool(lookup.get("disconnection_task"))
    loe = lookup.get("loe")
    return {
        "operator": "loe",
        "city": lookup.get("city"),
        "street": lookup.get("street"),
        "building": lookup.get("building"),
        "has_outage": has_outage,
        "status": "OFF" if has_outage else "UNKNOWN",
        "title": "Є активне відключення" if has_outage else "Групи адреси отримано",
        "subtitle": format_loe_subtitle(loe),
        "details": build_loe_details(loe),
        "message": "Є активне завдання на відключення" if has_outage else "Групи адреси отримано",
        "loe": loe,
        "disconnection_task": lookup.get("disconnection_task"),
        "planned_replace_counter": lookup.get("planned_replace_counter"),
    }


def apply_loe_schedule(status: dict, schedule: dict, now: Optional[datetime] = None) -> dict:
    """Add the official LOE group schedule while preserving address status."""
    group = (status.get("loe") or {}).get("gpv")
    schedule_groups = schedule.get("groups") or {}
    group_found = bool(group and isinstance(schedule_groups, dict) and group in schedule_groups)
    schedule_current = is_loe_schedule_current(schedule.get("date"), now=now)
    schedule_usable = schedule_current and group_found
    planned_intervals = schedule_groups.get(group, []) if group_found else []
    active_intervals = [
        interval
        for interval in planned_intervals
        if schedule_usable and is_loe_interval_active(schedule.get("date"), interval, now=now)
    ]
    emergency_outage = status.get("has_outage") is True
    if emergency_outage:
        has_outage = True
        current_status = "OFF"
        title = status.get("title") or "Є активне відключення"
    elif schedule_usable:
        has_outage = bool(active_intervals)
        current_status = "OFF" if has_outage else "ON"
        title = "Зараз є відключення" if has_outage else "Світло має бути"
    else:
        has_outage = None
        current_status = "UNKNOWN"
        title = "Графік не підтверджено"

    status = dict(status)
    status.update(
        {
            "has_outage": has_outage,
            "status": current_status,
            "title": title,
            "subtitle": (
                f"Група {group}: {', '.join(active_intervals if has_outage else planned_intervals)}"
                if group and (active_intervals if has_outage else planned_intervals)
                else status.get("subtitle") or "Для групи графік не знайдено"
            ),
            "date": schedule.get("date"),
            "outages": planned_intervals,
            "intervals": planned_intervals,
            "active_intervals": active_intervals,
            "schedule_source": schedule.get("source_url"),
            "schedule_updated_at": schedule.get("updated_at"),
        }
    )
    return status


def is_loe_interval_active(
    date: Optional[str], interval: str, now: Optional[datetime] = None
) -> bool:
    """Return whether an LOE interval is active in the Kyiv local timezone."""
    if not date or "-" not in interval:
        return False

    try:
        start_text, end_text = interval.split("-", 1)
        start_at = datetime.fromisoformat(f"{date}T{start_text}:00")
        end_at = datetime.fromisoformat(f"{date}T{end_text}:00")
    except (TypeError, ValueError):
        return False

    if end_at <= start_at:
        end_at += timedelta(days=1)

    try:
        timezone = ZoneInfo(config.TIMEZONE)
    except ZoneInfoNotFoundError:
        timezone = None

    current = now or (datetime.now(timezone) if timezone else datetime.now())
    if timezone:
        start_at = start_at.replace(tzinfo=timezone)
        end_at = end_at.replace(tzinfo=timezone)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone)
        else:
            current = current.astimezone(timezone)
    elif current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    return start_at <= current < end_at


@router.get("/status", response_model=PowerStatus, tags=["outages"])
async def get_power_status():
    cached = await get_cached_power_status()
    if cached is not None:
        return cached
    raise HTTPException(
        status_code=503,
        detail="Power status is temporarily unavailable",
    )


async def get_cached_power_status() -> Optional[PowerStatus]:
    if _status_cache and _is_current_legacy_status(_status_cache):
        return PowerStatus(**_status_cache)

    dated = await load_dated_status(current_status_date())
    if dated is not None and _is_current_dated_status(dated):
        return dated

    cached = await _redis_store.get_json("status:power")
    if isinstance(cached, dict) and _is_current_legacy_status(cached):
        return PowerStatus(**cached)
    fallback = load_fallback_status()
    if fallback is not None and _is_current_legacy_status(fallback):
        return fallback
    return None


async def refresh_power_status_once() -> bool:
    """Refresh electricity status without making API callers wait for it."""
    lock = get_status_refresh_lock()
    if lock.locked():
        logger.info("Skipping power refresh while another refresh is running")
        return False

    await lock.acquire()
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            _fetch_power_status(),
            timeout=config.SETTINGS.status_refresh_timeout_seconds,
        )
        result_payload = result.model_dump() if isinstance(result, PowerStatus) else result
        if isinstance(result_payload, dict) and result_payload.get("date") == current_status_date():
            _save_legacy_status(result_payload)
            try:
                await _redis_store.set_json(
                    "status:power", result_payload, config.STATUS_CACHE_TTL_SECONDS
                )
            except Exception:
                logger.warning(
                    "Power status saved locally but Redis persistence failed",
                    exc_info=True,
                )
        logger.info("Power status refresh finished in %.3fs", time.perf_counter() - started)
        return True
    except (httpx.HTTPError, asyncio.TimeoutError, StatusRefreshUnavailable) as exc:
        logger.warning(
            "Power status refresh failed after %.3fs: %s",
            time.perf_counter() - started,
            exc,
        )
        return False
    finally:
        lock.release()


async def run_background_refresh_loop(
    stop_event: asyncio.Event,
    interval_seconds: float = STATUS_REFRESH_INTERVAL_SECONDS,
) -> None:
    """Refresh electricity and water independently, starting immediately."""
    from app.water import refresh_water_status_once

    async def run_refresh_worker(refresh, name: str, timeout: Optional[float] = None):
        next_run = time.monotonic()
        while not stop_event.is_set():
            try:
                if timeout is None:
                    await refresh()
                else:
                    await asyncio.wait_for(refresh(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("Background %s refresh timed out", name)
            except Exception:
                logger.exception("Background %s refresh failed", name)

            next_run += interval_seconds
            delay = max(0, next_run - time.monotonic())
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                continue

    power_task = asyncio.create_task(run_refresh_worker(refresh_power_status_once, "power"))
    water_task = asyncio.create_task(
        run_refresh_worker(
            refresh_water_status_once,
            "water",
            timeout=config.SETTINGS.status_refresh_timeout_seconds,
        )
    )
    try:
        await asyncio.gather(power_task, water_task)
    finally:
        for task in (power_task, water_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(power_task, water_task, return_exceptions=True)


def build_daily_status() -> PowerStatus:
    return PowerStatus(
        city=config.CITY_NAME,
        operator=config.OPERATOR,
        type="DAILY_STATUS",
        message="Відключень не заплановано",
        date=datetime.now().strftime("%Y-%m-%d"),
        updatedAt=datetime.now().isoformat(),
        confidence=1.0,
    )


def load_fallback_status() -> Optional[PowerStatus]:
    try:
        with FALLBACK_FILE.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return PowerStatus(**payload)
    except (OSError, TypeError, ValueError):
        return None


def _dated_status_file(status_date: str):
    return HISTORY_DIR / f"{status_date}.json"


def _status_record_payload(parsed: dict, published_at: Optional[str]) -> dict:
    status = {
        "city": config.CITY_NAME,
        "operator": config.OPERATOR,
        "type": parsed["type"],
        "message": parsed.get("message"),
        "groups": parsed.get("groups"),
        "intervals": parsed.get("intervals"),
        "date": parsed["date"],
        "updatedAt": datetime.now().isoformat(),
        "confidence": parsed.get("confidence", 1.0),
    }
    return {"status": status, "published_at": published_at}


def _published_timestamp(value: object) -> Optional[float]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def _should_replace_publication(
    existing_published_at: object, candidate_published_at: object
) -> bool:
    existing_timestamp = _published_timestamp(existing_published_at)
    candidate_timestamp = _published_timestamp(candidate_published_at)
    if existing_timestamp is None:
        return candidate_timestamp is not None
    if candidate_timestamp is None:
        return False
    return candidate_timestamp > existing_timestamp


def _record_status(record: object, expected_date: Optional[str] = None) -> Optional[dict]:
    if not isinstance(record, dict):
        return None
    payload = record.get("status", record)
    if not isinstance(payload, dict):
        return None
    record_date = _valid_status_date(payload.get("date"))
    if record_date is None or (expected_date is not None and record_date != expected_date):
        return None
    return payload


async def load_dated_record(status_date: str) -> Optional[dict]:
    try:
        with _dated_status_file(status_date).open("r", encoding="utf-8") as file:
            record = json.load(file)
    except (OSError, TypeError, ValueError):
        record = None
    if _record_status(record, status_date) is not None:
        return record

    record = await _redis_store.get_json(f"status:power:{status_date}")
    return record if _record_status(record, status_date) is not None else None


async def load_dated_status(status_date: str) -> Optional[PowerStatus]:
    record = await load_dated_record(status_date)
    payload = _record_status(record, status_date)
    if payload is None:
        return None
    try:
        return PowerStatus(**payload)
    except (TypeError, ValueError):
        return None


def _write_dated_record(status_date: str, record: dict) -> bool:
    target = _dated_status_file(status_date)
    tmp_path = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=config.DATA_DIR,
            prefix="status-",
            suffix=".json",
        )
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, target)
        return True
    except OSError:
        try:
            with target.open("w", encoding="utf-8") as file:
                json.dump(record, file, ensure_ascii=False, indent=2)
            return True
        except OSError:
            logger.warning("Failed to persist dated status to %s", target)
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False


async def save_dated_status(parsed: dict, published_at: Optional[str]) -> bool:
    status_date = _valid_status_date(parsed.get("date"))
    if status_date is None:
        return False

    candidate = _status_record_payload(parsed, published_at)
    existing = await load_dated_record(status_date)
    if existing is not None and not _should_replace_publication(
        existing.get("published_at"), published_at
    ):
        return False

    if not _write_dated_record(status_date, candidate):
        return False
    try:
        await _redis_store.set_json(
            f"status:power:{status_date}",
            candidate,
            POWER_SCHEDULE_CACHE_TTL_SECONDS,
        )
    except Exception:
        logger.warning(
            "Dated status saved to file but Redis persistence failed for %s",
            status_date,
            exc_info=True,
        )
    return True


async def _fetch_power_status():
    started = time.perf_counter()
    posts = await fetch_latest_posts(limit=20)
    logger.info(
        "Fetched %d Telegram posts in %.3fs",
        len(posts),
        time.perf_counter() - started,
    )
    candidates: dict[str, tuple[dict, Optional[str]]] = {}
    seen_images: set[str] = set()

    for post in reversed(posts):
        parsed_text = parse_power_text(post.get("text", ""))
        if parsed_text:
            if not is_planned_outage_active(parsed_text):
                continue
            published_at = post.get("published_at")
            parsed_text = dict(parsed_text)
            status_date = _valid_status_date(parsed_text.get("date"))
            if status_date is not None:
                previous = candidates.get(status_date)
                if previous is None or _should_replace_publication(previous[1], published_at):
                    candidates[status_date] = (parsed_text, published_at)
            continue

        try:
            if not post.get("image"):
                continue
            if post["image"] in seen_images:
                continue
            seen_images.add(post["image"])

            download_started = time.perf_counter()
            image_path = await download_image(post["image"])
            logger.info(
                "Downloaded Telegram image in %.3fs",
                time.perf_counter() - download_started,
            )
            ocr = await extract_schedule_with_gate(image_path)
            if not ocr:
                continue

            parsed_image = build_status_from_ocr(ocr, post.get("published_at"))
            if not parsed_image:
                continue
            if not is_group_schedule_active(parsed_image):
                continue

            status_date = _valid_status_date(parsed_image.get("date"))
            if status_date is not None:
                published_at = post.get("published_at")
                previous = candidates.get(status_date)
                if previous is None or _should_replace_publication(previous[1], published_at):
                    candidates[status_date] = (parsed_image, published_at)

        except Exception as e:
            logger.error("OCR error: %s", e, exc_info=True)

    if not candidates:
        raise StatusRefreshUnavailable("No valid dated status was produced by the upstream source")

    for parsed, published_at in candidates.values():
        await save_dated_status(parsed, published_at)

    current = await load_dated_status(current_status_date())
    if current is not None and _is_current_dated_status(current):
        return current
    newest = next(iter(candidates.values()))
    for candidate in candidates.values():
        if _should_replace_publication(newest[1], candidate[1]):
            newest = candidate
    newest_parsed, newest_published_at = newest
    return _status_record_payload(newest_parsed, newest_published_at)["status"]


@router.get("/my-status", tags=["outages"])
async def get_my_status(
    operator: Annotated[str, Query(min_length=2, max_length=40)],
    group: Annotated[Optional[str], Query(max_length=10)] = None,
    city: Annotated[Optional[str], Query(max_length=120)] = None,
    street: Annotated[Optional[str], Query(max_length=160)] = None,
    building: Annotated[Optional[str], Query(max_length=40)] = None,
):
    normalized_operator = operator.lower().strip()

    if normalized_operator in ("naftogaz", "нафтогаз"):
        status = (await get_power_status()).dict()
        if not group and city and street and building:
            inferred_groups = infer_groups_for_address(f"{city} {street} {building}")
            if len(inferred_groups) == 1:
                group = inferred_groups[0]
        if not group:
            return build_personal_status_error(
                "naftogaz",
                "Для Нафтогазу потрібно передати group",
                "Не вибрано групу",
                "Оберіть групу Нафтогазу для перевірки статусу",
            )
        return build_my_naftogaz_status(status, group, city=city, street=street, building=building)

    if normalized_operator in ("loe", "львівобленерго", "lvivoblenergo"):
        if not city or not street or not building:
            return build_personal_status_error(
                "loe",
                "Для Львівобленерго потрібно передати city, street і building",
                "Не вибрано адресу",
                "Оберіть населений пункт, вулицю і будинок",
                [
                    build_detail("Населений пункт", city),
                    build_detail("Вулиця", street),
                    build_detail("Будинок", building),
                ],
            )

        lookup = await lookup_loe_address(city, street, building, debug=True)
        status = build_my_loe_status(lookup)
        if lookup and not lookup.get("error"):
            try:
                status = apply_loe_schedule(status, await fetch_loe_schedule())
            except (httpx.HTTPError, asyncio.TimeoutError) as exc:
                logger.warning("LOE schedule unavailable: %s", exc)
        return status

    return build_personal_status_error(
        operator,
        "Підтримуються operator=naftogaz і operator=loe",
        "Невідомий оператор",
        "Оберіть Нафтогаз Тепло або Львівобленерго",
        [build_detail("Оператор", operator)],
    )


@router.get("/mobile/home", tags=["outages"])
async def get_mobile_home(
    operator: Annotated[str, Query(min_length=2, max_length=40)] = "naftogaz",
    group: Annotated[Optional[str], Query(max_length=10)] = None,
    city: Annotated[Optional[str], Query(max_length=120)] = None,
    street: Annotated[Optional[str], Query(max_length=160)] = None,
    building: Annotated[Optional[str], Query(max_length=40)] = None,
    include_water: bool = True,
):
    electricity = await get_my_status(
        operator=operator,
        group=group,
        city=city,
        street=street,
        building=building,
    )
    water = await get_water_status() if include_water else None
    return build_mobile_home_response(electricity, water)


def save_status(parsed: dict) -> PowerStatus:
    status = {
        "city": config.CITY_NAME,
        "operator": config.OPERATOR,
        "type": parsed["type"],
        "message": parsed.get("message"),
        "groups": parsed.get("groups"),
        "intervals": parsed.get("intervals"),
        "date": parsed["date"],
        "updatedAt": datetime.now().isoformat(),
        "confidence": parsed.get("confidence", 1.0),
    }
    _save_legacy_status(status)
    return PowerStatus(**status)


def _save_legacy_status(status: dict) -> None:
    global _status_cache, _status_cache_time

    _status_cache = status
    _status_cache_time = time.time()

    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=config.DATA_DIR,
            prefix="status-",
            suffix=".json",
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, FALLBACK_FILE)
    except OSError:
        logger.warning("Failed to persist status to %s", FALLBACK_FILE)
