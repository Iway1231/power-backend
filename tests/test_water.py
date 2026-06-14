from datetime import datetime

import pytest
import httpx

from app.water import (
    get_water_status,
    is_water_outage_active,
    parse_water_outage,
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
        return [{
            "text": (
                "09.06.2026 р. з 10:00 до 17:00 буде тимчасово "
                "припинено водопостачання."
            ),
            "published_at": "2026-06-09T09:00:00+03:00",
        }]

    monkeypatch.setattr("app.water.fetch_water_posts", fake_fetch_water_posts)
    monkeypatch.setattr(
        "app.water.is_water_outage_active",
        lambda outage: True,
    )

    result = await get_water_status()

    assert result["type"] == "WATER_OUTAGE"
    assert result["from_time"] == "10:00"


@pytest.mark.asyncio
async def test_water_status_handles_unavailable_channel(monkeypatch):
    async def fake_fetch_water_posts(limit=20):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.water.fetch_water_posts", fake_fetch_water_posts)

    result = await get_water_status()

    assert result["type"] == "WATER_STATUS"
    assert result["has_outage"] is None
    assert result["source_available"] is False
