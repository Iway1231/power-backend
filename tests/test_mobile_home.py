import pytest
from fastapi.testclient import TestClient

from app.api import build_mobile_home_response, get_mobile_home
from app.main import app

client = TestClient(app)


def test_build_mobile_home_response_for_electricity_and_water():
    electricity = {
        "operator": "naftogaz",
        "group": "2.1",
        "has_outage": False,
        "status": "ON",
        "title": "?????? ??? ????",
        "subtitle": "??? ????? 2.1 ?????????? ?????",
        "details": [{"label": "?????", "value": "2.1"}],
        "date": "2026-09-11",
    }
    water = {
        "operator": "??????????????????????",
        "type": "WATER_OUTAGE",
        "message": "????????? ?????????? ??????????????",
        "date": "2026-09-11",
        "from_time": "10:00",
        "to_time": "17:00",
        "locations": ["???. ??????"],
    }

    result = build_mobile_home_response(electricity, water)

    assert result["schema_version"] == "1.0"
    assert result["overall_status"] == "OFF"
    assert result["primary"]["id"] == "electricity"
    assert result["sections"][0]["status"] == "ON"
    assert result["sections"][1]["id"] == "water"
    assert result["sections"][1]["status"] == "OFF"
    assert result["sections"][1]["details"][3] == {
        "label": "???????",
        "value": ["???. ??????"],
    }


def test_build_mobile_home_response_without_water_section():
    electricity = {
        "operator": "loe",
        "has_outage": None,
        "title": "????? ?????? ????????",
        "details": [],
    }

    result = build_mobile_home_response(electricity)

    assert result["overall_status"] == "UNKNOWN"
    assert [section["id"] for section in result["sections"]] == ["electricity"]


@pytest.mark.asyncio
async def test_get_mobile_home_uses_personal_status_and_water(monkeypatch):
    async def fake_get_my_status(**kwargs):
        return {
            "operator": kwargs["operator"],
            "group": kwargs["group"],
            "has_outage": False,
            "status": "ON",
            "title": "?????? ??? ????",
            "details": [],
        }

    async def fake_get_water_status():
        return {
            "operator": "??????????????????????",
            "type": "WATER_STATUS",
            "has_outage": False,
            "message": "?????????? ??????????? ??? ??????????? ???? ?????",
        }

    monkeypatch.setattr("app.api.get_my_status", fake_get_my_status)
    monkeypatch.setattr("app.api.get_water_status", fake_get_water_status)

    result = await get_mobile_home(operator="naftogaz", group="2.1")

    assert result["overall_status"] == "ON"
    assert len(result["sections"]) == 2
    assert result["sections"][0]["source"]["group"] == "2.1"


@pytest.mark.asyncio
async def test_get_mobile_home_can_skip_water(monkeypatch):
    async def fake_get_my_status(**kwargs):
        return {
            "operator": "naftogaz",
            "has_outage": False,
            "status": "ON",
            "title": "?????? ??? ????",
        }

    async def fail_get_water_status():
        raise AssertionError("water endpoint should not be called")

    monkeypatch.setattr("app.api.get_my_status", fake_get_my_status)
    monkeypatch.setattr("app.api.get_water_status", fail_get_water_status)

    result = await get_mobile_home(include_water=False)

    assert [section["id"] for section in result["sections"]] == ["electricity"]


def test_mobile_home_route_validates_operator_length():
    response = client.get("/api/v1/mobile/home?operator=x")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
