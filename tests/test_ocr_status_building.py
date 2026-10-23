from app.api import build_status_from_ocr


def test_empty_non_schedule_image_is_skipped():
    result = build_status_from_ocr(
        {
            "groups": {},
            "date": None,
            "confidence": 0.6,
        },
        "2026-06-06T08:00:00",
    )

    assert result is None


def test_empty_dated_schedule_is_not_treated_as_no_outages():
    result = build_status_from_ocr(
        {
            "groups": {},
            "date": "2026-06-06",
            "confidence": 0.6,
        },
        None,
    )

    assert result is None


def test_explicit_no_outages_result_keeps_its_own_date():
    result = build_status_from_ocr(
        {
            "type": "NO_OUTAGES",
            "groups": {},
            "date": "2026-06-06",
            "confidence": {"date": 1.0, "groups": 0.9},
        },
        "2026-06-07T08:00:00",
    )

    assert result["type"] == "DAILY_STATUS"
    assert result["date"] == "2026-06-06"


def test_unknown_schedule_date_is_not_replaced_by_publication_date():
    result = build_status_from_ocr(
        {
            "groups": {"1.1": ["11:00-14:00"]},
            "date": None,
            "confidence": {"date": 0.0, "groups": 0.9},
        },
        "2026-06-07T08:00:00",
    )

    assert result["date"] is None
