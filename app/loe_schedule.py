"""Current Lvivoblenergo graph retrieval and time based evaluation."""

import re
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from app import config
from app.http_retry import get_with_retry
from app.image_loader import download_image
from app.ocr import extract_schedule_from_image

GRAPH_API_URL = "https://api.loe.lviv.ua/api/menus"
GRAPH_TYPE = "photo-grafic"
_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)")


def local_now(now: Optional[datetime] = None) -> datetime:
    zone = ZoneInfo(config.SETTINGS.timezone)
    if now is None:
        return datetime.now(zone)
    if now.tzinfo is None:
        return now.replace(tzinfo=zone)
    return now.astimezone(zone)


def parse_schedule_date(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", value)
    if iso:
        return "-".join(iso.groups())
    match = _DATE_RE.search(value)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def graph_items(payload: dict) -> list[dict]:
    members = payload.get("hydra:member") if isinstance(payload, dict) else None
    if not isinstance(members, list):
        return []
    for menu in members:
        if isinstance(menu, dict) and menu.get("type") == GRAPH_TYPE:
            items = menu.get("menuItems")
            return (
                [item for item in items if isinstance(item, dict)]
                if isinstance(items, list)
                else []
            )
    return []


def schedule_from_ocr(
    ocr: Optional[dict], item: Optional[dict], now: Optional[datetime] = None
) -> dict:
    """Build a stable schedule object from the official graph item and OCR."""
    item = item or {}
    parsed_date = (
        (ocr or {}).get("date")
        or parse_schedule_date(item.get("description"))
        or parse_schedule_date(item.get("name"))
    )
    groups = (ocr or {}).get("groups") or {}
    normalized_groups = {}
    for group, value in groups.items():
        outages = value.get("outages") if isinstance(value, dict) else value
        if not isinstance(outages, list):
            continue
        normalized_groups[str(group)] = {
            "status": "OFF" if outages else "ON",
            "outages": sorted({str(outage) for outage in outages if isinstance(outage, str)}),
        }
    return {
        "type": "GROUP_SCHEDULE",
        "date": parsed_date,
        "groups": normalized_groups,
        "intervals": [],
        "source_available": bool(ocr and normalized_groups),
        "source": "poweron.loe.lviv.ua",
        "updatedAt": local_now(now).isoformat(),
    }


def schedule_is_current(schedule: dict, now: Optional[datetime] = None) -> bool:
    return schedule.get("date") == local_now(now).date().isoformat() and bool(
        schedule.get("source_available")
    )


def interval_bounds(interval: str) -> Optional[tuple[int, int]]:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", interval or "")
    if not match:
        return None
    sh, sm, eh, em = map(int, match.groups())
    if not (0 <= sh <= 23 and 0 <= eh <= 24 and 0 <= sm <= 59 and 0 <= em <= 59):
        return None
    if eh == 24 and em != 0:
        return None
    start, end = sh * 60 + sm, eh * 60 + em
    return (start, end) if end > start else None


def evaluate_group_schedule(schedule: dict, group: str, now: Optional[datetime] = None) -> dict:
    """Return ON/OFF only for a current, dated official schedule.

    ``outages`` always contains the planned intervals. ``active_intervals``
    contains only the interval covering the current local Kyiv time.
    """
    group_data = (schedule.get("groups") or {}).get(group)
    outages = list(group_data.get("outages") or []) if isinstance(group_data, dict) else []
    result = {"outages": outages, "intervals": outages, "active_intervals": []}
    if not schedule_is_current(schedule, now) or group_data is None:
        return {**result, "status": "UNKNOWN", "has_outage": None}
    minute = local_now(now).hour * 60 + local_now(now).minute
    active = [
        outage
        for outage in outages
        if (bounds := interval_bounds(outage)) and bounds[0] <= minute < bounds[1]
    ]
    result["active_intervals"] = active
    return {**result, "status": "OFF" if active else "ON", "has_outage": bool(active)}


async def fetch_loe_schedule(now: Optional[datetime] = None) -> dict:
    headers = {
        "Accept": "application/ld+json, application/json",
        "Referer": "https://poweron.loe.lviv.ua/",
    }
    async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT_SECONDS) as client:
        response = await get_with_retry(
            lambda: client.get(
                GRAPH_API_URL, params={"page": 1, "type": GRAPH_TYPE}, headers=headers
            ),
            retries=config.SETTINGS.upstream_retry_attempts,
            backoff_seconds=config.SETTINGS.upstream_retry_backoff_seconds,
        )
        payload = response.json()
    items = graph_items(payload)
    current = items[0] if items else None
    image_path = (current or {}).get("imageUrl") or (current or {}).get("slug")
    if not image_path:
        return schedule_from_ocr(None, current, now)
    image_url = (
        image_path if image_path.startswith("http") else f"https://api.loe.lviv.ua{image_path}"
    )
    path = await download_image(image_url)
    try:
        return schedule_from_ocr(extract_schedule_from_image(path), current, now)
    finally:
        import os

        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
