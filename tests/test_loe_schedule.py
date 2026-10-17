from app.loe_schedule import parse_loe_schedule


def test_parse_loe_schedule_reads_group_intervals_and_date():
    html = """
    <p>Графік погодинних відключень на 17.10.2026</p>
    <p>Інформація станом на 10:59 17.10.2026</p>
    <p>Група 1.1. Електроенергії немає з 20:00 до 22:30.</p>
    <p>Група 4.2. Електроенергії немає з 10:00 до 12:00, з 21:00 до 22:30.</p>
    <p>Група 5.2. Електроенергії є</p>
    """

    result = parse_loe_schedule(html)

    assert result["date"] == "2026-10-17"
    assert result["updated_at"] == "10:59 17.10.2026"
    assert result["groups"] == {
        "1.1": ["20:00-22:30"],
        "4.2": ["10:00-12:00", "21:00-22:30"],
        "5.2": [],
    }
