from app.ocr import extract_intervals, extract_schedule_from_image


def test_extract_intervals_accepts_four_hour_schedule_ranges():
    text = """
    електроенергії немає з 10:00 по 14:00
    електроенергії немає з 14:00 по 18:00
    електроенергії немає з 18:00 по 22:00
    """

    assert extract_intervals(text) == [
        "10:00-14:00",
        "14:00-18:00",
        "18:00-22:00",
    ]


def test_groups_exist():
    result = extract_schedule_from_image("tests/images/2025-12-25.jpg")

    groups = result["groups"]

    assert "1.1" in groups
    assert "6.2" in groups
    assert isinstance(groups["1.1"], list)
