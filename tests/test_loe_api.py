from app.loe_api import (
    available_buildings,
    clean_loe_value,
    common_loe_groups,
    find_loe_account,
    find_named_item,
    parse_loe_account,
)


def test_parse_loe_account_groups():
    account = {
        "buildingName": "2-Рђ",
        "chergGpv": "2.2",
        "chergGav": "6",
        "chergAchr": "4 (48.8Р“С†)",
        "chergGvsp": "РќРµ РІС…РѕРґРёС‚СЊ",
        "chergSgav": "РќРµ РІС…РѕРґРёС‚СЊ",
        "disconnectionTask": False,
        "planedReplaceCounter": False,
    }

    assert parse_loe_account(account) == {
        "building": "2-А",
        "loe": {
            "gpv": "2.2",
            "gav": "6",
            "sgav": None,
            "achr": "4 (48.8Гц)",
            "gvsp": None,
        },
        "disconnection_task": False,
        "planned_replace_counter": False,
    }


def test_find_loe_account_by_building():
    accounts = [
        {"buildingName": "3", "chergGpv": "2.2"},
        {"buildingName": "2-Рђ", "chergGpv": "2.2"},
    ]

    result = find_loe_account(accounts, "2-А")

    assert result["building"] == "2-А"
    assert result["loe"]["gpv"] == "2.2"


def test_clean_not_included_value():
    assert clean_loe_value("РќРµ РІС…РѕРґРёС‚СЊ") is None


def test_find_named_item_by_decoded_name():
    items = [
        {"id": 1053, "name": "РЁРєР»Рѕ"},
        {"id": 9999, "name": "РќРѕРІРѕСЏРІРѕСЂС–РІСЃСЊРє"},
    ]

    assert find_named_item(items, "Шкло")["id"] == 1053


def test_available_buildings_ignores_empty_values_and_sorts():
    accounts = [
        {"buildingName": "9", "chergGpv": "2.2"},
        {"buildingName": "", "chergGpv": "2.2"},
        {"buildingName": "6-А", "chergGpv": "2.2"},
        {"buildingName": "4", "chergGpv": "2.2"},
    ]

    assert available_buildings(accounts) == ["4", "6-А", "9"]


def test_common_loe_groups_returns_street_default():
    accounts = [
        {"buildingName": "9", "chergGpv": "2.2", "chergGav": "10"},
        {"buildingName": "", "chergGpv": "2.2", "chergGav": "10"},
    ]

    assert common_loe_groups(accounts) == {
        "gpv": "2.2",
        "gav": "10",
        "sgav": None,
        "achr": None,
        "gvsp": None,
    }
