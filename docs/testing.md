# Component Detail: System Testing Specification

This document details the testing frameworks, mocking strategies, and performance validation procedures configured for the Space Internet Service Provider and Telemetry Tracking System.

---

## 1. Testing Frameworks Setup

The project uses a hybrid test execution suite to validate both relational database operations and asynchronous storage layers:
1. **`pytest` & `pytest-django`**: The primary test runner for unit and integration tests.
2. **Django Test Suite**: Leveraged for isolated database transactions and model-level schema validations.
3. **Execution Commands**:
   * Run all unit tests:
     ```bash
     pytest
     ```
   * Run specific component integration tests (e.g., telemetry):
     ```bash
     pytest telemetry/tests/
     ```

---

## 2. Mocking & Dependency Isolation

Because the system relies on external databases (Redis, MongoDB) and API payloads, the test suite isolates dependencies using standard mocking libraries and test containers.

### 2.1 MongoDB Mocking
To test telemetry processing in isolation, the test suite utilizes `mongomock`, a library that simulates a MongoDB instance in memory:
```python
import mongomock
import pytest

@pytest.fixture
def mock_mongo_db():
    client = mongomock.MongoClient()
    return client['test_space_telemetry']
```
This avoids needing a running MongoDB server during fast unit tests.

### 2.2 Redis Mocking & Geospatial Queries
For geospatial and connection counter unit tests, we utilize `fakeredis`, which implements Redis commands in-memory:
```python
import fakeredis
import pytest

@pytest.fixture
def mock_redis_client():
    # fakeredis supports GEO commands, HSET, and INCR/DECR operations
    return fakeredis.FakeRedis(decode_responses=True)
```
Geospatial range lookups (`GEORADIUS` / `GEOADD`) are fully simulated by `fakeredis` without network overhead.

### 2.3 Integration Test Containers (Docker)
For full integration testing of database failovers, AOF persistence, and real-time clustering:
* **Docker Compose**: A dedicated test stack (`docker-compose.test.yml`) spins up real Redis, MongoDB, and PostgreSQL instances.
* **Test Isolation**: Each test run generates randomized test database names to prevent cross-contamination.

---

## 3. High-Throughput Performance & Stress Testing

To validate system SLA constraints (99.99% lookup uptime, sub-50ms p99 lookup latency, 10,000 writes/sec ingestion), the system relies on Locust and k6.

### 3.1 Locust Load Testing
Locust is used to simulate large-scale concurrent user traffic:
* **Satellite Terminals (Telemetry Streams)**: Simulates 10,000 concurrent satellites posting telemetry packets every 3–5 seconds through the Kafka ingestion endpoints.
* **Subscriber Terminals (Geospatial Queries)**: Simulates 50,000 concurrent subscribers calling `/api/orbit/nearest/` with randomized GPS coordinate parameters.
* **Sample locustfile configuration (`tests/locustfile.py`)**:
  ```python
  from locust import HttpUser, task, between
  import random

  class SpaceSubscriberUser(HttpUser):
      wait_time = between(0.1, 0.5)

      @task
      def get_nearest_satellites(self):
          lat = random.uniform(-90.0, 90.0)
          lon = random.uniform(-180.0, 180.0)
          self.client.get(f"/api/orbit/nearest/?lat={lat}&lon={lon}")
  ```

### 3.2 k6 Load Testing & Latency Profiles
k6 is utilized for sub-millisecond precision measurement of the geospatial routing latency profile:
* **Target SLO Validation**: Ensures that under high concurrency, the p99 response time for `/api/orbit/nearest/` remains strictly under 50ms.
* **Execution**:
  ```bash
  k6 run tests/performance_test.js
  ```
* **Output Analysis**: Metrics report average, p95, p99, and p99.9 latencies. Ingestion drop rates are graphed to ensure the Kafka broker buffer does not reject incoming payloads (retaining 99.999% persistence SLA).
