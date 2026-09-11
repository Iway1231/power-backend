import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_reject_invalid_url():
    with pytest.raises(ValidationError):
        Settings(channel_url="telegram.example")


def test_settings_reject_invalid_port():
    with pytest.raises(ValidationError):
        Settings(port=70000)


def test_settings_accept_production_configuration(tmp_path):
    settings = Settings(
        environment="production",
        log_format="json",
        data_dir=tmp_path,
    )

    assert settings.environment == "production"
    assert settings.data_dir == tmp_path


def test_settings_accept_api_key_configuration():
    settings = Settings(api_key="secret", api_key_required=True)

    assert settings.api_key == "secret"
    assert settings.api_key_required is True
