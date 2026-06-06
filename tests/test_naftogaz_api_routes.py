from app.api import get_naftogaz_addresses


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
