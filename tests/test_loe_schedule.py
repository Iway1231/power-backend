from datetime import datetime

from app.loe_schedule import (
    evaluate_group_schedule,
    graph_items,
    interval_bounds,
    parse_schedule_date,
    schedule_from_ocr,
    schedule_is_current,
)


def schedule(date="2026-10-18", outages=None):
    return {
        "type": "GROUP_SCHEDULE",
        "date": date,
        "source_available": True,
        "groups": {"1.1": {"status": "OFF", "outages": outages or ["11:00-12:00"]}},
    }


def test_graph_payload_uses_photo_graph_menu_and_current_item():
    payload = {
        "hydra:member": [
            {"type": "other"},
            {"type": "photo-grafic", "menuItems": [{"name": "Today"}]},
        ]
    }
    assert graph_items(payload) == [{"name": "Today"}]


def test_parse_schedule_date_accepts_iso_and_local_date():
    assert parse_schedule_date("Графік на 18.10.2026") == "2026-10-18"
    assert parse_schedule_date("2026-10-18") == "2026-10-18"
    assert parse_schedule_date("без дати") is None


def test_schedule_from_ocr_keeps_all_groups_and_date():
    result = schedule_from_ocr(
        {
            "date": "2026-10-18",
            "groups": {"1.1": {"outages": ["11:00-12:00"]}, "6.2": {"outages": []}},
        },
        {"name": "Today"},
        now=datetime(2026, 10, 18, 9, 0),
    )
    assert result["date"] == "2026-10-18"
    assert result["groups"]["1.1"]["outages"] == ["11:00-12:00"]
    assert result["groups"]["6.2"]["status"] == "ON"


def test_all_loe_groups_are_supported():
    groups = {
        f"{row}.{part}": {"outages": ["11:00-12:00"]} for row in range(1, 7) for part in (1, 2)
    }
    result = schedule_from_ocr({"date": "2026-10-18", "groups": groups}, {"name": "Today"})
    assert set(result["groups"]) == {f"{row}.{part}" for row in range(1, 7) for part in (1, 2)}


def test_group_state_before_during_and_after_interval():
    value = schedule()
    assert evaluate_group_schedule(value, "1.1", datetime(2026, 10, 18, 10, 59))["status"] == "ON"
    assert evaluate_group_schedule(value, "1.1", datetime(2026, 10, 18, 11, 30))["status"] == "OFF"
    assert evaluate_group_schedule(value, "1.1", datetime(2026, 10, 18, 12, 0))["status"] == "ON"


def test_multiple_intervals_and_empty_schedule():
    value = schedule(outages=["08:00-09:00", "18:00-20:00"])
    result = evaluate_group_schedule(value, "1.1", datetime(2026, 10, 18, 18, 30))
    assert result["outages"] == ["08:00-09:00", "18:00-20:00"]
    assert result["active_intervals"] == ["18:00-20:00"]
    assert (
        evaluate_group_schedule(schedule(outages=[]), "1.1", datetime(2026, 10, 18, 12, 0))[
            "status"
        ]
        == "ON"
    )


def test_missing_stale_or_unknown_group_is_not_confirmed_on():
    assert evaluate_group_schedule({"date": None, "groups": {}}, "1.1")["status"] == "UNKNOWN"
    assert (
        evaluate_group_schedule(schedule(date="2026-10-17"), "1.1", datetime(2026, 10, 18, 12, 0))[
            "status"
        ]
        == "UNKNOWN"
    )
    result = evaluate_group_schedule(schedule(), "2.2", datetime(2026, 10, 18, 12, 0))
    assert result["status"] == "UNKNOWN"
    assert result["has_outage"] is None


def test_interval_validation_and_current_date_timezone():
    assert interval_bounds("11:00-12:00") == (660, 720)
    assert interval_bounds("bad") is None
    assert schedule_is_current(schedule(), datetime(2026, 10, 18, 23, 0))
    assert not schedule_is_current(
        {**schedule(), "source_available": False}, datetime(2026, 10, 18, 23, 0)
    )
