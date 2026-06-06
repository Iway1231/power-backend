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


def test_empty_dated_schedule_becomes_daily_status():
    result = build_status_from_ocr(
        {
            "groups": {},
            "date": "2026-06-06",
            "confidence": 0.6,
        },
        None,
    )

    assert result == {
        "type": "DAILY_STATUS",
        "message": "Відключень не заплановано",
        "date": "2026-06-06",
        "confidence": 0.6,
    }
