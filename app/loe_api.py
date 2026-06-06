import re
from typing import Any, Optional

import httpx


BASE_URL = "https://power-api.loe.lviv.ua/api"
NOT_INCLUDED_TEXT = "Не входить"


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
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://poweron.loe.lviv.ua/",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{BASE_URL}/{path}", params=params, headers=headers)
        response.raise_for_status()
        return response.json()


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
