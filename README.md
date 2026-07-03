# Power Backend

[![CI](https://github.com/Iway1231/power-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/Iway1231/power-backend/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.127-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Power Backend is a production-oriented FastAPI service for utility outage data in the Novoyavorivsk community. It reads public Telegram posts, parses text and OCR-based schedule images, enriches results with local address/group mappings, and exposes mobile-friendly API endpoints for electricity and water outage status.

The project is designed to be simple enough for local civic tooling and structured enough for open-source collaboration: typed configuration, Docker support, CI, tests, security headers, rate limiting, health checks, and public contribution guidelines.

## Features

- Electricity outage parsing from Naftogaz Teplo Telegram posts.
- OCR support for group schedule images with Tesseract, OpenCV, and Ukrainian language data.
- Planned outage detection by group, village, street, and time interval.
- Lvivoblenergo address lookup integration for cities, streets, buildings, and account groups.
- Water outage notices from the public Novoyavorivskvodokanal Telegram channel.
- Android-friendly endpoints for operator selection, address dropdowns, bootstrap config, and personal status checks.
- In-memory caching with stale fallback for upstream address data.
- Validated environment configuration and safe defaults.
- Security headers, request IDs, rate limiting, structured logging, and Swagger/OpenAPI docs.

## Tech Stack

- **Python 3.10+**
- **FastAPI** and **Pydantic**
- **HTTPX** for upstream HTTP requests
- **BeautifulSoup** and **lxml** for Telegram HTML parsing
- **Tesseract OCR**, **OpenCV**, **Pillow**, and **NumPy** for image parsing
- **pytest** and **pytest-asyncio** for tests
- **Ruff** for linting and formatting
- **Docker** and **GitHub Actions** for delivery

## Quick Start

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/api/v1/health
```

Tesseract must be installed separately for OCR endpoints to parse local images reliably. The Docker image installs the required OCR packages automatically.

## Docker

Build and run with Docker Compose:

```powershell
copy .env.production.example .env
docker compose up --build
```

Or build the image directly:

```powershell
docker build -t power-backend .
docker run --rm -p 8000:8000 --env-file .env.production.example power-backend
```

The container exposes `GET /api/v1/health` as its healthcheck and stores runtime data in `/app/data`.

## API Examples

Health check:

```http
GET /api/v1/health
```

Current parsed electricity status:

```http
GET /api/v1/status
```

Personal status by Naftogaz group:

```http
GET /api/v1/my-status?operator=naftogaz&group=2.1
```

Lvivoblenergo address dropdowns:

```http
GET /api/v1/loe/cities
GET /api/v1/loe/streets?city=Шкло
GET /api/v1/loe/buildings?city=Шкло&street=1-го%20Травня
GET /api/v1/loe/lookup?city=Шкло&street=1-го%20Травня&building=1
```

Water outage notice:

```http
GET /api/v1/water/status
```

Example response:

```json
{
  "operator": "Новояворівськводоканал",
  "type": "WATER_OUTAGE",
  "message": "Тимчасове припинення водопостачання",
  "date": "2026-06-09",
  "from_time": "10:00",
  "to_time": "17:00",
  "locations": ["вул. Зелена", "с. Когути", "с. Стені"],
  "source": "telegram",
  "channel": "vodocanal_nya",
  "confidence": 1.0
}
```

Swagger UI and OpenAPI JSON:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/openapi.json
```

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `Power Schedule API` | Public API name. |
| `APP_VERSION` | `1.0.0` | Semantic application version. |
| `ENVIRONMENT` | `development` | `development`, `test`, or `production`. |
| `DEBUG` | `false` | Enables FastAPI debug mode. |
| `HOST` | `0.0.0.0` | Server host for deployment scripts. |
| `PORT` | `8000` | Server port. |
| `LOG_LEVEL` | `INFO` | Python log level. |
| `LOG_FORMAT` | `console` | `console` or `json`. |
| `CHANNEL_URL` | `https://t.me/s/nya_merezhi` | Naftogaz Telegram public mirror URL. |
| `WATER_CHANNEL_URL` | `https://t.me/s/vodocanal_nya` | Water utility Telegram public mirror URL. |
| `CITY_ID` | `novoyavorivsk` | Internal city identifier. |
| `CITY_NAME` | `Новояворівськ` | Display city name. |
| `REGION` | `Львівська область` | Display region name. |
| `OPERATOR` | `Нафтогаз Тепло` | Primary electricity operator name. |
| `TIMEZONE` | `Europe/Kyiv` | IANA timezone name. |
| `STATUS_CACHE_TTL_SECONDS` | `90` | Parsed status cache lifetime. |
| `LOE_CACHE_TTL_SECONDS` | `300` | Lvivoblenergo lookup cache lifetime. |
| `REQUEST_TIMEOUT_SECONDS` | `30` | Upstream HTTP timeout. |
| `RATE_LIMIT_REQUESTS` | `120` | Requests allowed per window and route. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window length. |
| `CORS_ORIGINS` | empty | Comma-separated allowed origins. |
| `ALLOWED_HOSTS` | `*` | Comma-separated trusted hostnames. |
| `DATA_DIR` | `data` | Runtime data directory. |

## Project Structure

```text
app/
  api.py              # API routes and response composition
  config.py           # validated runtime settings
  errors.py           # consistent exception responses
  group_directory.py  # Naftogaz group/address mapping
  loe_api.py          # Lvivoblenergo API client and cache
  main.py             # FastAPI app factory and middleware
  middleware.py       # request IDs, security headers, rate limiting
  ocr.py              # OCR schedule parsing
  parser.py           # text post parsing
  telegram_html.py    # Telegram public HTML reader
  water.py            # water outage parser and endpoint
tests/                # regression and route tests
.github/              # CI, issue templates, PR template
Dockerfile            # production container image
docker-compose.yml    # local production-like stack
```

## Development

Run tests:

```powershell
python -m pytest -q
```

Run linting and formatting checks:

```powershell
ruff check .
ruff format --check .
```

Apply formatting:

```powershell
ruff format .
```

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md), follow the [Code of Conduct](CODE_OF_CONDUCT.md), and open an issue before larger changes.

Good first contributions include:

- adding more OCR regression images,
- improving address normalization,
- strengthening parser tests,
- documenting Android integration examples,
- improving deployment examples.

## Security

Please do not open public issues for vulnerabilities. Follow [SECURITY.md](SECURITY.md) for responsible disclosure.

## License

This project is licensed under the [MIT License](LICENSE).
