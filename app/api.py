# app/api.py

from fastapi import APIRouter
from datetime import datetime
import json
import os
from typing import Dict, List, Optional

from app import config
from app.models import PowerStatus
from app.telegram_html import fetch_latest_posts
from app.image_loader import download_image
from app.group_directory import list_naftogaz_addresses, list_naftogaz_groups
from app.loe_api import (
    LOE_CACHE_TTL_SECONDS,
    available_buildings,
    fetch_loe_accounts,
    fetch_loe_cities,
    fetch_loe_streets,
    get_loe_cache_status,
    find_named_item,
    item_names,
    lookup_loe_address,
)
from app.ocr import extract_schedule_from_image
from app.parser import parse_power_text

router = APIRouter()

FALLBACK_FILE = "last_status.json"
HISTORY_DIR = "history"
os.makedirs(HISTORY_DIR, exist_ok=True)

API_V1_PREFIX = "/api/v1"

GROUP_ORDER = [
    "1.1", "1.2",
    "2.1", "2.2",
    "3.1", "3.2",
    "4.1", "4.2",
    "5.1", "5.2",
    "6.1", "6.2",
]


@router.get("/loe/cities")
async def get_loe_cities():
    cities = await fetch_loe_cities()
    return item_names(cities)


@router.get("/loe/streets")
async def get_loe_streets(city: str):
    cities = await fetch_loe_cities()
    city_item = find_named_item(cities, city)
    if not city_item:
        return {
            "error": "city_not_found",
            "query": city,
            "available": item_names(cities),
        }

    streets = await fetch_loe_streets(city_item["id"])
    return item_names(streets)


@router.get("/loe/buildings")
async def get_loe_buildings(city: str, street: str):
    cities = await fetch_loe_cities()
    city_item = find_named_item(cities, city)
    if not city_item:
        return {
            "error": "city_not_found",
            "query": city,
            "available": item_names(cities),
        }

    streets = await fetch_loe_streets(city_item["id"])
    street_item = find_named_item(streets, street)
    if not street_item:
        return {
            "error": "street_not_found",
            "city": city,
            "query": street,
            "available": item_names(streets),
        }

    accounts = await fetch_loe_accounts(city_item["id"], street_item["id"])
    return available_buildings(accounts)


@router.get("/loe/lookup")
async def get_loe_lookup(city: str, street: str, building: str):
    return await lookup_loe_address(city, street, building, debug=True)


@router.get("/naftogaz/addresses")
def get_naftogaz_addresses(group: Optional[str] = None):
    return list_naftogaz_addresses(group)


@router.get("/operators")
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


@router.get("/naftogaz/groups")
def get_naftogaz_groups():
    return list_naftogaz_groups(GROUP_ORDER)


@router.get("/health")
def get_health():
    return {
        "status": "ok",
        "service": "power-backend",
        "time": datetime.now().isoformat(),
    }


@router.get("/cache/status")
def get_cache_status():
    return {
        "loe": get_loe_cache_status(),
    }


