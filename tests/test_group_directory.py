from app.group_directory import (
    infer_groups_for_address,
    infer_settlements_for_address,
    list_naftogaz_addresses,
)


def test_infer_group_for_shklo_and_kurortna():
    assert infer_groups_for_address("вул. Курортна смт. Шкло") == ["1.2"]


def test_infer_group_for_lis_and_okilky():
    assert infer_groups_for_address("с. Ліс та с. Окілки") == ["1.2"]


def test_infer_settlements_for_lis_and_okilky():
    assert infer_settlements_for_address("с. Ліс та с. Окілки") == [
        {"name": "с. Ліс", "naftogaz": {"group": "1.2"}},
        {"name": "с. Окілки", "naftogaz": {"group": "1.2"}},
    ]


def test_infer_settlement_without_known_group():
    assert infer_settlements_for_address("с. Прилбичі") == [
        {"name": "с. Прилбичі"},
    ]


def test_infer_multiple_community_settlements_without_groups():
    assert infer_settlements_for_address("с. Бердихів та с. Молошковичі") == [
        {"name": "с. Бердихів"},
        {"name": "с. Молошковичі"},
    ]


def test_list_naftogaz_addresses_by_group():
    addresses = list_naftogaz_addresses("2.1")

    assert {
        "group": "2.1",
        "type": "street",
        "city": "Новояворівськ",
        "name": "Січових Стрільців",
        "buildings": ["1", "2", "4", "6"],
    } in addresses
    assert all(address["group"] == "2.1" for address in addresses)


def test_list_naftogaz_addresses_includes_settlements():
    addresses = list_naftogaz_addresses("1.2")

    assert {
        "group": "1.2",
        "type": "settlement",
        "name": "Окілки",
        "buildings": None,
    } in addresses
