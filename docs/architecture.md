# Space Internet Master Architecture Specification

This document details the system architecture, requirements, and SLA parameters for the **Space Internet Service Provider & Telemetry Tracking System** (`spaceinternet`).

---

## 1. System Requirements

### 1.1 Functional Requirements (FR)
1. **Registry Operations (PostgreSQL)**:
   * System administrators must be able to register, modify, and retire satellite metadata (name, NORAD ID, planned orbit altitude, inclination).
   * System administrators must be able to register ground stations with geographic coordinates (latitude, longitude) and throughput bandwidth capacities.
2. **Real-time Orbital Propagation (Redis)**:
   * Satellites must continuously push their current latitude, longitude, speed, and altitude to the telemetry system.
   * The system must update and cache these positions in a geospatial search index.
3. **High-Frequency Telemetry Ingestion (MongoDB)**:
   * Satellites must send vitals streams (CPU, temperature, battery levels, signal-to-noise ratio, throughput) which are stored as logs.
   * Historical vitals must be queryable chronologically for graphing and diagnostic charts.
4. **Geospatial Nearest-Routing queries (Redis)**:
   * Subscribers or ground stations must be able to query the system with their GPS coordinates and discover all active satellites within their line-of-sight cone (radius in km).
   * Results must be returned sorted by proximity.
5. **Connection Session Tracker (Redis)**:
   * The system must track active subscriber counts per satellite using atomic increment/decrement actions when terminals establish or tear down links.

### 1.2 Non-Functional Requirements (NFR)
1. **Low Latency Geospatial Routing**:
   * Nearest-satellite lookup requests (line-of-sight queries) must return responses within **sub-50ms** at the 99th percentile (p99).
2. **High Write Throughput**:
   * Telemetry ingestion pipelines must support up to **10,000 writes/second** to handle massive constellations without bottlenecking the network.
3. **Elasticity and Scalability**:
   * The telemetry logs store (MongoDB) and geospatial cache (Redis) must scale horizontally as new orbital shells are deployed.
4. **Data Isolation**:
   * Relational operational state must be strictly separated from high-volume logging data to prevent database locking and slow transactions.

---

## 2. CAP Theorem Alignment & DB Choices

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

---

## 3. SLA & Data Tiering Considerations

### 3.1 Service Level Agreements (SLA)
* **Geospatial Lookup Availability**: **99.99%** uptime.
* **Telemetry Data Persistence Success**: **99.999%** of received packets must be saved.
* **API Ingestion Rate Limiting**: Up to 100 requests/sec per satellite terminal.

### 3.2 Data Retention & Tiering Strategy
Because satellites stream vast quantities of telemetry, we use a three-tiered storage model to prevent database inflation:

| Data Class | Database | Retention Period | Action / Lifecycle |
|---|---|---|---|
| **Hot Coordinates** | Redis | 60 Seconds (sliding) | Replaced on every telemetry cycle. Expired via TTL if a satellite goes silent. |
| **Warm Telemetry** | MongoDB | 30 Days | Stored as time-series documents. Expired using MongoDB TTL Indexes. |
| **Cold Aggregates** | PostgreSQL | Indefinite | A daily cron job aggregates MongoDB telemetry (averages, peak loads) into Postgres for archival reports. |

---

## 4. Component File Reference
* Master Architecture: [architecture.md](file:///Users/amolc/2026/spaceinternet/docs/architecture.md)
* Relational Registry details: [satellite_registry.md](file:///Users/amolc/2026/spaceinternet/docs/satellite_registry.md)
* Telemetry details: [satellite_telemetry.md](file:///Users/amolc/2026/spaceinternet/docs/satellite_telemetry.md)
* Geolocation details: [satellite_locations.md](file:///Users/amolc/2026/spaceinternet/docs/satellite_locations.md)
