from typing import Any, Optional

import httpx


BASE_URL = "https://power-api.loe.lviv.ua/api"
NOT_INCLUDED_TEXT = "Не входить"


async def fetch_loe_accounts(city_id: int, street_id: int) -> list[dict]:
    params = {
        "pagination": "false",
        "city.id": city_id,
        "street.id": street_id,
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://poweron.loe.lviv.ua/",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{BASE_URL}/pw_accounts", params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

    return data.get("hydra:member", [])


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
