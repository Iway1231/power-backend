from app.api import build_group_state

def test_status_off_when_outages():
    groups = {
        "1.1": ["08:00-12:00"],
        "1.2": [],
    }

    result = build_group_state(groups)

    assert result["1.1"]["status"] == "OFF"
    assert result["1.2"]["status"] == "ON"
