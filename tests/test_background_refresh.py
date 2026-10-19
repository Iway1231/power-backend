import asyncio
from datetime import datetime, timedelta

import pytest

from app import api
from app.config import SETTINGS
from app.main import create_app


@pytest.mark.asyncio
async def test_background_refresh_runs_immediately_and_at_interval(monkeypatch):
    power_calls = 0
    water_calls = 0
    stop_event = asyncio.Event()
    refreshed = asyncio.Event()

    async def refresh_power():
        nonlocal power_calls
        power_calls += 1
        refreshed.set()

    async def refresh_water():
        nonlocal water_calls
        water_calls += 1

    monkeypatch.setattr(api, "refresh_power_status_once", refresh_power)
    monkeypatch.setattr("app.water.refresh_water_status_once", refresh_water)

    task = asyncio.create_task(api.run_background_refresh_loop(stop_event, interval_seconds=0.01))
    await asyncio.wait_for(refreshed.wait(), timeout=1)
    await asyncio.sleep(0.03)
    stop_event.set()
    await task

    assert power_calls >= 2
    assert water_calls >= 2


@pytest.mark.asyncio
async def test_background_refresh_recovers_after_one_refresh_error(monkeypatch):
    calls = 0
    stop_event = asyncio.Event()
    refreshed = asyncio.Event()

    async def refresh_power():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary failure")
        refreshed.set()
        stop_event.set()

    async def refresh_water():
        return None

    monkeypatch.setattr(api, "refresh_power_status_once", refresh_power)
    monkeypatch.setattr("app.water.refresh_water_status_once", refresh_water)

    await asyncio.wait_for(
        api.run_background_refresh_loop(stop_event, interval_seconds=0),
        timeout=1,
    )

    assert calls == 2
    assert refreshed.is_set()


@pytest.mark.asyncio
async def test_status_returns_cache_without_running_upstream_refresh(monkeypatch):
    cached = {
        "city": "Новояворівськ",
        "operator": "Нафтогаз Тепло",
        "type": "DAILY_STATUS",
        "message": "cached",
        "date": "2026-10-18",
        "updatedAt": datetime.now().isoformat(),
        "confidence": 1.0,
    }
    monkeypatch.setattr(api, "_status_cache", cached)
    monkeypatch.setattr(api, "_fetch_power_status", lambda: pytest.fail("refresh was called"))

    result = await api.get_power_status()

    assert result.message == "cached"


@pytest.mark.asyncio
async def test_status_returns_503_without_valid_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "_status_cache", None)
    monkeypatch.setattr(api, "FALLBACK_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(api._redis_store, "get_json", lambda key: asyncio.sleep(0, result=None))

    with pytest.raises(api.HTTPException) as error:
        await api.get_power_status()

    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_stale_daily_status_is_not_current(monkeypatch):
    stale = {
        "type": "DAILY_STATUS",
        "updatedAt": (
            datetime.now() - timedelta(seconds=api.STATUS_MAX_AGE_SECONDS + 1)
        ).isoformat(),
    }

    assert not api.is_status_current(stale)


@pytest.mark.asyncio
async def test_legacy_status_without_update_time_is_not_current():
    assert not api.is_status_current({"type": "DAILY_STATUS"})


@pytest.mark.asyncio
async def test_status_does_not_wait_for_first_refresh(monkeypatch, tmp_path):
    started = asyncio.Event()
    release = asyncio.Event()
    monkeypatch.setattr(api, "_status_cache", None)
    monkeypatch.setattr(api, "FALLBACK_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(api._redis_store, "get_json", lambda key: asyncio.sleep(0, result=None))

    async def slow_refresh():
        started.set()
        await release.wait()

    refresh_task = asyncio.create_task(slow_refresh())
    await started.wait()
    with pytest.raises(api.HTTPException) as error:
        await api.get_power_status()
    release.set()
    await refresh_task

    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_app_lifecycle_starts_one_refresh_task_and_stops_it(monkeypatch):
    started = asyncio.Event()

    async def fake_loop(stop_event):
        started.set()
        await stop_event.wait()

    monkeypatch.setattr(api, "run_background_refresh_loop", fake_loop)
    settings = SETTINGS.model_copy(update={"environment": "test"})
    application = create_app(settings)

    async with application.router.lifespan_context(application):
        await asyncio.wait_for(started.wait(), timeout=1)
        task = application.state.status_refresh_task
        assert not task.done()

    assert task.done()


@pytest.mark.asyncio
async def test_water_timeout_does_not_delay_power_refresh(monkeypatch):
    power_calls = 0
    power_done = asyncio.Event()
    stop_event = asyncio.Event()
    short_settings = SETTINGS.model_copy(update={"status_refresh_timeout_seconds": 0.01})
    monkeypatch.setattr(api.config, "SETTINGS", short_settings)

    async def refresh_power():
        nonlocal power_calls
        power_calls += 1
        if power_calls >= 2:
            power_done.set()
            stop_event.set()

    async def hanging_water():
        await asyncio.sleep(1)

    monkeypatch.setattr(api, "refresh_power_status_once", refresh_power)
    monkeypatch.setattr("app.water.refresh_water_status_once", hanging_water)

    await asyncio.wait_for(
        api.run_background_refresh_loop(stop_event, interval_seconds=0.01),
        timeout=1,
    )

    assert power_done.is_set()
    assert power_calls >= 2
