# app/ocr.py

import pytesseract
import cv2
import numpy as np
import re
import os
from typing import Optional, Dict, List

DEBUG = True
DEBUG_DIR = "debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

GROUP_ORDER = [
    "1.1", "1.2",
    "2.1", "2.2",
    "3.1", "3.2",
    "4.1", "4.2",
    "5.1", "5.2",
    "6.1", "6.2",
]

ROWS = [
    ("1.1", "1.2"),
    ("2.1", "2.2"),
    ("3.1", "3.2"),
    ("4.1", "4.2"),
    ("5.1", "5.2"),
    ("6.1", "6.2"),
]

VALID_INTERVALS = {
    "00:00-04:00",
    "04:00-08:00",
    "06:00-08:00",
    "08:00-12:00",
    "12:00-16:00",
    "16:00-20:00",
    "20:00-22:00",
    "20:00-23:59",
}

TIME_SEPARATORS = [
    "\u043f\u043e",  # по
    "\u0448\u043e",  # шо
    "\u0442\u043e",  # то
    "ho",
    "no",
    "mo",
    "ne",
    "zo",
    "-",
    "\u2013",
    "\u2014",
]
TIME_RE = re.compile(
    r"(\d{1,2})[:.,](\d{2})\s*(?:"
    + "|".join(re.escape(separator) for separator in TIME_SEPARATORS)
    + r")\s*(\d{1,2})[:.,](\d{2})"
)



# ======================================================
# PUBLIC ENTRY (API IMPORTS ONLY THIS)
# ======================================================

def extract_schedule_from_image(image_path: str) -> Optional[dict]:
    img = cv2.imread(image_path)
    if img is None:
        return None

    if detect_no_outages(img):
        return {
            "groups": {},
            "date": None,
            "confidence": 0.9,
            "type": "NO_OUTAGES",
        }

    date = extract_date_strict(img)

    tiles = split_tiles(img)
    groups: Dict[str, List[str]] = {}

    for idx, tile in enumerate(tiles):
        group = GROUP_ORDER[idx]
        text = ocr_tile(tile)
        intervals = extract_intervals(text)

        if intervals:
            groups[group] = intervals

        if DEBUG:
            print(f"[OCR] {group}: {intervals}")
            print(f"[TXT] {text}")

    groups = restore_rows(groups)

    return {
        "groups": groups,
        "date": date,
        "confidence": 0.9 if date else 0.6,
    }


def detect_no_outages(img: np.ndarray) -> bool:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    text = pytesseract.image_to_string(gray, lang="ukr+eng", config="--psm 6").lower()
    normalized = re.sub(r"\s+", " ", text)
    return (
        "без стабілізаційних" in normalized
        and "відключень" in normalized
    )


# ======================================================
# DATE
# ======================================================

def extract_date_strict(img: np.ndarray) -> Optional[str]:
    h, w, _ = img.shape
    candidates = []

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (5, 60, 80), (35, 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if 40 < cw < 180 and 10 < ch < 60 and y < h * 0.25:
            crop = img[max(0, y - 3):min(h, y + ch + 3), max(0, x - 3):min(w, x + cw + 3)]
            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            gray_crop = cv2.resize(gray_crop, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
            candidates.append((gray_crop, "--psm 7 -c tessedit_char_whitelist=0123456789."))

    roi = img[int(h * 0.05):int(h * 0.17), int(w * 0.35):int(w * 0.65)]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    candidates.append((thresh, "--psm 7 -c tessedit_char_whitelist=0123456789."))

    wide_roi = img[int(h * 0.04):int(h * 0.14), int(w * 0.20):int(w * 0.75)]
    wide_gray = cv2.cvtColor(wide_roi, cv2.COLOR_BGR2GRAY)
    wide_gray = cv2.resize(wide_gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    candidates.append((wide_gray, "--psm 6"))

    for candidate, config in candidates:
        raw = pytesseract.image_to_string(candidate, lang="eng", config=config)
        match = re.search(r"(\d{1,2})\D+(\d{1,2})\D+(\d{4})", raw)
        if not match:
            continue

        d, m, y = map(int, match.groups())
        if 1 <= d <= 31 and 1 <= m <= 12 and 2020 <= y <= 2030:
            return f"{y:04d}-{m:02d}-{d:02d}"

    return None


# ======================================================
# OCR / TIME
# ======================================================

def ocr_tile(tile: np.ndarray) -> str:
    tile = cv2.resize(tile, None, fx=2, fy=2)
    gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
    raw = pytesseract.image_to_string(gray, lang="ukr+eng", config="--psm 6")
    return raw.lower()


def extract_intervals(text: str) -> List[str]:
    found = set()

    for h1, m1, h2, m2 in TIME_RE.findall(text):
        start = fix_time(h1, m1)
        end = fix_time(h2, m2)
        if start and end:
            interval = f"{start}-{end}"
            if interval in VALID_INTERVALS:
                found.add(interval)

    return sorted(found)


def fix_time(h: str, m: str) -> Optional[str]:
    try:
        h = int(h)
        m = int(m)

        # 🔥 OCR FIXES
        if m in (9, 90):
            m = 0
        if h == 11 and m == 0:
            h = 20

        if 0 <= h <= 23 and m in (0, 59):
            return f"{h:02d}:{m:02d}"
    except:
        pass
    return None


# ======================================================
# GRID
# ======================================================

def split_tiles(img: np.ndarray) -> List[np.ndarray]:
    h, w, _ = img.shape
    grid = img[int(h * 0.17):h, 0:w]
    gh, gw, _ = grid.shape

    tiles = []
    for r in range(6):
        for c in range(2):
            tiles.append(
                grid[
                    r * gh // 6:(r + 1) * gh // 6,
                    c * gw // 2:(c + 1) * gw // 2
                ]
            )
    return tiles


def restore_rows(groups: Dict[str, List[str]]) -> Dict[str, List[str]]:
    out = groups.copy()

    for a, b in ROWS:
        ga = set(out.get(a, []))
        gb = set(out.get(b, []))

        # 🔹 якщо різниця 1 інтервал → OCR шум
        if ga and gb:
            if abs(len(ga) - len(gb)) == 1:
                merged = sorted(ga | gb)
                out[a] = merged
                out[b] = merged

    return out

