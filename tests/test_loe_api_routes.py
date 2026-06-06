import pytest

from app.api import get_loe_buildings, get_loe_cities, get_loe_lookup, get_loe_streets


@pytest.mark.asyncio
async def test_get_loe_cities(monkeypatch):
    async def fake_fetch_loe_cities():
        return [{"id": 1053, "name": "Шкло"}]

    monkeypatch.setattr("app.api.fetch_loe_cities", fake_fetch_loe_cities)

    assert await get_loe_cities() == ["Шкло"]


@pytest.mark.asyncio
async def test_get_loe_streets(monkeypatch):
    async def fake_fetch_loe_cities():
        return [{"id": 1053, "name": "Шкло"}]

    async def fake_fetch_loe_streets(city_id):
        assert city_id == 1053
        return [{"id": 23713, "name": "1-го травня"}]

    monkeypatch.setattr("app.api.fetch_loe_cities", fake_fetch_loe_cities)
    monkeypatch.setattr("app.api.fetch_loe_streets", fake_fetch_loe_streets)

    assert await get_loe_streets("Шкло") == ["1-го травня"]


@pytest.mark.asyncio
async def test_get_loe_buildings(monkeypatch):
    async def fake_fetch_loe_cities():
        return [{"id": 1053, "name": "Шкло"}]

    async def fake_fetch_loe_streets(city_id):
        return [{"id": 23713, "name": "1-го травня"}]

    async def fake_fetch_loe_accounts(city_id, street_id):
        assert city_id == 1053
        assert street_id == 23713
        return [
            {"buildingName": "1", "chergGpv": "2.2"},
            {"buildingName": "", "chergGpv": "2.2"},
            {"buildingName": "7-А", "chergGpv": "2.2"},
        ]

    monkeypatch.setattr("app.api.fetch_loe_cities", fake_fetch_loe_cities)
    monkeypatch.setattr("app.api.fetch_loe_streets", fake_fetch_loe_streets)
    monkeypatch.setattr("app.api.fetch_loe_accounts", fake_fetch_loe_accounts)

    assert await get_loe_buildings("Шкло", "1-го Травня") == ["1", "7-А"]


@pytest.mark.asyncio
async def test_get_loe_lookup(monkeypatch):
    async def fake_lookup_loe_address(city, street, building, debug=False):
        return {
            "city": city,
            "street": street,
            "building": building,
            "loe": {"gpv": "2.2"},
        }

    monkeypatch.setattr("app.api.lookup_loe_address", fake_lookup_loe_address)

    assert await get_loe_lookup("Шкло", "1-го Травня", "1") == {
        "city": "Шкло",
        "street": "1-го Травня",
        "building": "1",
        "loe": {"gpv": "2.2"},
    }
