# Power Backend

Backend API for reading electricity outage updates from the Naftogaz Teplo / Novoyavorivsk power channel.

The service fetches recent Telegram posts, parses outage schedules from images and text, and exposes the current result through a FastAPI endpoint.

## What It Parses

- Hourly group outage schedule images.
- Images that say there are no stabilization outages.
- Text posts about temporary planned outages.
- Planned outage posts by address, for example `вул. Курортна смт. Шкло`.
- Planned outage posts by group, for example `споживачів групи 3.2`.
- Text dates such as `05.06.2026` and `19 травня 2026 року`.

## API

Start the server and open:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/status
http://127.0.0.1:8000/docs
```

Main endpoint:

```http
GET /status
```

Example group schedule response:

```json
{
  "city": "Новояворівськ",
  "operator": "Нафтогаз Тепло",
  "type": "GROUP_SCHEDULE",
  "groups": {
    "2.1": {
      "status": "OFF",
      "outages": ["06:00-08:00"]
    }
  },
  "date": "2026-04-11",
  "confidence": 0.9
}
```

Example planned outage response:

```json
{
  "city": "Новояворівськ",
  "operator": "Нафтогаз Тепло",
  "type": "PLANNED_OUTAGE",
  "message": "Тимчасове припинення електропостачання",
  "intervals": [
    {
      "from_time": "10:00",
      "to_time": "16:00",
      "status": "OFF",
      "address": "с. Ліс та с. Окілки",
      "group": "1.2"
    }
  ],
  "date": "2026-05-19",
  "confidence": 1.0
}
```

## Setup

Create and activate a virtual environment:

```powershell
python -m venv venv
venv\Scripts\activate
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Install Tesseract OCR separately and make sure the `tesseract` executable is available in `PATH`.

The OCR logic uses Ukrainian and English trained data:

```text
ukr
eng
```

## Run

```powershell
uvicorn app.main:app --reload
```

## Tests

Run all tests:

```powershell
pytest
```

Run focused tests:

```powershell
pytest tests/test_no_magic_restore.py tests/test_planned_outage_text.py tests/test_group_directory.py -q
```

## Project Notes

- `images/`, `debug/`, `cache/`, `history/`, `data/`, `.vs/`, and `venv/` are local working folders and are ignored by git.
- `app/ocr.py` handles schedule image OCR.
- `app/parser.py` handles text post parsing.
- `app/group_directory.py` maps known addresses and villages to outage groups.
- `app/api.py` combines Telegram fetching, OCR parsing, text parsing, and the `/status` response.

