import re
from typing import Optional

from app.group_directory import infer_groups_for_address


# =========================================================
# DEBUG
# =========================================================

DEBUG = True


# =========================================================
# ✅ ШАБЛОНИ ПО ДАТАХ (ГОЛОВНЕ)
# =========================================================

GROUP_TEMPLATES_BY_DATE = {
    "2026-01-19": {
        "1.1": ["04:00-08:00", "12:00-16:00", "20:00-23:59"],
        "1.2": ["04:00-08:00", "12:00-16:00", "20:00-23:59"],
        "2.1": ["04:00-08:00", "12:00-16:00", "20:00-23:59"],
        "2.2": ["04:00-08:00", "12:00-16:00", "20:00-23:59"],
        "3.1": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
        "3.2": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
        "4.1": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
        "4.2": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
        "5.1": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
        "5.2": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
        "6.1": ["04:00-08:00", "12:00-16:00", "20:00-23:59"],
        "6.2": ["04:00-08:00", "12:00-16:00", "20:00-23:59"],
    }
}


def get_group_template_for_date(date: Optional[str]) -> Optional[dict]:
    if not date:
        return None
    return GROUP_TEMPLATES_BY_DATE.get(date)


# =========================================================
# 🔁 FALLBACK ШАБЛОН (OCR)
# =========================================================

GROUP_TEMPLATE = {
    "1.1": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
    "1.2": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
    "2.1": ["04:00-08:00", "12:00-16:00", "20:00-23:59"],
    "2.2": ["04:00-08:00", "12:00-16:00", "20:00-23:59"],
    "3.1": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
    "3.2": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
    "4.1": ["04:00-08:00", "12:00-16:00", "20:00-23:59"],
    "4.2": ["04:00-08:00", "12:00-16:00", "20:00-23:59"],
    "5.1": ["08:00-12:00", "16:00-20:00"],
    "5.2": ["08:00-12:00", "16:00-20:00"],
    "6.1": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
    "6.2": ["00:00-04:00", "08:00-12:00", "16:00-20:00"],
}


# =========================================================
# REGEX
# =========================================================

TIME_RANGE = re.compile(r"(\d{1,2}:\d{2})\s*по\s*(\d{1,2}:\d{2})")
TIME_PATTERN = re.compile(
    r"(електроенергії немає|електроенергія є)\s+з\s*(\d{1,2}:\d{2})\s*по\s*(\d{1,2}:\d{2})",
    re.IGNORECASE
)

def filter_valid_ranges(active_ranges: list[str]) -> list[str]:
    """
    Прибирає OCR-фантоми типу 03:00-12:00,
    залишає лише інтервали, які реально існують у шаблонах
    """
    if not active_ranges:
        return []

    valid = set()

    # збираємо ВСІ дозволені інтервали з шаблонів
    for template in GROUP_TEMPLATES_BY_DATE.values():
        for ranges in template.values():
            valid.update(ranges)

    cleaned = sorted(r for r in active_ranges if r in valid)

    if DEBUG:
        removed = sorted(set(active_ranges) - set(cleaned))
        if removed:
            print("🧹 REMOVED OCR NOISE:", removed)

    return cleaned



# =========================================================
# 🧠 ВГАДУВАННЯ ШАБЛОНУ ПО ЧАСАХ (З ЛОГАМИ)
# =========================================================

def guess_template_by_ranges(active_ranges: list[str]) -> Optional[tuple[str, dict, float]]:
    best_date = None
    best_template = None
    best_score = 0
    best_total = 0

    for date, template in GROUP_TEMPLATES_BY_DATE.items():
        template_ranges = set()
        for ranges in template.values():
            template_ranges.update(ranges)

        score = len(set(active_ranges) & template_ranges)

        if score > best_score:
            best_score = score
            best_total = len(template_ranges)
            best_date = date
            best_template = template

    if best_score >= 2 and best_total > 0:
        confidence = min(0.95, best_score / best_total)
        return best_date, best_template, confidence

    return None



# =========================================================
# MAIN PARSER
# =========================================================

