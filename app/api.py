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
from app.loe_api import (
    available_buildings,
    fetch_loe_accounts,
    fetch_loe_cities,
    fetch_loe_streets,
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
