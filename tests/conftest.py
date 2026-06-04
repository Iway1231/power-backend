import os
import pytest

@pytest.fixture(scope="session")
def project_root():
    return os.path.dirname(os.path.dirname(__file__))
