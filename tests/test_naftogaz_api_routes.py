from app.api import get_naftogaz_addresses, get_naftogaz_groups, get_operators


def test_get_operators():
    assert get_operators() == [
        {
            "id": "naftogaz",
            "name": "Нафтогаз Тепло",
            "status_url": "/api/v1/my-status?operator=naftogaz&group={group}",
            "selection": "group",
        },
        {
            "id": "loe",
            "name": "Львівобленерго",
            "status_url": "/api/v1/my-status?operator=loe&city={city}&street={street}&building={building}",
            "selection": "address",
        },
    ]


def test_get_naftogaz_addresses_filters_by_group():
    addresses = get_naftogaz_addresses("2.1")

    assert addresses
    assert all(address["group"] == "2.1" for address in addresses)
    assert {
        "group": "2.1",
        "type": "street",
        "city": "Новояворівськ",
        "name": "50-річчя УПА",
        "buildings": ["1", "3", "5"],
    } in addresses


def test_get_naftogaz_groups_includes_group_addresses():
    groups = get_naftogaz_groups()
    group = next(item for item in groups if item["id"] == "2.1")

    assert group["name"] == "Група 2.1"
    assert group["addresses"]
    assert all(address["group"] == "2.1" for address in group["addresses"])
