from app.ocr import restore_rows

def test_no_magic_copy_when_both_empty():
    groups = {
        "3.1": [],
        "3.2": []
    }

    restored = restore_rows(groups)

    assert restored["3.1"] == []
    assert restored["3.2"] == []
