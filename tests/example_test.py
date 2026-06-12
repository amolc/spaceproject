# tests/example_test.py

"""Tests demonstrating the mock fixtures defined in `tests/conftest.py`.
These tests cover:
1. An in‑memory MongoDB instance using `mongomock`.
2. An in‑memory Redis client using `fakeredis`.
"""

import pytest


def test_mock_mongo_db(mock_mongo_db):
    """Simple CRUD check against the mongomock fixture.
    The fixture provides a ``Database`` object. We create a collection,
    insert a document, and verify we can retrieve it.
    """
    collection = mock_mongo_db["demo_collection"]
    document = {"name": "satellite", "norad_id": 12345}
    # Insert the document
    insert_result = collection.insert_one(document)
    assert insert_result.inserted_id is not None

    # Retrieve and verify the document
    fetched = collection.find_one({"_id": insert_result.inserted_id})
    assert fetched is not None
    assert fetched["name"] == "satellite"
    assert fetched["norad_id"] == 12345


def test_mock_redis_client(mock_redis_client):
    """Validate basic Redis operations using the fakeredis fixture.
    We test ``geoadd``, ``geopos``, and ``setnx`` behaviours.
    """
    client = mock_redis_client

    # Geo add a satellite location
    added = client.geoadd("satellite_locations", 10.0, 20.0, "sat-001")
    # ``geoadd`` returns the number of elements added
    assert added == 1

    # Verify the position
    position = client.geopos("satellite_locations", "sat-001")
    assert position == [(20.0, 10.0)]  # Note: returns (lat, lng)

    # Test setnx – should set the key only if it does not exist
    first_set = client.setnx("connection_counter:sat-001", 42)
    assert first_set is True
    second_set = client.setnx("connection_counter:sat-001", 99)
    assert second_set is False
    # Value should remain the first one
    value = client.get("connection_counter:sat-001")
    assert int(value) == 42
