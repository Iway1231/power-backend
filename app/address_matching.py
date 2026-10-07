"""Normalize outage address lists and match them to a saved user address."""

import re
from typing import Optional

from app.group_directory import list_naftogaz_addresses

STREET_RE = re.compile(r"вул\.?\s+([^\n:;]+)", re.IGNORECASE)
BUILDING_RE = re.compile(r"\b(\d+[а-яa-zА-ЯA-Z]?(?:[-/]\d+[а-яa-zА-ЯA-Z]?)?)\b")


def normalize_name(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = value.casefold().replace("’", "'").replace("`", "'")
    normalized = re.sub(r"\b(вулиця|вул)\.?\b", "", normalized)
    normalized = re.sub(r"[^\wА-Яа-яІіЇїЄєҐґ']+", " ", normalized)
    return " ".join(normalized.split())


def normalize_building(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = re.sub(r"\s+", "", value).replace("А", "A").replace("а", "A").upper()
    return re.sub(r"(?<=\d)-(?=[A-Z])", "", normalized)


def _building_values(value: str) -> list[str]:
    return [normalize_building(match) for match in BUILDING_RE.findall(value)]


def _add_target(targets: list[dict], street: str, buildings: list[str] | None = None) -> None:
    street = re.split(r"\s+(?:смт|с-ще)\.?\s+", street, maxsplit=1, flags=re.IGNORECASE)[0]
    street = normalize_name(street)
    if not street:
        return
    values = sorted({item for item in (buildings or []) if item})
    for target in targets:
        if target["street"] == street:
            target["buildings"] = sorted(set(target["buildings"]) | set(values))
            return
    targets.append({"street": street, "buildings": values})


def extract_address_targets(text: str, city: Optional[str] = None) -> list[dict]:
    """Extract street/building targets from Telegram outage text.

    The parser intentionally keeps unknown facilities out of address matching.
    A street without buildings means the whole street is affected.
    """
    if not text:
        return []

    targets: list[dict] = []
    lines = [line.strip(" \t•⚡📍") for line in text.splitlines()]
    current_street = ""

    for line in lines:
        if not line:
            continue
        street_match = re.search(r"(?:^|\s)вул\.?\s+(.+)", line, re.IGNORECASE)
        if not street_match:
            if current_street and re.fullmatch(r"[\d\s,.;:/А-Яа-яA-Za-z-]+", line):
                _add_target(targets, current_street, _building_values(line))
            else:
                current_street = ""
            continue

        body = street_match.group(1).strip(" .;:")
        # Posts often say "вул. Мазепи та вул. Пасічника".
        parts = re.split(r"\s+та\s+вул\.?\s+", body, flags=re.IGNORECASE)
        current_street = ""
        for part in parts:
            part = part.strip(" .;:")
            building_match = re.search(r"[,;:]\s*(\d.*)$", part)
            if building_match:
                street = part[: building_match.start()]
                buildings = _building_values(building_match.group(1))
            else:
                number_match = re.search(
                    r"\s+(\d+[А-Яа-яA-Za-z]?(?:[-/]\d+[А-Яа-яA-Za-z]?)?(?:\s*,.*)?)$", part
                )
                if number_match:
                    street = part[: number_match.start()]
                    buildings = _building_values(number_match.group(1))
                else:
                    street, buildings = part, []
            _add_target(targets, street, buildings)
            if not buildings:
                current_street = street

    result = []
    normalized_city = normalize_name(city)
    for target in targets:
        item = {"street": target["street"], "buildings": target["buildings"]}
        if normalized_city:
            item["city"] = normalized_city
        result.append(item)
    return result


def extract_entity_targets(text: str) -> list[dict]:
    """Extract settlements and residential areas named in an outage post."""
    if not text:
        return []

    normalized_text = normalize_name(text)
    targets: list[dict] = []
    for address in list_naftogaz_addresses():
        if address.get("type") not in {"settlement", "residential_area"}:
            continue
        name = address.get("name") or ""
        if normalize_name(name) not in normalized_text:
            continue
        targets.append({"type": address["type"], "name": name, "group": address["group"]})
    return targets


def address_matches(
    target: dict,
    city: Optional[str],
    street: Optional[str],
    building: Optional[str],
) -> bool:
    """Return true when a parsed target covers a user's selected address."""
    if target.get("city") and normalize_name(target["city"]) != normalize_name(city):
        return False
    if normalize_name(target.get("street")) != normalize_name(street):
        return False
    buildings = {normalize_building(value) for value in target.get("buildings", [])}
    return not buildings or normalize_building(building) in buildings
