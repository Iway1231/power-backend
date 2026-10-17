import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


@pytest.fixture(scope="session")
def project_root():
    return ROOT_DIR


@pytest.fixture(scope="session")
def test_app():
    from app.config import SETTINGS
    from app.main import create_app

    settings = SETTINGS.model_copy(
        update={"environment": "test", "allowed_hosts": ["testserver", "localhost", "127.0.0.1"]}
    )
    return create_app(settings)
