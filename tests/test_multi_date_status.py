import asyncio
import json
from datetime import datetime, timedelta

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
async def test_unknown_publication_cannot_replace_known_publication(
    isolated_schedule_store,
):
    await api.save_dated_status(
        _parsed("2026-10-19", "known"),
        "2026-10-18T12:00:00+03:00",
    )

    assert not await api.save_dated_status(_parsed("2026-10-19", "missing"), None)
    assert not await api.save_dated_status(_parsed("2026-10-19", "invalid"), "not-a-date")

    record = json.loads(
        (isolated_schedule_store[0] / "2026-10-19.json").read_text(encoding="utf-8")
    )
    assert record["status"]["message"] == "known"


@pytest.mark.asyncio
async def test_dated_status_ignores_updated_at_age(monkeypatch, isolated_schedule_store):
    status_date = "2026-10-18"
    monkeypatch.setattr(api, "current_status_date", lambda: status_date)
    old_status = api._status_record_payload(
        _parsed(status_date, "old but valid"),
        "2026-10-17T12:00:00+03:00",
    )
    old_status["status"]["updatedAt"] = (
        datetime.now() - timedelta(seconds=api.STATUS_MAX_AGE_SECONDS + 60)
    ).isoformat()
    (isolated_schedule_store[0] / f"{status_date}.json").write_text(
        json.dumps(old_status), encoding="utf-8"
    )

    result = await api.get_power_status()

    assert result.message == "old but valid"


@pytest.mark.asyncio
async def test_mismatched_file_date_falls_back_to_matching_redis_record(
    monkeypatch, isolated_schedule_store
):
    status_date = "2026-10-18"
    monkeypatch.setattr(api, "current_status_date", lambda: status_date)
    wrong = api._status_record_payload(_parsed("2026-10-19", "wrong"), None)
    matching = api._status_record_payload(_parsed(status_date, "matching"), None)
    (isolated_schedule_store[0] / f"{status_date}.json").write_text(
        json.dumps(wrong), encoding="utf-8"
    )
    isolated_schedule_store[1][f"status:power:{status_date}"] = matching

    result = await api.get_power_status()

    assert result.message == "matching"


@pytest.mark.asyncio
async def test_redis_write_failure_keeps_multiple_dates_in_files(
    monkeypatch, isolated_schedule_store
):
    async def failing_set(*_args):
        raise RuntimeError("redis offline")

    monkeypatch.setattr(api._redis_store, "set_json", failing_set)
    assert await api.save_dated_status(_parsed("2026-10-18", "today"), None)
    assert await api.save_dated_status(_parsed("2026-10-19", "tomorrow"), None)

    assert (isolated_schedule_store[0] / "2026-10-18.json").exists()
    assert (isolated_schedule_store[0] / "2026-10-19.json").exists()


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
