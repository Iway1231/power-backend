import cv2
import pytesseract
import re
from typing import Dict, List


# =========================================================
# CONFIG
# =========================================================

ROWS = 6
COLS = 2

GROUPS = [
    ["1.1", "1.2"],
    ["2.1", "2.2"],
    ["3.1", "3.2"],
    ["4.1", "4.2"],
    ["5.1", "5.2"],
    ["6.1", "6.2"],
]

TIME_RANGE = re.compile(r"(\d{1,2}:\d{2})\s*по\s*(\d{1,2}:\d{2})")


# =========================================================
# MAIN ENTRY
# =========================================================

def extract_schedule_from_image(image_path: str) -> Dict[str, List[str]]:
    """
    🔥 РІЖЕ КАРТИНКУ НА КАРТКИ І OCR КОЖНОЇ
    """
    img = cv2.imread(image_path)
    if img is None:
        return {}

    h, w, _ = img.shape

    # ❗️ОБРІЗАЄМО ШАПКУ (логотип + дата)
    header_cut = int(h * 0.18)
    grid = img[header_cut:h, 0:w]

    gh, gw, _ = grid.shape

    cell_h = gh // ROWS
    cell_w = gw // COLS

    result: Dict[str, List[str]] = {}

    for r in range(ROWS):
        for c in range(COLS):
            y1 = r * cell_h
            y2 = (r + 1) * cell_h
            x1 = c * cell_w
            x2 = (c + 1) * cell_w

            cell = grid[y1:y2, x1:x2]

            group = GROUPS[r][c]
            ranges = ocr_cell_times(cell)

            if ranges:
                result[group] = ranges

    return result


# =========================================================
# OCR ONE CELL
# =========================================================

def ocr_cell_times(cell_img) -> List[str]:
    """
    OCR ОДНІЄЇ КАРТКИ → ЧАСИ
    """
    gray = cv2.cvtColor(cell_img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    _, thresh = cv2.threshold(
        gray, 0, 255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    text = pytesseract.image_to_string(
        thresh,
        lang="ukr",
        config="--psm 6"
    ).lower()

    ranges = []

    for start, end in TIME_RANGE.findall(text):
        ranges.append(f"{fix_time(start)}-{fix_time(end)}")

    return sorted(set(ranges))


# =========================================================
# HELPERS
# =========================================================

def fix_time(t: str) -> str:
    h, m = map(int, t.split(":"))
    return f"{h:02d}:{m:02d}"
