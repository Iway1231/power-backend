import asyncio
from datetime import datetime

import pytest

from app import api
from app.ocr import extract_intervals, fix_time, is_valid_interval


def test_fix_time_does_not_rewrite_1100_as_2000():
    assert fix_time("11", "00") == "11:00"


def test_extract_intervals_accepts_valid_non_template_minutes():
    assert extract_intervals("з 17:00 по 19:30") == ["17:00-19:30"]


def test_extract_intervals_keeps_partial_results_without_inventing_ranges():
    text = "з 17:00 по 19:30; з 25:00 по 26:00"

    assert extract_intervals(text) == ["17:00-19:30"]


def test_invalid_intervals_are_not_treated_as_outages():
    assert not is_valid_interval("25:00-26:00")
    assert not is_valid_interval("12:60-13:00")
    assert not is_valid_interval("19:30-17:00")
    assert not is_valid_interval("10:00-10:00")


def test_schedule_with_no_intervals_does_not_create_outage_data():
    assert extract_intervals("Електроенергія є") == []


def test_group_schedule_without_date_is_not_active():
    parsed = {
        "type": "GROUP_SCHEDULE",
        "date": None,
        "groups": {"1.1": {"outages": ["11:00-14:00"]}},
    }

    assert not api.is_group_schedule_active(parsed, now=datetime(2026, 6, 6, 10, 0))


@pytest.mark.asyncio
async def test_source_failure_does_not_create_daily_status(monkeypatch, tmp_path):
    async def fail_fetch():
        raise api.StatusRefreshUnavailable("source unavailable")

    monkeypatch.setattr(api, "_fetch_power_status", fail_fetch)
    monkeypatch.setattr(api, "_status_cache", None)
    monkeypatch.setattr(api, "_status_cache_time", 0)
    monkeypatch.setattr(api, "HISTORY_DIR", tmp_path / "history")
    api.HISTORY_DIR.mkdir()
    monkeypatch.setattr(api._redis_store, "get_json", lambda key: asyncio.sleep(0, result=None))
    monkeypatch.setattr(api, "FALLBACK_FILE", api.config.DATA_DIR / "missing-test-status.json")

    with pytest.raises(api.HTTPException) as error:
        await api.get_power_status()

    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_missing_ocr_date_is_not_saved_as_dated_status(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "HISTORY_DIR", tmp_path / "history")
    api.HISTORY_DIR.mkdir()
    monkeypatch.setattr(api, "current_status_date", lambda: "2026-06-06")
    monkeypatch.setattr(
        api,
        "fetch_latest_posts",
        lambda limit=20: asyncio.sleep(
            0,
            result=[
                {
                    "text": "",
                    "image": "https://example.test/image.jpg",
                    "published_at": "2026-06-06T08:00:00+03:00",
                }
            ],
        ),
    )
    monkeypatch.setattr(api, "download_image", lambda url: asyncio.sleep(0, result="image.jpg"))
    monkeypatch.setattr(
        api,
        "extract_schedule_with_gate",
        lambda path: asyncio.sleep(
            0,
            result={
                "groups": {"1.1": ["11:00-14:00"]},
                "date": None,
                "confidence": {"date": 0.0, "groups": 0.9},
            },
        ),
    )

    with pytest.raises(api.StatusRefreshUnavailable):
        await api._fetch_power_status()

    assert list(api.HISTORY_DIR.glob("*.json")) == []


@pytest.mark.asyncio
async def test_ocr_cache_uses_image_digest_and_survives_redis_failure(monkeypatch, tmp_path):
    status_date = api.current_status_date()
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(api, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(api.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(api, "FALLBACK_FILE", tmp_path / "last_status.json")

    redis_data = {}

    async def redis_get(key):
        return redis_data.get(key)

    async def redis_set(key, value, _ttl):
        return False

    monkeypatch.setattr(api._redis_store, "get_json", redis_get)
    monkeypatch.setattr(api._redis_store, "set_json", redis_set)
    monkeypatch.setattr(api, "_ocr_memory_cache", {})
    monkeypatch.setattr(
        api,
        "fetch_latest_posts",
        lambda limit=20: asyncio.sleep(
            0,
            result=[
                {
                    "post_id": "42",
                    "text": "",
                    "image": "https://example.test/42.jpg",
                    "published_at": f"{status_date}T08:00:00+03:00",
                }
            ],
        ),
    )

    downloads = 0
    ocr_calls = 0
    image_contents = [b"first image", b"first image", b"updated image"]

    async def download(_url):
        nonlocal downloads
        content = image_contents[downloads]
        downloads += 1
        path = tmp_path / f"image-{downloads}.jpg"
        path.write_bytes(content)
        return str(path)

    async def extract(_path):
        nonlocal ocr_calls
        ocr_calls += 1
        return {
            "groups": {"1.1": ["00:00-23:59"]},
            "date": status_date,
            "confidence": {"date": 1.0, "groups": 1.0},
        }

    monkeypatch.setattr(api, "download_image", download)
    monkeypatch.setattr(api, "extract_schedule_with_gate", extract)

    await api._fetch_power_status()
    await api._fetch_power_status()
    await api._fetch_power_status()

    assert downloads == 3
    assert ocr_calls == 2
    assert api._ocr_memory_cache


@pytest.mark.asyncio
async def test_valid_status_is_saved_before_a_later_slow_ocr(monkeypatch):
    status_date = api.current_status_date()
    saved = asyncio.Event()
    release_slow_ocr = asyncio.Event()
    ocr_calls = 0

    monkeypatch.setattr(
        api,
        "fetch_latest_posts",
        lambda limit=20: asyncio.sleep(
            0,
            result=[
                {
                    "post_id": "new",
                    "text": "",
                    "image": "https://example.test/new.jpg",
                    "published_at": f"{status_date}T10:00:00+03:00",
                },
                {
                    "post_id": "old",
                    "text": "",
                    "image": "https://example.test/old.jpg",
                    "published_at": f"{status_date}T09:00:00+03:00",
                },
            ],
        ),
    )
    monkeypatch.setattr(
        api,
        "download_image",
        lambda url: asyncio.sleep(0, result=url),
    )
    monkeypatch.setattr(api, "_image_digest", lambda path: path)
    monkeypatch.setattr(api, "_ocr_memory_cache", {})
    monkeypatch.setattr(api._redis_store, "get_json", lambda key: asyncio.sleep(0, result=None))
    monkeypatch.setattr(api._redis_store, "set_json", lambda *args: asyncio.sleep(0, result=False))
    monkeypatch.setattr(api, "is_group_schedule_active", lambda parsed: True)
    monkeypatch.setattr(api, "load_dated_status", lambda date: asyncio.sleep(0, result=None))

    async def save_dated_status(_parsed, _published_at):
        saved.set()
        return True

    async def extract(_path):
        nonlocal ocr_calls
        ocr_calls += 1
        if ocr_calls == 2:
            await release_slow_ocr.wait()
        return {
            "groups": {"1.1": ["00:00-23:59"]},
            "date": status_date,
            "confidence": {"date": 1.0, "groups": 1.0},
        }

    monkeypatch.setattr(api, "save_dated_status", save_dated_status)
    monkeypatch.setattr(api, "extract_schedule_with_gate", extract)

    task = asyncio.create_task(api._fetch_power_status())
    await asyncio.wait_for(saved.wait(), timeout=1)
    assert not task.done()
    release_slow_ocr.set()
    await task
