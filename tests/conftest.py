import pytest

from psx_pipeline.fixtures import make_fixture


@pytest.fixture
def tables():
    return make_fixture(70)
