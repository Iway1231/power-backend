import json
from app.ocr import extract_schedule_from_image

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def test_ocr_2026_01_21():
    result = extract_schedule_from_image("tests/images/2026-01-21.jpg")
    expected = load_json("tests/expected/2026-01-21.json")

    assert result["groups"] == expected["groups"]

