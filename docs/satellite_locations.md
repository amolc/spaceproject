# Component Detail: Real-Time Orbital Tracking & Connection Manager

This document describes the design, Redis data structures, and algorithms used to support real-time geospatial location queries and subscriber link states.

---

## 1. Database Role (Redis)

Operational orbit routing decisions are time-critical:
* Satellites travel at approximately **7.8 km/s** in Low Earth Orbit (LEO), meaning their lines of sight change rapidly.
* Routing algorithms require finding active satellites in sub-millisecond ranges to prevent internet packet drops.

We utilize **Redis** because:
* **Sub-Millisecond Read/Write**: In-memory speeds support real-time geospatial updates and queries.
* **Native Geospatial Commands**: Built-in support for Geohash indexing and radial lookups.
* **Atomic Operations**: Thread-safe operations prevent connection counter race conditions.

---

## 2. Redis Data Structures & Key Designs

We deploy three distinct Redis structures, managed in [connections/orbit_service.py](file:///Users/amolc/2026/spaceinternet/connections/orbit_service.py):

```
       [Redis Keyspace]
       ├── "satellite_locations" ──────────────────► Geospatial ZSET (GEOADD)
       │                                              - Member: "55001" (Geohash 52-bit)
       │                                              - Member: "55002" (Geohash 52-bit)
       │
       ├── "satellite_meta:55001" ─────────────────► HASH (HSET)
       │                                              - speed_kms: 7.6
       │                                              - altitude_km: 550
       │                                              - updated_at: "2026-06-09T01:00:00"
       │
       └── "satellite_connections:55001" ──────────► STRING Counter (INCR/DECR)
                                                      - Value: 42
```

### 2.1 Geospatial Index (`ZSET`)
* **Key**: `satellite_locations`
* **Command**: `GEOADD satellite_locations longitude latitude norad_id`
* **Internal Behavior**: Redis converts the (longitude, latitude) coordinates into a 52-bit **Geohash** integer. This integer is inserted into a Sorted Set (ZSET) where the score is the geohash value. This enables range searches along a single-dimensional index.

### 2.2 Satellite Metadata Hash
* **Key**: `satellite_meta:{norad_id}`
* **Fields**: `latitude`, `longitude`, `altitude_km`, `speed_kms`, `updated_at`
* **Why**: The geospatial index only holds coordinates. Supplementary values (speed, altitude, timestamp) are stored in this metadata hash for quick lookups.

### 2.3 Subscriber Connections Counter
* **Key**: `satellite_connections:{norad_id}`
* **Type**: String representing an integer.
* **Why**: Managed using atomic commands `INCR` and `DECR` to ensure thread safety when multiple clients connect/disconnect simultaneously.

---

## 3. Core Algorithms & Operations

### 3.1 Geospatial Line-Of-Sight Search
To route connection requests, ground terminals run a nearest-satellite query:
```python
r.georadius(
    'satellite_locations',
    longitude=lon,
    latitude=lat,
    radius=radius_km,
    unit='km',
    withdist=True,
    withcoord=True
)
```
1. Redis performs a quick index range scan on the `satellite_locations` Sorted Set.
2. It filters satellites falling within the radius circle using distance calculations (Haversine formula).
3. The results are returned sorted from closest to farthest.

### 3.2 Thread-Safe Link Allocation
When subscriber terminals request connection, the application calls `increment_active_connections`:
```python
def increment_active_connections(norad_id):
    r = get_redis_client()
    return r.incr(f"satellite_connections:{norad_id}")
```
* **Thread Safety**: Because `INCR` is an atomic, single-threaded operations loop in Redis, it guarantees that concurrent link requests never trigger race conditions (e.g. over-subscribing a satellite beyond capacity).

---

## 4. Production Persistence Configuration

To guarantee no connection state or mapping details are lost during container recycles or server restarts, Redis is configured with:
1. **Append-Only File (AOF)**: Enabled with `appendfsync everysec` for durability.
2. **RDB Snapshots**: Standard background snapshotting configured as a secondary recovery route.

---

## 5. Sequence Diagram

This sequence diagram illustrates real-time coordinate caching, geospatial radius routing lookup, and subscriber link increments:

```mermaid
sequenceDiagram
    actor Sat as Satellite Terminal
    participant Django as Django REST API
    database Redis as Redis Cache

    Note over Sat, Redis: Geospatial Positioning & Cache Workflow

    Sat->>Django: POST /api/orbit/update/ (Lat/Lon/Altitude/Speed)
    activate Django
    Django->>Redis: GEOADD satellite_locations lon lat norad_id
    activate Redis
    Redis-->>Django: Added/Updated
    deactivate Redis
    Django->>Redis: HSET satellite_meta:norad_id mapping={lat, lon, alt, speed, updated_at}
    activate Redis
    Redis-->>Django: Success
    deactivate Redis
    Django-->>Sat: HTTP 200 OK (caching confirmed)
    deactivate Django

    actor User as Ground Station Terminal
    User->>Django: GET /api/orbit/nearest/?lat=X&lon=Y&radius=Z
    activate Django
    Django->>Redis: GEORADIUS satellite_locations lon lat Z km withdist withcoord
    activate Redis
    Redis-->>Django: List of [norad_id, distance, coords]
    deactivate Redis
    loop for each norad_id
        Django->>Redis: HGETALL satellite_meta:norad_id
        activate Redis
        Redis-->>Django: Metadata dict
        deactivate Redis
        Django->>Redis: GET satellite_connections:norad_id
        activate Redis
        Redis-->>Django: Counter value
        deactivate Redis
    end
    Django-->>User: HTTP 200 OK (JSON nearest satellites with status/connections)
    deactivate Django
```

