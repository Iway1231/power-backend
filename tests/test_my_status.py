from datetime import datetime

import pytest

from app.api import (
    build_group_state,
    build_my_loe_status,
    build_my_naftogaz_status,
    get_my_status,
    is_group_schedule_active,
)


def test_my_naftogaz_status_for_group_schedule_outage():
    status = {
        "type": "GROUP_SCHEDULE",
        "groups": build_group_state({"2.1": ["08:00-12:00"]}),
        "date": "2026-06-07",
    }

    result = build_my_naftogaz_status(status, "2.1", now=datetime(2026, 6, 7, 7, 0))

    assert result == {
        "operator": "naftogaz",
        "group": "2.1",
        "has_outage": True,
        "status": "OFF",
        "outages": ["08:00-12:00"],
        "title": "Зараз є відключення",
        "subtitle": "Група 2.1: 08:00-12:00",
        "details": [
            {"label": "Група", "value": "2.1"},
            {"label": "Дата", "value": "2026-06-07"},
            {"label": "Інтервали", "value": ["08:00-12:00"]},
        ],
        "message": "Є відключення",
        "date": "2026-06-07",
        "source_type": "GROUP_SCHEDULE",
    }


def test_my_naftogaz_status_for_group_schedule_without_outage():
    status = {
        "type": "GROUP_SCHEDULE",
        "groups": build_group_state({"2.1": ["08:00-12:00"]}),
        "date": "2026-06-07",
    }

    result = build_my_naftogaz_status(status, "2.2")

    assert result["has_outage"] is False
    assert result["status"] == "ON"
    assert result["outages"] == []
    assert result["title"] == "Світло має бути"


def test_my_naftogaz_status_ignores_expired_group_schedule_interval():
    status = {
        "type": "GROUP_SCHEDULE",
        "groups": build_group_state({"2.1": ["06:00-08:00"]}),
        "date": "2026-04-11",
    }

    result = build_my_naftogaz_status(status, "2.1", now=datetime(2026, 6, 7, 13, 0))

    assert result["has_outage"] is False
    assert result["status"] == "ON"
    assert result["outages"] == []
    assert result["title"] == "Світло має бути"


def test_expired_group_schedule_is_inactive():
    status = {
        "type": "GROUP_SCHEDULE",
        "groups": build_group_state({"2.1": ["06:00-08:00"]}),
        "date": "2026-04-11",
    }

    assert not is_group_schedule_active(status, now=datetime(2026, 6, 7, 13, 0))


def test_my_naftogaz_status_for_planned_outage_group():
    interval = {
        "from_time": "09:00",
        "to_time": "17:00",
        "status": "OFF",
        "address": "вул. Курортна смт. Шкло",
        "naftogaz": {"group": "1.2"},
    }
    status = {
        "type": "PLANNED_OUTAGE",
        "intervals": [interval],
        "date": "2026-06-07",
    }

    result = build_my_naftogaz_status(status, "1.2")

    assert result["has_outage"] is True
    assert result["status"] == "OFF"
    assert result["intervals"] == [interval]
    assert result["title"] == "Є планове відключення"


def test_my_naftogaz_status_for_unknown_group():
    result = build_my_naftogaz_status({"type": "DAILY_STATUS"}, "9.9")

    assert result["has_outage"] is None
    assert result["message"] == "Невідома група Нафтогазу"
    assert result["title"] == "Невідома група"


def test_my_loe_status_returns_address_groups():
    lookup = {
        "city": "Шкло",
        "street": "1-го травня",
        "building": "1",
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

    result = build_my_loe_status(lookup)

    assert result == {
        "operator": "loe",
        "city": "Шкло",
        "street": "1-го травня",
        "building": "1",
        "has_outage": False,
        "status": "UNKNOWN",
        "title": "Групи адреси отримано",
        "subtitle": "ГПВ 2.2, ГАВ 6, АЧР 4 (48.8Гц)",
        "details": [
            {"label": "ГПВ", "value": "2.2"},
            {"label": "ГАВ", "value": "6"},
            {"label": "АЧР", "value": "4 (48.8Гц)"},
        ],
        "message": "Групи адреси отримано",
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


def test_my_loe_status_uses_disconnection_task_as_outage():
    lookup = {
        "city": "Шкло",
        "street": "1-го травня",
        "building": "1",
        "loe": {"gpv": "2.2"},
        "disconnection_task": True,
        "planned_replace_counter": False,
    }

    result = build_my_loe_status(lookup)

    assert result["has_outage"] is True
    assert result["status"] == "OFF"
    assert result["title"] == "Є активне відключення"
    assert result["message"] == "Є активне завдання на відключення"


def test_my_loe_status_returns_lookup_errors():
    result = build_my_loe_status({"error": "building_not_found", "available_buildings": ["1"]})

    assert result["has_outage"] is None
    assert result["error"] == "building_not_found"
    assert result["details"] == []
    assert result["error_details"]["available_buildings"] == ["1"]


@pytest.mark.asyncio
async def test_get_my_status_for_loe(monkeypatch):
    async def fake_lookup_loe_address(city, street, building, debug=False):
        return {
            "city": city,
            "street": street,
            "building": building,
            "loe": {"gpv": "2.2"},
            "disconnection_task": False,
            "planned_replace_counter": False,
        }

    monkeypatch.setattr("app.api.lookup_loe_address", fake_lookup_loe_address)

    result = await get_my_status(
        "loe",
        city="Шкло",
        street="1-го Травня",
        building="1",
    )

    assert result["operator"] == "loe"
    assert result["city"] == "Шкло"
    assert result["loe"] == {"gpv": "2.2"}
