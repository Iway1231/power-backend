import copy
import os
import re
import time
from typing import Any, Optional

import httpx


BASE_URL = "https://power-api.loe.lviv.ua/api"
NOT_INCLUDED_TEXT = "Не входить"
LOE_CACHE_TTL_SECONDS = int(os.getenv("LOE_CACHE_TTL_SECONDS", "300"))
_LOE_CACHE: dict[tuple, tuple[float, dict]] = {}


async def fetch_loe_cities(otg_id: Optional[int] = None) -> list[dict]:
    params = {
        "pagination": "false",
    }
    if otg_id is not None:
        params["otg.id"] = otg_id
    data = await fetch_loe_collection("pw_cities", params)
    return data.get("hydra:member", [])


async def fetch_loe_streets(city_id: int) -> list[dict]:
    params = {
        "pagination": "false",
        "city.id": city_id,
    }
    data = await fetch_loe_collection("pw_streets", params)
    return data.get("hydra:member", [])


async def fetch_loe_accounts(city_id: int, street_id: int) -> list[dict]:
    params = {
        "pagination": "false",
        "city.id": city_id,
        "street.id": street_id,
    }
    data = await fetch_loe_collection("pw_accounts", params)
    return data.get("hydra:member", [])


async def fetch_loe_collection(path: str, params: dict) -> dict:
    cached = get_cached_loe_collection(path, params)
    if cached is not None:
        return cached

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://poweron.loe.lviv.ua/",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{BASE_URL}/{path}", params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        set_cached_loe_collection(path, params, data)
        return data


def get_loe_cache_key(path: str, params: dict) -> tuple:
    return path, tuple(sorted((key, str(value)) for key, value in params.items()))


def get_cached_loe_collection(path: str, params: dict, now: Optional[float] = None) -> Optional[dict]:
    key = get_loe_cache_key(path, params)
    cached = _LOE_CACHE.get(key)
    if not cached:
        return None

    cached_at, data = cached
    now = time.time() if now is None else now
    if now - cached_at > LOE_CACHE_TTL_SECONDS:
        _LOE_CACHE.pop(key, None)
        return None

    return copy.deepcopy(data)


def set_cached_loe_collection(path: str, params: dict, data: dict, now: Optional[float] = None) -> None:
    key = get_loe_cache_key(path, params)
    cached_at = time.time() if now is None else now
    _LOE_CACHE[key] = cached_at, copy.deepcopy(data)


def clear_loe_cache() -> None:
    _LOE_CACHE.clear()


def get_loe_cache_status(now: Optional[float] = None) -> dict:
    now = time.time() if now is None else now
    entries = []
    expired_count = 0

    for key, (cached_at, data) in _LOE_CACHE.items():
        age_seconds = max(0, int(now - cached_at))
        expires_in_seconds = max(0, int(LOE_CACHE_TTL_SECONDS - age_seconds))
        if expires_in_seconds == 0 and age_seconds > LOE_CACHE_TTL_SECONDS:
            expired_count += 1

        path, params = key
        entries.append({
            "path": path,
            "params": dict(params),
            "age_seconds": age_seconds,
            "expires_in_seconds": expires_in_seconds,
            "items": len(data.get("hydra:member", [])) if isinstance(data, dict) else None,
        })

    return {
        "ttl_seconds": LOE_CACHE_TTL_SECONDS,
        "entries_count": len(_LOE_CACHE),
        "expired_entries_count": expired_count,
        "entries": entries,
    }


async def lookup_loe_address(
    city_name: str,
    street_name: str,
    building: str,
    otg_id: Optional[int] = None,
    debug: bool = False,
) -> Optional[dict]:
    cities = await fetch_loe_cities(otg_id)
    city = find_named_item(cities, city_name)
    if not city:
        if debug:
            return {
                "error": "city_not_found",
                "query": city_name,
                "available": item_names(cities),
            }
        return None

    streets = await fetch_loe_streets(city["id"])
    street = find_named_item(streets, street_name)
    if not street:
        if debug:
            return {
                "error": "street_not_found",
                "city": decode_mojibake(city.get("name")),
                "query": street_name,
                "available": item_names(streets),
            }
        return None

    accounts = await fetch_loe_accounts(city["id"], street["id"])
    account = find_loe_account(accounts, building)
    if not account:
        if debug:
            return {
                "error": "building_not_found",
                "city": decode_mojibake(city.get("name")),
                "street": decode_mojibake(street.get("name")),
                "query": building,
                "available_buildings": available_buildings(accounts),
                "street_default": common_loe_groups(accounts),
            }
        return None

    account["city"] = decode_mojibake(city.get("name"))
    account["street"] = decode_mojibake(street.get("name"))
    return account


def item_names(items: list[dict]) -> list[str]:
    return [
        decode_mojibake(item.get("name"))
        for item in items
        if item.get("name")
    ]


def available_buildings(accounts: list[dict]) -> list[str]:
    buildings = {
        parsed["building"]
        for parsed in (parse_loe_account(account) for account in accounts)
        if parsed["building"]
    }
    return sorted(buildings, key=building_sort_key)


def common_loe_groups(accounts: list[dict]) -> Optional[dict]:
    groups = [
        parse_loe_account(account)["loe"]
        for account in accounts
    ]
    if not groups:
        return None

    first = groups[0]
    if all(group == first for group in groups):
        return first

    return None


def building_sort_key(value: str) -> tuple[int, str]:
    match = re.match(r"(\d+)", value)
    if match:
        return int(match.group(1)), value
    return 999999, value


def parse_loe_account(account: dict[str, Any]) -> dict:
    return {
        "building": decode_mojibake(account.get("buildingName")) or None,
        "loe": {
            "gpv": clean_loe_value(account.get("chergGpv")),
            "gav": clean_loe_value(account.get("chergGav")),
            "sgav": clean_loe_value(account.get("chergSgav")),
            "achr": clean_loe_value(account.get("chergAchr")),
            "gvsp": clean_loe_value(account.get("chergGvsp")),
        },
        "disconnection_task": bool(account.get("disconnectionTask")),
        "planned_replace_counter": bool(account.get("planedReplaceCounter")),
    }


def find_loe_account(accounts: list[dict], building: str) -> Optional[dict]:
    normalized_building = normalize_building(building)
    for account in accounts:
        if normalize_building(decode_mojibake(account.get("buildingName"))) == normalized_building:
            return parse_loe_account(account)
    return None


def find_named_item(items: list[dict], query: str) -> Optional[dict]:
    normalized_query = normalize_name(query)
    for item in items:
        name = decode_mojibake(item.get("name"))
        if normalize_name(name) == normalized_query:
            return item

    for item in items:
        name = decode_mojibake(item.get("name"))
        if normalized_query in normalize_name(name):
            return item

    return None


def clean_loe_value(value: Any) -> Optional[str]:
    value = decode_mojibake(value)
    if not value:
        return None
    if value.casefold() == NOT_INCLUDED_TEXT.casefold():
        return None
    return value


def decode_mojibake(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)

    try:
        return value.encode("cp1251").decode("utf-8")
    except UnicodeError:
        return value


def normalize_building(value: Any) -> str:
    value = decode_mojibake(value)
    value = value.replace("А", "A").replace("а", "A")
    value = value.replace(" ", "").replace("_", "-").upper()
    return value


def normalize_name(value: Any) -> str:
    value = decode_mojibake(value).casefold()
    value = value.replace("’", "'").replace("`", "'")
    value = value.replace("вулиця", "вул.").replace("село", "с.")
    value = value.replace("смт", "с-ще")
    return " ".join(value.replace(".", " ").split())
