# app/generate_expected_api.py

import json
import os
from datetime import datetime

from app.ocr import extract_schedule_from_image

# =========================
# CONFIG
# =========================

IMAGE = "tests/images/2025-12-25.jpg"
DATE = "2025-12-25"

OUT_DIR = "tests/expected_api"
OUT = f"{OUT_DIR}/{DATE}.json"

GROUP_ORDER = [
    "1.1", "1.2",
    "2.1", "2.2",
    "3.1", "3.2",
    "4.1", "4.2",
    "5.1", "5.2",
    "6.1", "6.2",
]

os.makedirs(OUT_DIR, exist_ok=True)

# =========================
# HELPERS
# =========================

def restore_row_intervals(groups: dict) -> dict:
    """
    ✔ копіює інтервали ТІЛЬКИ якщо одна клітинка порожня
    ❌ не створює нових інтервалів
    """
    restored = {g: list(groups.get(g, [])) for g in GROUP_ORDER}

    rows = [
        ("1.1", "1.2"),
        ("2.1", "2.2"),
        ("3.1", "3.2"),
        ("4.1", "4.2"),
        ("5.1", "5.2"),
        ("6.1", "6.2"),
    ]

    for a, b in rows:
        if restored[a] and not restored[b]:
            restored[b] = restored[a].copy()
        elif restored[b] and not restored[a]:
            restored[a] = restored[b].copy()

    return restored


def add_status(groups: dict) -> dict:
    """
    ON  → outages порожні
    OFF → outages є
    """
    result = {}

    for g, outages in groups.items():
        result[g] = {
            "status": "OFF" if outages else "ON",
            "outages": outages
        }

    return result


# =========================
# RUN
# =========================

ocr = extract_schedule_from_image(IMAGE)

if not ocr or not isinstance(ocr, dict):
    raise RuntimeError("❌ OCR returned nothing")

groups = ocr.get("groups", {})

groups = restore_row_intervals(groups)
groups = add_status(groups)

api_snapshot = {
    "type": "GROUP_SCHEDULE",
    "message": "Графік погодинних відключень",
    "groups": groups,
    "date": DATE,
    "generatedAt": datetime.now().isoformat()
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(api_snapshot, f, ensure_ascii=False, indent=2)

print(f"✅ API SNAPSHOT SAVED → {OUT}")
