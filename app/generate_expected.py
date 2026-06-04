from app.ocr import extract_schedule_from_image
import json, os, sys

IMG = sys.argv[1]
OUT = sys.argv[2]

os.makedirs(os.path.dirname(OUT), exist_ok=True)

data = extract_schedule_from_image(IMG)
if not data:
    raise SystemExit("❌ OCR failed")

with open(OUT,"w",encoding="utf-8") as f:
    json.dump(data,f,ensure_ascii=False,indent=2)

print("✅ expected saved:", OUT)
