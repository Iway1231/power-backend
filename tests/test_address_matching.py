from app.address_matching import address_matches, extract_address_targets, extract_entity_targets
from app.parser import parse_power_text

TEXT_WITH_HEADINGS = """
У зв’язку з проведенням планових ремонтних робіт на трансформаторних підстанціях
19.09.2026 з 15:00 до 18:00 буде тимчасово припинено електропостачання за такими адресами та об’єктами:
📍 вул. Вербицького:
9а, 3;
📍 вул. Шухевича:
8, 11, 11а, 12;
📍 вул. Ю. Липи:
1, 1А, 3, 5, 7, 9.
"""


def test_extract_address_targets_with_house_lists():
    targets = extract_address_targets(TEXT_WITH_HEADINGS, city="Новояворівськ")

    assert {target["street"] for target in targets} == {
        "вербицького",
        "шухевича",
        "ю липи",
    }
    shukhevicha = next(target for target in targets if target["street"] == "шухевича")
    assert shukhevicha["buildings"] == ["11", "11A", "12", "8"]


def test_address_match_is_narrow_for_listed_buildings():
    target = {"city": "новояворівськ", "street": "шухевича", "buildings": ["8", "11A"]}

    assert address_matches(target, "Новояворівськ", "вул. Шухевича", "11-а")
    assert not address_matches(target, "Новояворівськ", "вул. Шухевича", "12")


def test_street_without_buildings_matches_whole_street():
    target = {"city": "новояворівськ", "street": "пасічника", "buildings": []}

    assert address_matches(target, "Новояворівськ", "Пасічника", "1")
    assert address_matches(target, "Новояворівськ", "Пасічника", "99")


def test_planned_outage_contains_structured_addresses():
    result = parse_power_text(TEXT_WITH_HEADINGS)

    assert result["type"] == "PLANNED_OUTAGE"
    interval = result["intervals"][0]
    assert interval["address_scope"] == "ADDRESSES"
    assert len(interval["addresses"]) == 3
ENTITY_OUTAGE = """
Увага! Тимчасове припинення електропостачання
У зв’язку з проведенням планових ремонтних робіт 10.08.2026 р. з 09:00 до 13:00 буде
тимчасово припинено електропостачання таких споживачів:
⚡ с. Стадники
⚡ Житловий масив «Синє очко»
⚡ Житловий масив К1
"""


def test_extract_entity_targets_from_residential_outage_notice():
    targets = extract_entity_targets(ENTITY_OUTAGE)

    assert {(target["type"], target["name"], target["group"]) for target in targets} == {
        ("settlement", "Стадники", "3.1"),
        ("residential_area", "Житловий масив «Синє очко»", "6.1"),
        ("residential_area", "Житловий масив К1", "6.1"),
    }


def test_planned_outage_assigns_all_entity_groups():
    result = parse_power_text(ENTITY_OUTAGE)
    interval = result["intervals"][0]

    assert interval["entity_scope"] == "ENTITIES"
    assert {item["group"] for item in interval["entities"]} == {"3.1", "6.1"}
    assert interval["naftogaz"] == {"groups": ["3.1", "6.1"]}
