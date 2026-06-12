# conftest.py - shared fixtures for pytest

import pytest
import mongomock
import fakeredis

@pytest.fixture
def mock_mongo_db():
    """Fixture that provides an in‑memory MongoDB using mongomock.
    Returns a database instance named ``test_space_telemetry``.
    """
    client = mongomock.MongoClient()
    return client["test_space_telemetry"]

@pytest.fixture
def mock_redis_client():
    """Fixture that provides an in‑memory Redis client using fakeredis.
    Configured with ``decode_responses=True`` to mimic typical string handling.
    """
    return fakeredis.FakeRedis(decode_responses=True)