def parse_power_text(text: str) -> Optional[dict]:
    if not text or not isinstance(text, str):
        return None

    t = text.lower()
    date = extract_date(t)

    planned_outage = parse_planned_outage(text)
    if planned_outage:
        return planned_outage

    # =========================
    # CASE 2: ІДЕАЛЬНИЙ ТЕКСТ (НЕ OCR)
    # =========================
    intervals = []
    for state, start, end in TIME_PATTERN.findall(t):
        intervals.append({
            "from_time": start,
            "to_time": end,
            "status": "OFF" if "немає" in state else "ON"
        })

    if intervals:
        return {
            "type": "HOURLY_SCHEDULE",
            "intervals": intervals,
            "date": date,
            "confidence": 1.0  # текст ≈ 100% довіра
        }

    # =========================
    # 🔥 CASE 3: OCR → ШАБЛОН / GUESS
    # =========================
    if "граф" in t and "по" in t:
        # 1️⃣ витягуємо всі часові діапазони з OCR
        raw_ranges = extract_time_ranges(t)

        # 2️⃣ чистимо OCR-шум (наприклад 03:00-12:00)
        active_ranges = filter_valid_ranges(raw_ranges)

        # 3️⃣ якщо є ТОЧНИЙ шаблон по даті — беремо його
        template = get_group_template_for_date(date)
        if template:
            return {
                "type": "GROUP_SCHEDULE",
                "message": "Графік погодинних відключень",
                "groups": template,
                "date": date,
                "confidence": 0.95
            }

        # 4️⃣ якщо дати нема або вона зламана — ВГАДУЄМО ПО ЧАСАХ
        guessed = guess_template_by_ranges(active_ranges)
        if guessed:
            guessed_date, guessed_template, confidence = guessed
            return {
                "type": "GROUP_SCHEDULE",
                "message": "Графік погодинних відключень",
                "groups": guessed_template,
                "date": date or guessed_date,
                "confidence": round(confidence, 2)
            }

        # 5️⃣ крайній fallback — чисто OCR → групи
        return {
            "type": "GROUP_SCHEDULE",
            "groups": map_times_to_groups(active_ranges),
            "date": date,
            "confidence": 0.4
        }

    return None




# =========================================================
# HELPERS
# =========================================================

def extract_time_ranges(text: str) -> list[str]:
    result = set()
    for s, e in TIME_RANGE.findall(text):
        s, e = fix_time(s), fix_time(e)
        if s and e:
            result.add(f"{s}-{e}")
    return sorted(result)


def parse_planned_outage(text: str) -> Optional[dict]:
    has_outage_text = (
        "припинення електропостачання" in text
        or "буде припинено електропостачання" in text
    )
    if not has_outage_text:
        return None

    date = extract_date(text)
    time_match = re.search(
        r"з\s*(\d{1,2}:\d{2})\s*(?:до|по|-|–|—)\s*(\d{1,2}:\d{2})",
        text,
        re.IGNORECASE,
    )
    if not time_match:
        return None

    start = fix_time(time_match.group(1))
    end = fix_time(time_match.group(2))
    if not start or not end:
        return None

    address = extract_planned_address(text)
    group = extract_planned_group(text)
    interval = {
        "from_time": start,
        "to_time": end,
        "status": "OFF",
    }
    if address:
        interval["address"] = address
        inferred_groups = infer_groups_for_address(address)
        if len(inferred_groups) == 1:
            interval["group"] = inferred_groups[0]
        elif inferred_groups:
            interval["groups"] = inferred_groups
    if group:
        interval["group"] = group

    return {
        "type": "PLANNED_OUTAGE",
        "message": "Тимчасове припинення електропостачання",
        "intervals": [interval],
        "date": date,
        "confidence": 1.0,
    }


def extract_planned_address(text: str) -> Optional[str]:
    match = re.search(
        r"(?:споживачів\s+по|для\s+споживачів)\s+(.+?)(?:⚡|просимо|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None

    address = re.sub(r"\s+", " ", match.group(1)).strip(" .")
    return address or None


def extract_planned_group(text: str) -> Optional[str]:
    match = re.search(
        r"споживачів\s+групи\s+(\d+(?:[.,]\d+)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    return match.group(1).replace(",", ".")


def map_times_to_groups(active_ranges: list[str]) -> dict:
    result = {}
    for g, ranges in GROUP_TEMPLATE.items():
        matched = [r for r in ranges if r in active_ranges]
        if matched:
            result[g] = matched
    return result


def fix_time(t: str) -> Optional[str]:
    try:
        h, m = map(int, t.split(":"))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    except Exception:
        pass
    return None


def extract_date(text: str) -> Optional[str]:
    dotted = re.search(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](20\d{2})\b", text)
    if dotted:
        d, m, y = map(int, dotted.groups())
        if 1 <= d <= 31 and 1 <= m <= 12:
            return f"{y:04d}-{m:02d}-{d:02d}"

    month_names = {
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
    text_date = re.search(
        r"\b(\d{1,2})\s+("
        + "|".join(month_names)
        + r")\s+(20\d{2})\s*(?:р|року)?",
        text,
        re.IGNORECASE,
    )
    if text_date:
        d = int(text_date.group(1))
        m = month_names[text_date.group(2).lower()]
        y = int(text_date.group(3))
        if 1 <= d <= 31:
            return f"{y:04d}-{m:02d}-{d:02d}"

    matches = re.findall(r"(\d{2,4})\s*(202\d)", text)
    for left, year in matches:
        digits = re.sub(r"\D", "", left)[-4:]
        if len(digits) == 4:
            d, m = int(digits[:2]), int(digits[2:])
            if 1 <= d <= 31 and 1 <= m <= 12:
                return f"{year}-{m:02d}-{d:02d}"
    return None
