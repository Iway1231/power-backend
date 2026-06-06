import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


@pytest.fixture(scope="session")
def project_root():
    return ROOT_DIR
