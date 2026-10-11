# Android API Contract

Base URL examples:

- Local Wi-Fi: `http://192.168.0.119:8000`
- Production: use an HTTPS domain. Do not ship a home/LAN IP in the release app.

## Authentication

The backend supports an optional shared API key. In production configure `API_KEY` and `API_KEY_REQUIRED=true`, then send:

```http
X-API-Key: <key>
```

The key is a shared transport gate, not a permanent secret: Android APKs can be inspected. Use HTTPS, rate limiting, and rotate the key when needed. Health and OpenAPI discovery remain public.

## Address Selection

```http
GET /api/v1/loe/cities
GET /api/v1/loe/streets?city=Шкло
GET /api/v1/loe/buildings?city=Шкло&street=1-го%20Травня
GET /api/v1/loe/lookup?city=Шкло&street=1-го%20Травня&building=1
```

The configured `LOE_OTG_ID=73` limits the city list to the Novoyavorivsk community. The lookup response contains the selected building and its groups:

```json
{
  "building": "1",
  "loe": {"gpv": "2.2", "gav": "6", "sgav": null, "achr": "4 (48.8Гц)", "gvsp": null},
  "disconnection_task": false,
  "planned_replace_counter": false,
  "city": "Шкло",
  "street": "1-го Травня"
}
```

## Status

```http
GET /api/v1/my-status?operator=loe&city=Шкло&street=1-го%20Травня&building=1
GET /api/v1/mobile/home?operator=loe&city=Шкло&street=1-го%20Травня&building=1&include_water=false
```

`/mobile/home` returns `schema_version`, `updated_at`, `overall_status`, `primary`, and `sections`. Each section contains `id`, `label`, `operator`, `has_outage`, `status`, `title`, `subtitle`, `details`, `date`, `outages`, `intervals`, `source_available`, and `source`.

## Error Contract

All errors use this shape:

```json
{
  "error": {
    "code": "upstream_unavailable",
    "message": "An upstream data source is temporarily unavailable",
    "request_id": "..."
  }
}
```

Important codes:

- `validation_error` (`422`) - invalid query parameters;
- `invalid_api_key` (`401`) - missing or incorrect key;
- `rate_limit_exceeded` (`429`) - retry after the `Retry-After` header;
- `upstream_unavailable` (`503`) - retry with backoff;
- `city_not_found`, `street_not_found`, `building_not_found` (`404`) - selection mismatch.

Android should show a cached result for temporary `429`/`503` failures, retry with exponential backoff, and display `request_id` when asking for support.

## Wi-Fi and Mobile Internet Checklist

1. Start the server on `0.0.0.0`, not only `127.0.0.1`.
2. On Wi-Fi, open `/api/v1/health` using the computer's LAN IP.
3. For LTE/mobile internet, deploy the API behind HTTPS on a public host or use a secure tunnel. `192.168.x.x` works only inside the same local network.
4. Verify `/api/v1/health`, `/api/v1/loe/cities`, and `/api/v1/mobile/home` from the Android device.
5. Do not expose port `8000` directly to the internet without HTTPS, authentication, and a reverse proxy.