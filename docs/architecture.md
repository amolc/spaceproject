# Space Internet Master Architecture Specification

This document details the system architecture, requirements, and SLA parameters for the **Space Internet Service Provider & Telemetry Tracking System** (`spaceinternet`).

---

## 1. System Requirements

### 1.1 Functional Requirements (FR)
1. **Registry Operations (PostgreSQL)**:
   * System administrators must be able to register, modify, and retire satellite metadata (name, NORAD ID, planned orbit altitude, inclination).
   * System administrators must be able to register ground stations with geographic coordinates (latitude, longitude) and throughput bandwidth capacities.
   * Ground station connection locks and bandwidth capacity must adjust dynamically.
2. **Real-time Orbital Propagation (Redis & Background Worker)**:
   * The system must run a background SGP4-based propagation worker that periodically (every 5 seconds) calculates satellite latitude, longitude, speed, and altitude.
   * Coordinates must be cached in a geospatial search index.
3. **High-Frequency Telemetry Ingestion (MongoDB & Kafka)**:
   * The ingestion pipeline must decouple client requests from database insertions by routing vitals streams (CPU, temperature, battery levels, signal-to-noise ratio, throughput) through a message queue ingestion buffer (Apache Kafka or RabbitMQ).
   * Asynchronous workers must read from the queue and perform high-speed batch writes to MongoDB.
   * Historical vitals must be queryable chronologically for diagnostic dashboards.
4. **Geospatial Nearest-Routing and Mesh (ISL) Queries (Redis)**:
   * Subscribers or ground stations must be able to discover all active satellites within their line-of-sight cone (radius in km), calculated with oblate spheroid curvature equations.
   * The system must route requests dynamically across a simulated inter-satellite link (ISL) mesh network, balancing latency (shortest path via Dijkstra/A*) and connection load.
5. **Connection Session Tracker & Handover (Redis)**:
   * The system must track active subscriber counts per satellite using atomic `INCR`/`DECR` operations.
   * The system must execute predictive handovers to pre-allocate links before the active satellite drops below a ground terminal's local horizon.

### 1.2 Non-Functional Requirements (NFR)
1. **Low Latency Geospatial Routing**:
   * Nearest-satellite lookup requests (line-of-sight and routing queries) must return responses within **sub-50ms** at the 99th percentile (p99).
2. **High Write Throughput & Backpressure Ingestion**:
   * Telemetry ingestion pipelines must support up to **10,000 writes/second** under load. Backpressure from the database must be absorbed by the message broker queues.
3. **Elasticity, Scalability & Memory Management**:
   * The telemetry logs store (MongoDB) and geospatial cache (Redis) must scale horizontally.
   * Memory allocations must be bounded (e.g. Redis container capped, with a `volatile-lru` eviction policy for location updates and transient states).
4. **Data Isolation & Relational Safety**:
   * Relational operational state must be strictly separated from high-volume logging data to prevent locking. Concurrency control (optimistic/pessimistic lock retries) must protect ground station capacity records.
5. **Resiliency and Graceful Degradation**:
   * Circuit breaker patterns must prevent system cascades during database outages.
   * High availability (99.99% lookup availability SLA) must be supported by Redis Sentinel and MongoDB Replica Sets.

