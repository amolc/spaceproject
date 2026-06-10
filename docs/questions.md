# Project Documentation Gap Analysis & Questions

This document tracks the coverage, gaps, and open design/implementation questions regarding key topics in the **Space Internet Service Provider & Telemetry Tracking System** (`spaceinternet`) documentation.

---

## 1. Memory Management
* **Current Coverage**: Discusses Redis as an in-memory database in [satellite_locations.md](file:///Users/amolc/2026/spaceproject/docs/satellite_locations.md) and mentions MongoDB in-memory sorting and TTL-based document expiration in [satellite_telemetry.md](file:///Users/amolc/2026/spaceproject/docs/satellite_telemetry.md).
* **Gaps**: Missing low-level memory allocation, eviction policy configurations, and caching limits.
* **Open Questions**:
  1. What is the designated Redis eviction policy (e.g., `volatile-lru`, `noeviction`) when the in-memory store reaches its maximum memory limit?
  2. What are the memory limits and sizing specifications allocated to the Redis and MongoDB containers or instances under maximum constellation load?
  3. Are there specific memory pooling or garbage collection (GC) optimizations required for the Python/Django runtime to handle high-frequency telemetry requests?

---

## 2. Modelling & Data Flow
* **Current Coverage**: Relational models for Satellite and GroundStation are shown in [satellite_registry.md](file:///Users/amolc/2026/spaceproject/docs/satellite_registry.md). Redis structures and NoSQL telemetry documents are defined in [satellite_locations.md](file:///Users/amolc/2026/spaceproject/docs/satellite_locations.md) and [satellite_telemetry.md](file:///Users/amolc/2026/spaceproject/docs/satellite_telemetry.md). Diagrams depict how data flows from terminals through the REST API to the DBs.
* **Gaps**: Detailed schema validations, data archiving pipeline specifications, and backpressure handling.
* **Open Questions**:
  1. How is backpressure handled when the ingestion API receives telemetry writes exceeding the PostgreSQL validation or MongoDB insertion limits?
  2. What is the mechanism for the "daily cron job" that aggregates MongoDB data into PostgreSQL (e.g., Celery task, cron utility, custom management command)?
  3. Are there transactional boundaries or lock-retry mechanisms designed for the relational database when ground station throughput capacities or subscriber link states change?

---

## 3. Simulation & Trajectory Simulator
* **Current Coverage**: Mentions "Real-time Orbital Propagation" (satellites pushing positions to Redis) in [architecture.md](file:///Users/amolc/2026/spaceproject/docs/architecture.md) and orbital inclination/altitude parameters in [satellite_registry.md](file:///Users/amolc/2026/spaceproject/docs/satellite_registry.md).
* **Gaps**: Completely missing any description of an orbital trajectory simulator or propagation math engine.
* **Open Questions**:
  1. Is there an internal Python-based trajectory simulator (e.g., using SGP4 or Keplerian orbital propagation), or does the system rely entirely on external satellite telemetry payloads?
  2. How are simulated satellite coordinates generated for local testing? Is there a coordinate generator script or standard TLE (Two-Line Element) input set?
  3. What is the update frequency of the simulator compared to the telemetry ingestion rate (e.g., continuous math propagation vs. 3-5s pushes)?

---

## 4. Performance & Real-Time Scenarios
* **Current Coverage**: Outlines SLA requirements (p99 latency < 50ms, 10,000 writes/sec) and database indexing strategies in [architecture.md](file:///Users/amolc/2026/spaceproject/docs/architecture.md).
* **Gaps**: Actual performance benchmark results and edge-case handling under network instability.
* **Open Questions**:
  1. How does the system handle real-time edge cases such as delayed or out-of-order telemetry packets from satellites?
  2. What are the caching and circuit-breaker designs when connection to Redis or MongoDB fails? Does the system fallback to PostgreSQL or degrade gracefully?
  3. Have load/stress testing benchmarks been run to prove that the current architecture sustains the target write volume of 10,000 writes/second?

---

## 5. Algorithm Design
* **Current Coverage**: Mentions geospatial lookup using Redis `GEORADIUS` (Haversine formula) and atomic connection increment/decrement in [satellite_locations.md](file:///Users/amolc/2026/spaceproject/docs/satellite_locations.md).
* **Gaps**: Lacks details on specific routing algorithms or geometric intersection math.
* **Open Questions**:
  1. How is the line-of-sight cone calculated? Does it incorporate Earth curvature, ground station elevation constraints, or minimum elevation angles?
  2. When selecting satellites for routing, does the algorithm incorporate factors like active connection count (load balancing) and bandwidth capacity, or does it sort purely by distance?

---

## 6. Testing
* **Current Coverage**: Not covered in the project documentation.
* **Gaps**: Missing unit, integration, and load testing procedures.
* **Open Questions**:
  1. What testing frameworks are configured for this project (e.g., `pytest`, Django's test suite, or mock frameworks for MongoDB/Redis)?
  2. How do we mock external telemetry streams, geospatial queries, and connection handshakes during test suites?
  3. Are there performance and stress-testing suites configured to validate SLA/latency constraints?
