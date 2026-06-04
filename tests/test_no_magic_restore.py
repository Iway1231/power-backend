from app.ocr import extract_intervals, restore_rows

def test_no_magic_copy_when_both_empty():
    groups = {
        "3.1": [],
        "3.2": []
    }

    restored = restore_rows(groups)

    assert restored["3.1"] == []
    assert restored["3.2"] == []


def test_no_magic_copy_when_one_side_empty():
    groups = {
        "2.1": [],
        "2.2": ["12:00-16:00"],
    }

    restored = restore_rows(groups)

    assert restored["2.1"] == []
    assert restored["2.2"] == ["12:00-16:00"]


def test_extract_intervals_handles_ne_ocr_separator():
    assert extract_intervals("з 08:00 ne 12:00") == ["08:00-12:00"]


def test_extract_intervals_handles_single_early_outage():
    assert extract_intervals("з 6:00 по 8:00") == ["06:00-08:00"]