### 1.3 High-Performance Runtime Execution (PyPy JIT Recommendation)
To sustain high-frequency math calculations (SGP4 orbital propagation loops) and process heavy batch telemetry insertions, the Python background runtime should utilize **[PyPy](https://pypy.org/features.html)** rather than standard CPython:
* **Just-In-Time (JIT) Compiler**: Translates heavy loops into machine code, delivering significant speedups for CPU-bound propagation logic and telemetry JSON serialization.
* **Low-Latency Generational Garbage Collection**: Utilizes a highly optimized, non-blocking GC schema that avoids execution pauses, preventing telemetry packet delivery jitter.
* **Reduced Memory Footprint**: Objects in PyPy are represented more compactly, lowering memory footprint under massive satellite counts.

---

## 2. Hybrid Application Framework Design

To maximize developer velocity, relational consistency, and real-time asynchronous throughput, the system employs a **dual-framework Python hybrid architecture**:

```
        [Client Requests]
        ├── Administration, Auth, Registry CRUD (PostgreSQL)
        │    └── Django App Server (WSGI / Gunicorn)
        │
        └── High-Frequency, Low-Latency Endpoints (Redis / Kafka)
             └── FastAPI App Server (ASGI / Uvicorn)
```

### 2.1 Django Admin & Registry Server (WSGI)
* **Role**: Serves the relational metadata CRUD endpoints (`/api/satellites/`, `/api/ground-stations/`), administrative user interfaces, authentication protocols, and database migration routines.
* **Database Target**: PostgreSQL.
* **Why**: Django's robust built-in admin panel, Django REST Framework, and secure ORM migration systems are perfect for handling relational business models that change infrequently but demand absolute integrity.

### 2.2 FastAPI Real-Time Server (ASGI)
* **Role**: Exposes high-speed, asynchronous endpoints for telemetry ingestion (`/api/telemetry/ingest/`), real-time geospatial nearest routing lookups (`/api/orbit/nearest/`), websocket telemetry dashboards (`/ws/live/`), and predictive handovers.
* **Database Targets**: Redis cache and the Kafka/RabbitMQ ingestion broker.
* **Why**: Built on ASGI (Starlette and Uvicorn), FastAPI handles concurrency with extremely low overhead, yielding sub-millisecond route resolution. Its asynchronous capabilities allow it to process tens of thousands of requests per second concurrently without blocking.
* **Integration**: Both frameworks share access to the same PostgreSQL (read-only for FastAPI) and Redis configurations, keeping the systems unified.

---

## 3. CAP Theorem Alignment & DB Choices

The three databases are distributed across the CAP (Consistency, Availability, Partition Tolerance) spectrum according to their workloads:

```
            CONSISTENCY (C)
               /        \
              /          \
             /  Postgres  \
            /     (CP/CA)  \
           /                \
 AVAILABILITY (A) -------- PARTITION TOLERANCE (P)
     [Redis (AP)]          [MongoDB (AP/CP)]
```

* **PostgreSQL (CP/CA Focus)**: 
  * *Rationale*: Relational data (satellites, ground stations, user subscription billing) requires absolute transactional ACID consistency. If a partition occurs, we prioritize data correctness over partial writes.
* **MongoDB (CP/AP Configurable)**:
  * *Rationale*: Telemetry data represents a write-heavy append-only log. We write with `w: 1` concern for high-speed writes (AP focus), but can escalate write concern to `majority` (CP focus) for critical alert payloads.
* **Redis (AP Focus)**:
  * *Rationale*: Geospatial search and active link counters are highly dynamic. If a node fails, we prioritize low-latency access and availability of position tracking over strict, global replication consistency, since orbital coordinates stale in seconds anyway.
* **Message Ingestion Queue (Kafka/RabbitMQ - CP/AP Configurable)**:
  * *Rationale*: Ingestion buffers must maintain telemetry durability. Under high pressure, they act as the primary backpressure absorber, decoupling API requests from downstream database writes.

---

## 4. SLA & Data Tiering Considerations

### 4.1 Service Level Agreements (SLA)
* **Geospatial Lookup Availability**: **99.99%** uptime.
* **Telemetry Data Persistence Success**: **99.999%** of received packets must be saved.
* **API Ingestion Rate Limiting**: Up to 100 requests/sec per satellite terminal.

### 4.2 Data Retention & Tiering Strategy
Because satellites stream vast quantities of telemetry, we use a three-tiered storage model to prevent database inflation:

| Data Class | Database | Retention Period | Action / Lifecycle |
|---|---|---|---|
| **Hot Coordinates** | Redis | 60 Seconds (sliding) | Replaced on every telemetry cycle. Expired via TTL if a satellite goes silent. |
| **Warm Telemetry** | MongoDB | 30 Days | Stored as time-series documents. Expired using MongoDB TTL Indexes. |
| **Cold Aggregates** | PostgreSQL | Indefinite | A Celery-beat/cron worker aggregates MongoDB telemetry (averages, peak loads) into Postgres for archival reports. |

---

## 5. Component File Reference
* Master Architecture: [architecture.md](file:///Users/amolc/2026/spaceproject/docs/architecture.md)
* Relational Registry details: [satellite_registry.md](file:///Users/amolc/2026/spaceproject/docs/satellite_registry.md)
* Telemetry details: [satellite_telemetry.md](file:///Users/amolc/2026/spaceproject/docs/satellite_telemetry.md)
* Geolocation details: [satellite_locations.md](file:///Users/amolc/2026/spaceproject/docs/satellite_locations.md)
* Testing details: [testing.md](file:///Users/amolc/2026/spaceproject/docs/testing.md)


