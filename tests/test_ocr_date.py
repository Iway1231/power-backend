from app.ocr import extract_schedule_from_image

def test_date_recognition():
    result = extract_schedule_from_image("tests/images/2025-12-25.jpg")

    assert result is not None
    assert result["date"] == "2025-12-25"
    assert result["confidence"]["date"] == 1.0
