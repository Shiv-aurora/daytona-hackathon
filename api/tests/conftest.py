import pytest

from db.testing import open_test_database


@pytest.fixture
def database():
    with open_test_database() as db:
        yield db
