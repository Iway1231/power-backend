"""Read the current hourly outage schedule published by Lvivoblenergo."""

import re
import time
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app import config
from app.http_retry import get_with_retry

SCHEDULE_URL = "https://poweron.loe.lviv.ua/"
GROUP_RE = re.compile(
    r"^Група\s+(?P<group>\d+\.\d+)\.\s+"
    r"Електроенергії\s+(?P<state>є|немає)"
    r"(?:\s+(?P<ranges>.*?))?\.?$",
    re.IGNORECASE,
)
INTERVAL_RE = re.compile(r"з\s+(\d{2}:\d{2})\s+до\s+(\d{2}:\d{2})", re.IGNORECASE)
DATE_RE = re.compile(r"на\s+(\d{2}\.\d{2}\.\d{4})")
UPDATED_RE = re.compile(r"станом\s+на\s+(.+)$", re.IGNORECASE)

_cached_schedule: Optional[dict] = None
_cached_at = 0.0


async def fetch_loe_schedule() -> dict:
    """Fetch and parse the current schedule without performing OCR."""
    global _cached_schedule, _cached_at

    now = time.time()
    if _cached_schedule is not None and now - _cached_at < config.LOE_CACHE_TTL_SECONDS:
        return dict(_cached_schedule)

    async with httpx.AsyncClient(
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        response = await get_with_retry(
            lambda: client.get(SCHEDULE_URL),
            retries=config.SETTINGS.upstream_retry_attempts,
            backoff_seconds=config.SETTINGS.upstream_retry_backoff_seconds,
        )

    schedule = parse_loe_schedule(response.text)
    _cached_schedule = schedule
    _cached_at = now
    return dict(schedule)


def parse_loe_schedule(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    paragraphs = [node.get_text(" ", strip=True) for node in soup.select("p")]
    groups: dict[str, list[str]] = {}
    date = None
    updated_at = None
    image_url = None

    for text in paragraphs:
        if date is None:
            date_match = DATE_RE.search(text)
            if date_match:
                try:
                    date = datetime.strptime(date_match.group(1), "%d.%m.%Y").date().isoformat()
                except ValueError:
                    pass

        if updated_at is None:
            updated_match = UPDATED_RE.search(text)
            if updated_match:
                updated_at = updated_match.group(1)

        match = GROUP_RE.match(text)
        if not match:
            continue
        groups[match.group("group")] = [
            f"{start}-{end}" for start, end in INTERVAL_RE.findall(match.group("ranges") or "")
        ]

    image = soup.select_one('a[href*="/media/"]')
    if image:
        image_url = image.get("href")

    return {
        "source_url": SCHEDULE_URL,
        "image_url": image_url,
        "date": date,
        "updated_at": updated_at,
        "groups": groups,
    }


def clear_loe_schedule_cache() -> None:
    global _cached_schedule, _cached_at
    _cached_schedule = None
    _cached_at = 0.0
