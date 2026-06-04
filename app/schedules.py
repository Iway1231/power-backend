# app/schedules.py

GROUP_SCHEDULES = {
    ("Новояворівськ", "Нафтогаз Тепло"): {
        "00:00-04:00": ["1.1", "1.2"],
        "04:00-08:00": ["2.1", "2.2"],
        "08:00-12:00": ["3.1", "3.2"],
        "12:00-16:00": ["4.1", "4.2"],
        "16:00-20:00": ["5.1", "5.2"],
        "20:00-23:59": ["6.1", "6.2"],
    }
}


def get_group_schedule(city: str, operator: str) -> dict | None:
    return GROUP_SCHEDULES.get((city, operator))
