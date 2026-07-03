import logging
import re
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter

from app import config

WATER_CHANNEL_URL = config.WATER_CHANNEL_URL

router = APIRouter(prefix="/water", tags=["water"])
logger = logging.getLogger(__name__)

MONTHS = {
    "січня": 1,
    "лютого": 2,
    "березня": 3,
    "квітня": 4,
    "травня": 5,
    "червня": 6,
    "липня": 7,
    "серпня": 8,
    "вересня": 9,
    "жовтня": 10,
    "листопада": 11,
    "грудня": 12,
}


async def fetch_water_posts(limit: int = 20) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
        ),
    }
    async with httpx.AsyncClient(
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        headers=headers,
        follow_redirects=True,
    ) as client:
        response = await client.get(WATER_CHANNEL_URL)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    posts = []

    for message in soup.select("div.tgme_widget_message")[:limit]:
        text_element = message.select_one(".tgme_widget_message_text")
        date_element = message.select_one("time[datetime]")
        posts.append(
            {
                "text": text_element.get_text("\n", strip=True) if text_element else "",
                "published_at": date_element["datetime"] if date_element else None,
            }
        )

    return posts


def parse_water_outage(text: str, published_at: Optional[str] = None) -> Optional[dict]:
    if not text or not re.search(
        r"(припинен[оа]\s+водопостачання|без\s+водопостачання|води\s+не\s+буде)",
        text,
        re.IGNORECASE,
    ):
        return None

    date = extract_water_date(text, published_at)
    from_time, to_time = extract_water_times(text)

    if not date or not from_time:
        return None

    return {
        "operator": "Новояворівськводоканал",
        "type": "WATER_OUTAGE",
        "message": "Тимчасове припинення водопостачання",
        "date": date,
        "from_time": from_time,
        "to_time": to_time,
        "locations": extract_water_locations(text),
        "source": "telegram",
        "channel": "vodocanal_nya",
        "confidence": 1.0 if to_time else 0.9,
    }


def extract_water_date(text: str, published_at: Optional[str] = None) -> Optional[str]:
    dotted = re.search(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](20\d{2})\b", text)
    if dotted:
        day, month, year = map(int, dotted.groups())
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None

    named = re.search(
        r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")(?:\s+(20\d{2}))?",
        text,
        re.IGNORECASE,
    )
    if not named:
        return None

    day = int(named.group(1))
    month = MONTHS[named.group(2).lower()]
    year = int(named.group(3)) if named.group(3) else published_year(published_at)
    if not year:
        return None

    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def published_year(published_at: Optional[str]) -> Optional[int]:
    if not published_at:
        return None
    try:
        return datetime.fromisoformat(published_at.replace("Z", "+00:00")).year
    except ValueError:
        return None


def extract_water_times(text: str) -> tuple[Optional[str], Optional[str]]:
    interval = re.search(
        r"(?:з|із)\s*(\d{1,2}:\d{2})\s*(?:до|по|-|–|—)\s*(\d{1,2}:\d{2})",
        text,
        re.IGNORECASE,
    )
    if interval:
        return normalize_time(interval.group(1)), normalize_time(interval.group(2))

    start = re.search(r"(?:з|із)\s*(\d{1,2}:\d{2})", text, re.IGNORECASE)
    restoration = re.search(
        r"(?:час\s+відновлення|відновлення\s+водопостачання).*?(\d{1,2}:\d{2})",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    return (
        normalize_time(start.group(1)) if start else None,
        normalize_time(restoration.group(1)) if restoration else None,
    )


def normalize_time(value: str) -> Optional[str]:
    try:
        hour, minute = map(int, value.split(":"))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    except (AttributeError, ValueError):
        pass
    return None


def extract_water_locations(text: str) -> list[str]:
    blocks = []
    patterns = [
        (
            r"водопостачання\s+у\s+районі\s*(.+?)"
            r"(?=також|орієнтовн|просимо|дякуємо|$)"
        ),
        (
            r"води\s+не\s+буде\s+у:?\s*(.+?)"
            r"(?=також|орієнтовн|просимо|дякуємо|$)"
        ),
        (
            r"без\s+водопостачання\s+залишаться:?\s*(.+?)"
            r"(?=орієнтовн|просимо|дякуємо|$)"
        ),
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            blocks.append(match.group(1))

    locations = []
    for block in blocks:
        cleaned = re.sub(r"[•▪●]", ",", block)
        cleaned = re.sub(r"\s+(?:та|і)\s+", ",", cleaned, flags=re.IGNORECASE)
        for item in re.split(r"[,;\n]+", cleaned):
            location = re.sub(r"\s+", " ", item).strip(" .:-")
            if location and location not in locations:
                locations.append(location)

    return locations


def is_water_outage_active(outage: dict, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    date = outage.get("date")
    to_time = outage.get("to_time") or "23:59"
    try:
        ends_at = datetime.fromisoformat(f"{date}T{to_time}:00")
    except (TypeError, ValueError):
        return True
    return ends_at >= now


@router.get("/status")
async def get_water_status():
    try:
        posts = await fetch_water_posts(limit=20)
    except httpx.HTTPError as exc:
        logger.warning("Water Telegram channel is unavailable: %s", exc)
        return {
            "operator": "Новояворівськводоканал",
            "type": "WATER_STATUS",
            "has_outage": None,
            "message": "Не вдалося оновити повідомлення водоканалу",
            "channel": "vodocanal_nya",
            "source_available": False,
        }

    active_outages = []

    for post in posts:
        outage = parse_water_outage(
            post.get("text", ""),
            post.get("published_at"),
        )
        if outage and is_water_outage_active(outage):
            active_outages.append(outage)

    if active_outages:
        return max(
            active_outages,
            key=lambda item: (item["date"], item["from_time"]),
        )

    return {
        "operator": "Новояворівськводоканал",
        "type": "WATER_STATUS",
        "has_outage": False,
        "message": "Актуальних повідомлень про відключення води немає",
        "channel": "vodocanal_nya",
    }
