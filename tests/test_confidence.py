from app.ocr import extract_schedule_from_image

def test_confidence_structure():
    result = extract_schedule_from_image("tests/images/2025-12-25.jpg")

    confidence = result["confidence"]

    assert "date" in confidence
    assert "groups" in confidence
    assert 0 <= confidence["groups"] <= 1
