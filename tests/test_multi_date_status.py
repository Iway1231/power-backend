import asyncio
import json

import pytest

from app import api


def _parsed(status_date: str, message: str) -> dict:
    return {
        "type": "GROUP_SCHEDULE",
        "date": status_date,
        "groups": {"1.2": {"status": "OFF", "outages": ["10:00-12:00"]}},
        "intervals": [],
        "message": message,
        "confidence": 1.0,
    }


@pytest.fixture
def isolated_schedule_store(monkeypatch, tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(api, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(api.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(api, "FALLBACK_FILE", tmp_path / "last_status.json")

    redis_data = {}

    async def redis_get(key):
        return redis_data.get(key)

    async def redis_set(key, value, _ttl):
        redis_data[key] = value
        return True

    monkeypatch.setattr(api._redis_store, "get_json", redis_get)
    monkeypatch.setattr(api._redis_store, "set_json", redis_set)
    return history_dir, redis_data


@pytest.mark.asyncio
async def test_refresh_persists_multiple_dates_and_rolls_over_without_fetch(
    monkeypatch, isolated_schedule_store
):
    history_dir, _redis_data = isolated_schedule_store
    today = "2026-10-18"
    tomorrow = "2026-10-19"
    monkeypatch.setattr(api, "current_status_date", lambda: today)
    monkeypatch.setattr(api, "is_group_schedule_active", lambda parsed: True)
    parsed_by_text = {
        "today": _parsed(today, "сьогодні"),
        "tomorrow": _parsed(tomorrow, "завтра"),
    }
    monkeypatch.setattr(api, "parse_power_text", lambda text: parsed_by_text.get(text))
    monkeypatch.setattr(
        api,
        "fetch_latest_posts",
        lambda limit=20: asyncio.sleep(
            0,
            result=[
                {"text": "tomorrow", "image": None, "published_at": "2026-10-18T09:00:00+03:00"},
                {"text": "today", "image": None, "published_at": "2026-10-18T08:00:00+03:00"},
            ],
        ),
    )

    result = await api._fetch_power_status()

    assert result.date == today
    assert (history_dir / f"{today}.json").exists()
    assert (history_dir / f"{tomorrow}.json").exists()

    monkeypatch.setattr(api, "current_status_date", lambda: tomorrow)
    api._status_cache = None
    api._status_cache_time = 0
    monkeypatch.setattr(api, "fetch_latest_posts", lambda **kwargs: pytest.fail("fetch called"))

    rolled_over = await api.get_power_status()

    assert rolled_over.date == tomorrow
    assert rolled_over.message == "завтра"


@pytest.mark.asyncio
async def test_same_date_only_newer_publication_replaces_saved_schedule(
    isolated_schedule_store,
):
    await api.save_dated_status(
        _parsed("2026-10-19", "newer"),
        "2026-10-18T12:00:00+03:00",
    )
    replaced = await api.save_dated_status(
        _parsed("2026-10-19", "older"),
        "2026-10-18T11:00:00+03:00",
    )

    record = json.loads(
        (isolated_schedule_store[0] / "2026-10-19.json").read_text(encoding="utf-8")
    )

    assert replaced is False
    assert record["status"]["message"] == "newer"


@pytest.mark.asyncio
async def test_future_only_schedule_is_not_returned_as_current(
    monkeypatch, isolated_schedule_store
):
    tomorrow = "2026-10-19"
    monkeypatch.setattr(api, "current_status_date", lambda: "2026-10-18")
    await api.save_dated_status(_parsed(tomorrow, "майбутній"), None)
    api._status_cache = None

    with pytest.raises(api.HTTPException) as error:
        await api.get_power_status()

    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_invalid_refresh_does_not_delete_existing_dated_schedule(
    monkeypatch, isolated_schedule_store
):
    status_date = "2026-10-18"
    monkeypatch.setattr(api, "current_status_date", lambda: status_date)
    await api.save_dated_status(_parsed(status_date, "збережений"), "2026-10-18T08:00:00+03:00")

    monkeypatch.setattr(api, "fetch_latest_posts", lambda limit=20: asyncio.sleep(0, result=[]))
    assert await api.refresh_power_status_once() is False

    record = json.loads(
        (isolated_schedule_store[0] / f"{status_date}.json").read_text(encoding="utf-8")
    )
    assert record["status"]["message"] == "збережений"
