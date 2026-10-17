import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app import api
from app.main import app


@pytest.mark.asyncio
async def test_power_status_runs_ocr_outside_event_loop(monkeypatch):
    monkeypatch.setattr(api, "_status_cache", None)
    monkeypatch.setattr(api, "_status_cache_time", 0)
    monkeypatch.setattr(
        api,
        "fetch_latest_posts",
        lambda limit=20: asyncio.sleep(
            0,
            result=[{"text": "", "image": "https://example.test/image.jpg"}],
        ),
    )
    monkeypatch.setattr(api, "download_image", lambda url: asyncio.sleep(0, result="image.jpg"))
    monkeypatch.setattr(api, "parse_power_text", lambda text: None)
    monkeypatch.setattr(
        api,
        "extract_schedule_from_image",
        lambda path: {
            "type": "GROUP_SCHEDULE",
            "date": "2099-01-01",
            "groups": {"1.1": {"status": "OFF", "outages": ["08:00-12:00"]}},
            "intervals": [],
            "message": "test",
            "confidence": 1.0,
        },
    )
    monkeypatch.setattr(api, "is_group_schedule_active", lambda parsed: True)
    monkeypatch.setattr(api, "save_status", lambda parsed: parsed)

    calls = []

    async def fake_to_thread(function, *args):
        calls.append((function, args))
        return function(*args)

    monkeypatch.setattr(api.asyncio, "to_thread", fake_to_thread)

    result = await api._fetch_power_status()

    assert result["type"] == "GROUP_SCHEDULE"
    assert calls == [(api.extract_schedule_from_image, ("image.jpg",))]


@pytest.mark.asyncio
async def test_concurrent_refreshes_do_not_run_ocr_in_parallel(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def fake_to_thread(function, *args):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {
            "type": "GROUP_SCHEDULE",
            "date": "2099-01-01",
            "groups": {"1.1": {"status": "OFF", "outages": ["08:00-12:00"]}},
            "intervals": [],
            "message": "test",
            "confidence": 1.0,
        }

    monkeypatch.setattr(api.asyncio, "to_thread", fake_to_thread)

    first = asyncio.create_task(api.extract_schedule_with_gate("first.jpg"))
    await started.wait()
    second = await api.extract_schedule_with_gate("second.jpg")
    release.set()
    result = await first

    assert result["type"] == "GROUP_SCHEDULE"
    assert second is None
    assert calls == 1


@pytest.mark.asyncio
async def test_concurrent_power_refreshes_share_one_result(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "_status_cache", None)
    monkeypatch.setattr(api, "_status_cache_time", 0)
    monkeypatch.setattr(api, "FALLBACK_FILE", tmp_path / "last_status.json")
    monkeypatch.setattr(api._redis_store, "get_json", lambda key: asyncio.sleep(0, result=None))
    monkeypatch.setattr(api._redis_store, "set_json", lambda *args: asyncio.sleep(0))
    monkeypatch.setattr(
        api,
        "fetch_latest_posts",
        lambda limit=20: asyncio.sleep(0, result=[{"text": "outage", "image": None}]),
    )
    parsed = {
        "type": "GROUP_SCHEDULE",
        "date": "2099-01-01",
        "groups": {"1.1": {"status": "OFF", "outages": ["08:00-12:00"]}},
        "intervals": [],
        "message": "test",
        "confidence": 1.0,
    }
    calls = 0

    def fake_parse_power_text(text):
        nonlocal calls
        calls += 1
        return parsed

    monkeypatch.setattr(api, "parse_power_text", fake_parse_power_text)
    monkeypatch.setattr(api, "is_planned_outage_active", lambda value: True)

    first, second = await asyncio.gather(api.get_power_status(), api.get_power_status())

    assert first.type == second.type == "GROUP_SCHEDULE"
    assert calls == 1


@pytest.mark.asyncio
async def test_power_status_restores_last_status_after_upstream_failure(monkeypatch, tmp_path):
    fallback_file = tmp_path / "last_status.json"
    fallback_file.write_text(
        '{"city":"Новояворівськ","operator":"Нафтогаз Тепло",'
        '"type":"GROUP_SCHEDULE","message":"saved","groups":{},'
        '"intervals":[],"date":"2099-01-01","updatedAt":"2099-01-01T00:00:00",'
        '"confidence":1.0}',
        encoding="utf-8",
    )
    monkeypatch.setattr(api, "FALLBACK_FILE", fallback_file)
    monkeypatch.setattr(api, "_status_cache", None)
    monkeypatch.setattr(api, "_status_cache_time", 0)
    monkeypatch.setattr(api._redis_store, "get_json", lambda key: asyncio.sleep(0, result=None))

    async def fail_fetch():
        raise httpx.ConnectError("upstream offline")

    monkeypatch.setattr(api, "_fetch_power_status", fail_fetch)

    result = await api.get_power_status()

    assert result.type == "GROUP_SCHEDULE"
    assert result.message == "saved"


@pytest.mark.asyncio
async def test_power_status_ignores_expired_planned_outage_in_redis(monkeypatch):
    stale = {
        "city": "Новояворівськ",
        "operator": "Нафтогаз Тепло",
        "type": "PLANNED_OUTAGE",
        "message": "expired",
        "groups": None,
        "intervals": [{"from_time": "11:00", "to_time": "12:00", "status": "OFF"}],
        "date": "2026-10-16",
        "updatedAt": "2026-10-16T21:11:57",
        "confidence": 1.0,
    }
    monkeypatch.setattr(
        api._redis_store,
        "get_json",
        lambda key: asyncio.sleep(0, result=stale),
    )
    monkeypatch.setattr(api._redis_store, "set_json", lambda *args: asyncio.sleep(0))
    refreshed = api.PowerStatus(
        city="Новояворівськ",
        operator="Нафтогаз Тепло",
        type="DAILY_STATUS",
        message="current",
        date="2026-10-17",
        confidence=1.0,
    )
    monkeypatch.setattr(api, "_fetch_power_status", lambda: asyncio.sleep(0, result=refreshed))
    monkeypatch.setattr(
        api, "is_planned_outage_active", lambda value: value.get("date") == "2026-10-17"
    )

    result = await api.get_power_status()

    assert result.type == "DAILY_STATUS"
    assert result.message == "current"


def test_status_route_returns_fallback_after_refresh_timeout(monkeypatch, tmp_path):
    fallback_file = tmp_path / "last_status.json"
    fallback_file.write_text(
        '{"city":"Новояворівськ","operator":"Нафтогаз Тепло",'
        '"type":"GROUP_SCHEDULE","message":"saved","groups":{},'
        '"intervals":[],"date":"2099-01-01","updatedAt":"2099-01-01T00:00:00",'
        '"confidence":1.0}',
        encoding="utf-8",
    )
    monkeypatch.setattr(api, "FALLBACK_FILE", fallback_file)
    monkeypatch.setattr(api._redis_store, "get_json", lambda key: asyncio.sleep(0, result=None))

    async def timeout_fetch():
        raise asyncio.TimeoutError

    monkeypatch.setattr(api, "_fetch_power_status", timeout_fetch)

    response = TestClient(app).get("/api/v1/status")

    assert response.status_code == 200
    assert response.json()["message"] == "saved"
