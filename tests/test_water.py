import asyncio
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from app.water import (
    get_water_status,
    is_water_outage_active,
    is_water_outage_currently_active,
    parse_water_outage,
    refresh_water_status_once,
)


def test_parse_water_outage_with_restoration_time():
    text = """
    Увага!
    09.06.2026 р. з 10:00 буде тимчасово припинено водопостачання
    у районі вул. Зелена, АЗС «WOG», СТ «Приміський садівник»,
    с. Когути та с. Стені.

    Також тимчасово без водопостачання залишаться:
    • Смок Хаус BBQ;
    • відпочинковий комплекс «Криве Озеро»;
    • готель «Ланцелот».

    Орієнтовний час відновлення водопостачання — 17:00.
    """

    result = parse_water_outage(text)

    assert result["type"] == "WATER_OUTAGE"
    assert result["date"] == "2026-06-09"
    assert result["from_time"] == "10:00"
    assert result["to_time"] == "17:00"
    assert "вул. Зелена" in result["locations"]
    assert "с. Когути" in result["locations"]
    assert "с. Стені" in result["locations"]
    assert "готель «Ланцелот»" in result["locations"]


def test_parse_water_outage_with_named_date_and_interval():
    text = """
    УВАГА!
    У четвер, 23 квітня, з 10:00 до 13:00 буде тимчасово припинено
    водопостачання.
    """

    result = parse_water_outage(text, "2026-04-22T17:01:00+03:00")

    assert result["date"] == "2026-04-23"
    assert result["from_time"] == "10:00"
    assert result["to_time"] == "13:00"


def test_real_vodocanal_posts_parse_without_inventing_missing_times():
    fixtures = json.loads(
        (Path(__file__).parent / "fixtures" / "vodocanal_nya_posts.json").read_text(
            encoding="utf-8"
        )
    )

    for post in fixtures:
        result = parse_water_outage(post["text"], post["published_at"])
        expected = post["expected"]
        assert result is not None
        assert result["type"] == expected["type"]
        assert result["date"] == expected["date"]
        assert result["from_time"] == expected["from_time"]
        assert result["to_time"] == expected["to_time"]
        assert result["locations"] == expected["locations"]


def test_parse_water_outage_for_stadnyky_repair_notice():
    text = (
        "23 жовтня 2026 року з 10:30 до 16:00 буде тимчасово припинено "
        "водопостачання у с. Стадники через ремонтні роботи."
    )

    result = parse_water_outage(text)

    assert result["date"] == "2026-10-23"
    assert result["from_time"] == "10:30"
    assert result["to_time"] == "16:00"
    assert result["locations"] == ["с. Стадники"]


def test_water_outage_without_date_is_not_accepted():
    assert parse_water_outage("з 10:30 до 16:00 буде припинено водопостачання") is None


def test_water_outage_with_invalid_time_is_not_accepted():
    text = "23 жовтня 2026 року з 25:30 до 16:00 буде припинено водопостачання"

    assert parse_water_outage(text) is None


def test_unknown_water_location_is_preserved_without_allowlist_filtering():
    result = parse_water_outage(
        "23 жовтня 2026 року з 10:30 до 16:00 буде припинено "
        "водопостачання у с. Невідоме через ремонтні роботи."
    )

    assert result["locations"] == ["с. Невідоме"]


def test_future_water_outage_is_planned_not_current():
    outage = {
        "date": "2026-10-23",
        "from_time": "10:30",
        "to_time": "16:00",
    }

    assert is_water_outage_active(outage, now=datetime(2026, 10, 23, 9, 0))
    assert not is_water_outage_currently_active(outage, now=datetime(2026, 10, 23, 9, 0))
    assert is_water_outage_currently_active(outage, now=datetime(2026, 10, 23, 12, 0))
    assert not is_water_outage_active(outage, now=datetime(2026, 10, 23, 17, 0))


def test_water_mobile_section_keeps_future_outage_planned():
    from app.api import build_water_mobile_section

    result = build_water_mobile_section(
        {
            "type": "WATER_OUTAGE",
            "has_outage": False,
            "date": "2026-10-23",
            "from_time": "10:30",
            "to_time": "16:00",
        }
    )

    assert result["has_outage"] is False
    assert result["status"] == "ON"
    assert result["title"] == "Заплановане відключення води"


def test_water_mobile_section_does_not_treat_missing_interval_as_available():
    from app.api import build_water_mobile_section

    result = build_water_mobile_section(
        {
            "type": "WATER_OUTAGE",
            "has_outage": None,
            "date": "2026-10-19",
            "to_time": "19:00",
        }
    )

    assert result["has_outage"] is None
    assert result["status"] == "UNKNOWN"


def test_expired_water_outage_is_inactive():
    outage = {
        "date": "2026-06-09",
        "to_time": "17:00",
    }

    assert not is_water_outage_active(
        outage,
        now=datetime(2026, 6, 10, 9, 0),
    )


@pytest.mark.asyncio
async def test_water_status_returns_active_post(monkeypatch):
    async def fake_fetch_water_posts(limit=20):
        return [
            {
                "text": ("09.06.2026 р. з 10:00 до 17:00 буде тимчасово припинено водопостачання."),
                "published_at": "2026-06-09T09:00:00+03:00",
            }
        ]

    monkeypatch.setattr("app.water.fetch_water_posts", fake_fetch_water_posts)
    monkeypatch.setattr(
        "app.water.is_water_outage_active",
        lambda outage: True,
    )
    redis_data = {}

    async def redis_get(key):
        return redis_data.get(key)

    async def redis_set(key, value, _ttl):
        redis_data[key] = value
        return True

    monkeypatch.setattr("app.water._redis_store.get_json", redis_get)
    monkeypatch.setattr("app.water._redis_store.set_json", redis_set)

    assert await refresh_water_status_once()
    result = await get_water_status()

    assert result["type"] == "WATER_OUTAGE"
    assert result["from_time"] == "10:00"


@pytest.mark.asyncio
async def test_water_status_handles_unavailable_channel(monkeypatch):
    async def fake_fetch_water_posts(limit=20):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.water.fetch_water_posts", fake_fetch_water_posts)
    monkeypatch.setattr(
        "app.water._redis_store.get_json", lambda key: asyncio.sleep(0, result=None)
    )

    assert not await refresh_water_status_once()
    result = await get_water_status()

    assert result["type"] == "WATER_STATUS"
    assert result["has_outage"] is None
    assert result["source_available"] is False
