import os
from pathlib import Path


def load_local_env(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_local_env()

CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/s/nya_merezhi")

CITY_ID = os.getenv("CITY_ID", "novoyavorivsk")
CITY_NAME = os.getenv("CITY_NAME", "Новояворівськ")
REGION = os.getenv("REGION", "Львівська область")
OPERATOR = os.getenv("OPERATOR", "Нафтогаз Тепло")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Kyiv")
