from datetime import datetime

from app.api import is_planned_outage_active


def test_past_planned_outage_is_inactive():
    parsed = {
        "type": "PLANNED_OUTAGE",
        "date": "2026-06-05",
        "intervals": [
            {
                "from_time": "09:00",
                "to_time": "17:00",
                "status": "OFF",
            }
        ],
    }

    assert not is_planned_outage_active(parsed, now=datetime(2026, 6, 6, 13, 45))


def test_future_planned_outage_is_active():
    parsed = {
        "type": "PLANNED_OUTAGE",
        "date": "2026-06-06",
        "intervals": [
            {
                "from_time": "14:00",
                "to_time": "17:00",
                "status": "OFF",
            }
        ],
    }

    assert is_planned_outage_active(parsed, now=datetime(2026, 6, 6, 13, 45))


def test_planned_outage_with_unknown_end_stays_active():
    parsed = {
        "type": "PLANNED_OUTAGE",
        "date": "2026-06-05",
        "intervals": [
            {
                "from_time": "09:00",
                "status": "OFF",
            }
        ],
    }

    assert is_planned_outage_active(parsed, now=datetime(2026, 6, 6, 13, 45))