@router.get("/app/config")
def get_app_config():
    return {
        "app": {
            "name": "Power Monitor",
            "api_version": "1",
        },
        "operators": get_operators(),
        "endpoints": {
            "operators": f"{API_V1_PREFIX}/operators",
            "personal_status": f"{API_V1_PREFIX}/my-status",
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


def merge_date(ocr_date: Optional[str], post_date: Optional[str]) -> str:
    if ocr_date:
        return ocr_date
    if post_date:
        return post_date[:10]
    return datetime.now().strftime("%Y-%m-%d")


def is_planned_outage_active(parsed: dict, now: Optional[datetime] = None) -> bool:
    if parsed.get("type") != "PLANNED_OUTAGE":
        return True

    date = parsed.get("date")
    intervals = parsed.get("intervals") or []
    if not date or not intervals:
        return True

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
        return True

    return latest_end >= now


def is_schedule_interval_active(date: Optional[str], interval: str, now: Optional[datetime] = None) -> bool:
    if not date:
        return True

    try:
        to_time = interval.split("-", 1)[1]
        end_at = datetime.fromisoformat(f"{date}T{to_time}:00")
    except (IndexError, ValueError):
        return True

    now = now or datetime.now()
    return end_at >= now


def active_schedule_intervals(date: Optional[str], intervals: List[str], now: Optional[datetime] = None) -> List[str]:
    return [
        interval
        for interval in intervals
        if is_schedule_interval_active(date, interval, now=now)
    ]


def is_group_schedule_active(parsed: dict, now: Optional[datetime] = None) -> bool:
    if parsed.get("type") != "GROUP_SCHEDULE":
        return True

    groups = parsed.get("groups") or {}
    all_outages = []
    for group_status in groups.values():
        all_outages.extend(group_status.get("outages") or [])

    if not all_outages:
        return True

    return bool(active_schedule_intervals(parsed.get("date"), all_outages, now=now))


def build_status_from_ocr(ocr: dict, post_date: Optional[str]) -> Optional[dict]:
    if ocr.get("type") == "NO_OUTAGES":
        date = merge_date(ocr.get("date"), post_date)
        return {
            "type": "DAILY_STATUS",
            "message": "Відключень не заплановано",
            "date": date,
            "confidence": ocr.get("confidence", 0.9),
        }

    raw_groups = ocr.get("groups", {})
    if not raw_groups:
        if not ocr.get("date"):
            return None

        return {
            "type": "DAILY_STATUS",
            "message": "Відключень не заплановано",
            "date": ocr["date"],
            "confidence": ocr.get("confidence", 0.8),
        }

    return {
        "type": "GROUP_SCHEDULE",
        "groups": build_group_state(raw_groups),
        "date": merge_date(ocr.get("date"), post_date),
        "confidence": ocr.get("confidence", 0.8),
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
    parts = [
        f"{label} {loe[key]}"
        for key, label in labels.items()
        if loe.get(key)
    ]
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
    return [
        build_detail(label, loe[key])
        for key, label in labels.items()
        if loe.get(key)
    ]


def build_my_naftogaz_status(status: dict, group: str, now: Optional[datetime] = None) -> dict:
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
        outages = active_schedule_intervals(status.get("date"), group_status.get("outages") or [], now=now)
        has_outage = bool(outages)
        return {
            "operator": "naftogaz",
            "group": group,
            "has_outage": has_outage,
            "status": "OFF" if has_outage else "ON",
            "outages": outages,
            "title": "Зараз є відключення" if has_outage else "Світло має бути",
            "subtitle": f"Група {group}: {', '.join(outages)}" if has_outage else f"Для групи {group} відключень не заплановано",
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
            if naftogaz.get("group") == group:
                matching_intervals.append(interval)
                continue

            for settlement in interval.get("settlements") or []:
                settlement_naftogaz = settlement.get("naftogaz") or {}
                if settlement_naftogaz.get("group") == group:
                    matching_intervals.append(interval)
                    break

        has_outage = bool(matching_intervals)
        return {
            "operator": "naftogaz",
            "group": group,
            "has_outage": has_outage,
            "status": "OFF" if has_outage else "ON",
            "intervals": matching_intervals,
            "title": "Є планове відключення" if has_outage else "Світло має бути",
            "subtitle": f"Для групи {group} знайдено планове відключення" if has_outage else f"Для групи {group} планового відключення не знайдено",
            "details": [
                build_detail("Група", group),
                build_detail("Дата", status.get("date")),
                build_detail("Інтервали", matching_intervals),
            ],
            "message": "Є планове відключення" if has_outage else "Для цієї групи планового відключення не знайдено",
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


@router.get("/status", response_model=PowerStatus)
async def get_power_status():
    posts = await fetch_latest_posts(limit=20)

    for post in reversed(posts):
        parsed_text = parse_power_text(post.get("text", ""))
        if parsed_text:
            if not is_planned_outage_active(parsed_text):
                continue
            return save_status(parsed_text)

        try:
            if not post.get("image"):
                continue

            image_path = await download_image(post["image"])
            ocr = extract_schedule_from_image(image_path)
            if not ocr:
                continue

            parsed_image = build_status_from_ocr(ocr, post.get("published_at"))
            if not parsed_image:
                continue
            if not is_group_schedule_active(parsed_image):
                continue

            return save_status(parsed_image)

        except Exception as e:
            print("❌ OCR ERROR:", e)

    return PowerStatus(
        city=config.CITY_NAME,
        operator=config.OPERATOR,
        type="DAILY_STATUS",
        message="Відключень не заплановано",
        date=datetime.now().strftime("%Y-%m-%d"),
        updatedAt=datetime.now().isoformat(),
        confidence=1.0,
    )


@router.get("/my-status")
async def get_my_status(
    operator: str,
    group: Optional[str] = None,
    city: Optional[str] = None,
    street: Optional[str] = None,
    building: Optional[str] = None,
):
    normalized_operator = operator.lower().strip()

    if normalized_operator in ("naftogaz", "нафтогаз"):
        status = (await get_power_status()).dict()
        if not group:
            return {
                "operator": "naftogaz",
                "has_outage": None,
                "message": "Для Нафтогазу потрібно передати group",
            }
        return build_my_naftogaz_status(status, group)

    if normalized_operator in ("loe", "львівобленерго", "lvivoblenergo"):
        if not city or not street or not building:
            return {
                "operator": "loe",
                "has_outage": None,
                "message": "Для Львівобленерго потрібно передати city, street і building",
            }

        lookup = await lookup_loe_address(city, street, building, debug=True)
        return build_my_loe_status(lookup)

    return {
        "operator": operator,
        "has_outage": None,
        "message": "Підтримуються operator=naftogaz і operator=loe",
    }


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

    with open(FALLBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    return PowerStatus(**status)
