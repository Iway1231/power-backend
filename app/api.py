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


@router.get("/status", response_model=PowerStatus)
async def get_power_status():
    posts = await fetch_latest_posts(limit=20)

    for post in reversed(posts):
        if not post.get("image"):
            continue

        try:
            image_path = await download_image(post["image"])
            ocr = extract_schedule_from_image(image_path)
            if not ocr:
                continue

            groups = build_group_state(ocr.get("groups", {}))
            date = merge_date(ocr.get("date"), post.get("published_at"))

            return save_status({
                "type": "GROUP_SCHEDULE",
                "groups": groups,
                "date": date,
                "confidence": ocr.get("confidence", 0.8),
            })

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
        "groups": parsed["groups"],
        "date": parsed["date"],
        "updatedAt": datetime.now().isoformat(),
        "confidence": parsed.get("confidence", 1.0),
    }

    with open(FALLBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    return PowerStatus(**status)
