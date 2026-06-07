import os

from app.config import load_local_env


def test_load_local_env_sets_missing_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_POWER_BACKEND_VALUE=hello\n", encoding="utf-8")
    monkeypatch.delenv("TEST_POWER_BACKEND_VALUE", raising=False)

    load_local_env(str(env_file))

    assert os.environ["TEST_POWER_BACKEND_VALUE"] == "hello"


def test_load_local_env_keeps_existing_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_POWER_BACKEND_VALUE=from_file\n", encoding="utf-8")
    monkeypatch.setenv("TEST_POWER_BACKEND_VALUE", "from_system")

    load_local_env(str(env_file))

    assert os.environ["TEST_POWER_BACKEND_VALUE"] == "from_system"
