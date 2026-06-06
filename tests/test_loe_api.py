from app.loe_api import clean_loe_value, find_loe_account, parse_loe_account


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
