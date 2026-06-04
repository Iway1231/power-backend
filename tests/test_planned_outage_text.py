from app.parser import parse_power_text


def test_planned_outage_text_message():
    text = """
    Увага! Тимчасове припинення електропостачання⚡️

    У зв'язку з проведенням планових робіт по очистці повітряної лінії 6кВ 4/5
    05.06.2026 р. з 09:00 до 17:00 буде припинено електропостачання
    споживачів по вул. Курортна смт. Шкло.
    ⚡️Просимо вибачення за тимчасові незручності.
    """

    result = parse_power_text(text)

    assert result["type"] == "PLANNED_OUTAGE"
    assert result["date"] == "2026-06-05"
    assert result["intervals"] == [
        {
            "from_time": "09:00",
            "to_time": "17:00",
            "status": "OFF",
            "address": "вул. Курортна смт. Шкло",
            "group": "1.2",
        }
    ]


def test_planned_outage_group_message():
    text = """
    Увага! Тимчасове припинення електропостачання⚡️

    У зв'язку з проведенням планових ремонтних робіт на трансформаторній підстанції
    28.05.2026 р. з 10:00 до 14:00 буде припинено електропостачання споживачів групи 3.2
    ⚡️Просимо вибачення за тимчасові незручності
    """

    result = parse_power_text(text)

    assert result["type"] == "PLANNED_OUTAGE"
    assert result["date"] == "2026-05-28"
    assert result["intervals"] == [
        {
            "from_time": "10:00",
            "to_time": "14:00",
            "status": "OFF",
            "group": "3.2",
        }
    ]


def test_planned_outage_textual_date_and_village_address():
    text = """
    Увага! Тимчасове припинення електропостачання ⚡

    У зв'язку з проведенням планових ремонтних робіт на одній із підстанцій, завтра
    19 травня 2026 року з 10:00 до 16:00 буде тимчасово припинено електропостачання
    для споживачів с. Ліс та с. Окілки.
    """

    result = parse_power_text(text)

    assert result["type"] == "PLANNED_OUTAGE"
    assert result["date"] == "2026-05-19"
    assert result["intervals"] == [
        {
            "from_time": "10:00",
            "to_time": "16:00",
            "status": "OFF",
            "address": "с. Ліс та с. Окілки",
            "group": "1.2",
        }
    ]
