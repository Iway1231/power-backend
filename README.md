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
GET /api/v1/status
```

Legacy unversioned routes such as `/status` still work, but Android should prefer `/api/v1/...` routes.

Lvivoblenergo address lookup endpoints for app dropdowns:

```http
GET /api/v1/loe/cities
GET /api/v1/loe/streets?city=Шкло
GET /api/v1/loe/buildings?city=Шкло&street=1-го%20Травня
GET /api/v1/loe/lookup?city=Шкло&street=1-го%20Травня&building=1
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
      "settlements": [
        {
          "name": "с. Ліс",
          "naftogaz": {
            "group": "1.2"
          }
        },
        {
          "name": "с. Окілки",
          "naftogaz": {
            "group": "1.2"
          }
        }
      ],
      "naftogaz": {
        "group": "1.2"
      }
    }
  ],
  "date": "2026-05-19",
  "confidence": 1.0
}
```

## Android App Flow

Use this sequence when building the Android app.

### 1. Load App Config

```http
GET /api/v1/app/config
```

This returns the API version, supported operators, endpoint paths, and cache settings. Android should call this once at startup and then use the returned `endpoints` values.

### 2. Load Operators

```http
GET /api/v1/operators
```

Example:

```json
[
  {
    "id": "naftogaz",
    "name": "Нафтогаз Тепло",
    "status_url": "/api/v1/my-status?operator=naftogaz&group={group}",
    "selection": "group"
  },
  {
    "id": "loe",
    "name": "Львівобленерго",
    "status_url": "/api/v1/my-status?operator=loe&city={city}&street={street}&building={building}",
    "selection": "address"
  }
]
```

If `selection` is `group`, show Naftogaz groups. If `selection` is `address`, show city, street, and building dropdowns.

### 3. Naftogaz User Setup

Load available Naftogaz groups and their address hints:

```http
GET /api/v1/naftogaz/groups
```

Example group item:

```json
{
  "id": "2.1",
  "name": "Група 2.1",
  "addresses": [
    {
      "group": "2.1",
      "type": "street",
      "city": "Новояворівськ",
      "name": "Січових Стрільців",
      "buildings": ["1", "2", "4", "6"]
    }
  ]
}
```

Save the selected group locally in the Android app.

Check personal status:

```http
GET /api/v1/my-status?operator=naftogaz&group=2.1
```

Example:

```json
{
  "operator": "naftogaz",
  "group": "2.1",
  "has_outage": false,
  "status": "ON",
  "title": "Світло має бути",
  "subtitle": "Для групи 2.1 відключень не заплановано",
  "details": [
    {"label": "Група", "value": "2.1"},
    {"label": "Дата", "value": "2026-06-07"},
    {"label": "Інтервали", "value": []}
  ]
}
```

### 4. Lvivoblenergo User Setup

Load cities:

```http
GET /api/v1/loe/cities
```

Load streets after city selection:

```http
GET /api/v1/loe/streets?city=Шкло
```

Load buildings after street selection:

```http
GET /api/v1/loe/buildings?city=Шкло&street=1-го%20Травня
```

Save `city`, `street`, and `building` locally in the Android app.

Check personal status:

```http
GET /api/v1/my-status?operator=loe&city=Шкло&street=1-го%20Травня&building=1
```

Example:

```json
{
  "operator": "loe",
  "city": "Шкло",
  "street": "1-го травня",
  "building": "1",
  "has_outage": false,
  "status": "UNKNOWN",
  "title": "Групи адреси отримано",
  "subtitle": "ГПВ 2.2, ГАВ 6, АЧР 4 (48.8Гц)",
  "details": [
    {"label": "ГПВ", "value": "2.2"},
    {"label": "ГАВ", "value": "6"},
    {"label": "АЧР", "value": "4 (48.8Гц)"}
  ],
  "loe": {
    "gpv": "2.2",
    "gav": "6",
    "sgav": null,
    "achr": "4 (48.8Гц)",
    "gvsp": null
  }
}
```

For Lvivoblenergo, `gpv`, `gav`, `sgav`, `achr`, and `gvsp` are address groups, not a full hourly outage schedule. The API uses `status: "UNKNOWN"` unless Lvivoblenergo returns an explicit `disconnection_task`.

### 5. Service Checks

Health check:

```http
GET /api/v1/health
```

Lvivoblenergo cache status:

```http
GET /api/v1/cache/status
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
- `app/group_directory.py` maps known addresses and villages to Naftogaz outage groups.
- `app/loe_api.py` normalizes Lvivoblenergo account data from `power-api.loe.lviv.ua`.
- Lvivoblenergo groups stay separate from Naftogaz groups. Use the `loe` object for `gpv`, `gav`, `sgav`, `achr`, and `gvsp` data.

Example Lvivoblenergo data:

```json
{
  "building": "2-А",
  "loe": {
    "gpv": "2.2",
    "gav": "6",
    "sgav": null,
    "achr": "4 (48.8Гц)",
    "gvsp": null
  }
}
```
- `app/api.py` combines Telegram fetching, OCR parsing, text parsing, and the `/status` response.
