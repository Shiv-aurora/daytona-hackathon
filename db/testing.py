"""Offline test databases. Tests never open external service connections."""

from collections.abc import Iterator
from contextlib import contextmanager

from db.bootstrap import ensure_indexes
from db.fakes import FakeDatabase


@contextmanager
def open_test_database(bootstrap: bool = True) -> Iterator[FakeDatabase]:
    db = FakeDatabase()
    if bootstrap:
        ensure_indexes(db)
    yield db
