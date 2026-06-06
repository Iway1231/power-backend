from datetime import datetime

from app.api import build_group_state, build_my_naftogaz_status, is_group_schedule_active


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


def test_my_naftogaz_status_for_unknown_group():
    result = build_my_naftogaz_status({"type": "DAILY_STATUS"}, "9.9")

    assert result["has_outage"] is None
    assert result["message"] == "Невідома група Нафтогазу"
