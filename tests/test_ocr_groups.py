from app.ocr import extract_schedule_from_image

def test_groups_exist():
    result = extract_schedule_from_image("tests/images/2025-12-25.jpg")

    groups = result["groups"]

    assert "1.1" in groups
    assert "6.2" in groups
    assert isinstance(groups["1.1"], list)
