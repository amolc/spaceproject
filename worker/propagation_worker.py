import os
import sys
import time
import json
import random
import requests
import pymongo
import redis
import psycopg2
from datetime import datetime, timezone
from skyfield.api import load, wgs84, EarthSatellite

# Seeding constants
SEED_GROUND_STATIONS = [
    {"station_id": "GS-SG", "name": "GS-Singapore", "latitude": 1.3521, "longitude": 103.8198, "elevation_m": 15.0, "status": "ONLINE", "bandwidth_capacity_gbps": 100.0},
    {"station_id": "GS-LDN", "name": "GS-London", "latitude": 51.5074, "longitude": -0.1278, "elevation_m": 35.0, "status": "ONLINE", "bandwidth_capacity_gbps": 120.0},
    {"station_id": "GS-NYC", "name": "GS-NewYork", "latitude": 40.7128, "longitude": -74.0060, "elevation_m": 10.0, "status": "ONLINE", "bandwidth_capacity_gbps": 150.0},
    {"station_id": "GS-SYD", "name": "GS-Sydney", "latitude": -33.8688, "longitude": 151.2093, "elevation_m": 25.0, "status": "ONLINE", "bandwidth_capacity_gbps": 80.0},
    {"station_id": "GS-CPT", "name": "GS-CapeTown", "latitude": -33.9249, "longitude": 18.4241, "elevation_m": 12.0, "status": "ONLINE", "bandwidth_capacity_gbps": 90.0},
    {"station_id": "GS-TKY", "name": "GS-Tokyo", "latitude": 35.6762, "longitude": 139.6503, "elevation_m": 40.0, "status": "ONLINE", "bandwidth_capacity_gbps": 200.0},
    {"station_id": "GS-PAR", "name": "GS-Paris", "latitude": 48.8566, "longitude": 2.3522, "elevation_m": 35.0, "status": "ONLINE", "bandwidth_capacity_gbps": 110.0},
    {"station_id": "GS-SAO", "name": "GS-SaoPaulo", "latitude": -23.5505, "longitude": -46.6333, "elevation_m": 760.0, "status": "ONLINE", "bandwidth_capacity_gbps": 130.0},
    {"station_id": "GS-BOM", "name": "GS-Mumbai", "latitude": 19.0760, "longitude": 72.8777, "elevation_m": 14.0, "status": "ONLINE", "bandwidth_capacity_gbps": 140.0},
    {"station_id": "GS-REK", "name": "GS-Reykjavik", "latitude": 64.1466, "longitude": -21.9426, "elevation_m": 15.0, "status": "ONLINE", "bandwidth_capacity_gbps": 75.0},
    {"station_id": "GS-ANC", "name": "GS-Anchorage", "latitude": 61.2181, "longitude": -149.9003, "elevation_m": 38.0, "status": "ONLINE", "bandwidth_capacity_gbps": 85.0},
    {"station_id": "GS-HNL", "name": "GS-Honolulu", "latitude": 21.3069, "longitude": -157.8583, "elevation_m": 6.0, "status": "ONLINE", "bandwidth_capacity_gbps": 95.0},
    {"station_id": "GS-DXB", "name": "GS-Dubai", "latitude": 25.2048, "longitude": 55.2708, "elevation_m": 16.0, "status": "ONLINE", "bandwidth_capacity_gbps": 160.0},
    {"station_id": "GS-LOS", "name": "GS-Lagos", "latitude": 6.5244, "longitude": 3.3792, "elevation_m": 41.0, "status": "ONLINE", "bandwidth_capacity_gbps": 115.0},
    {"station_id": "GS-GOH", "name": "GS-Nuuk", "latitude": 64.1743, "longitude": -51.7373, "elevation_m": 70.0, "status": "ONLINE", "bandwidth_capacity_gbps": 85.0},
    {"station_id": "GS-AKL", "name": "GS-Auckland", "latitude": -36.8485, "longitude": 174.7633, "elevation_m": 20.0, "status": "ONLINE", "bandwidth_capacity_gbps": 125.0},
]


FALLBACK_TLES = """
ISS (ZARYA)
1 25544U 98067A   26161.50000000  .00016717  00000-0  10285-3 0  9009
2 25544  51.6405 281.3814 0004561 113.8402 246.3312 15.49845612  1008
TIANGONG
1 48274U 21035A   26161.50000000  .00005717  00000-0  10285-3 0  9009
2 48274  41.5805 181.3814 0004561  93.8402 146.3312 15.58845612  1008
STARLINK-30302
1 55001U 22001A   26161.50000000  .00001234  00000-0  10285-3 0  9009
2 55001  53.0000 120.0000 0001000  50.0000 200.0000 15.05000000  1008
STARLINK-30303
1 55002U 22001B   26161.50000000  .00001234  00000-0  10285-3 0  9009
2 55002  53.0000 150.0000 0001000  60.0000 210.0000 15.05000000  1008
STARLINK-30304
1 55003U 22001C   26161.50000000  .00001234  00000-0  10285-3 0  9009
2 55003  53.0000 180.0000 0001000  70.0000 220.0000 15.05000000  1008
STARLINK-30305
1 55004U 22001D   26161.50000000  .00001234  00000-0  10285-3 0  9009
2 55004  53.0000 210.0000 0001000  80.0000 230.0000 15.05000000  1008
STARLINK-30306
1 55005U 22001E   26161.50000000  .00001234  00000-0  10285-3 0  9009
2 55005  53.0000 240.0000 0001000  90.0000 240.0000 15.05000000  1008
STARLINK-30307
1 55006U 22001F   26161.50000000  .00001234  00000-0  10285-3 0  9009
2 55006  53.0000 270.0000 0001000 100.0000 250.0000 15.05000000  1008
"""

def load_db_config():
    install_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "install.json")
    if not os.path.exists(install_path):
        print("Error: install.json not found. Run check_and_setup.py first.")
        sys.exit(1)
    with open(install_path) as f:
        return json.load(f)

def seed_database(pg_params):
    print("Checking if database seeding is required...")
    try:
        conn = psycopg2.connect(**pg_params)
        cur = conn.cursor()
        
        # Seed ground stations incrementally if they don't exist yet
        seeded_count = 0
        for gs in SEED_GROUND_STATIONS:
            cur.execute("SELECT 1 FROM satellites_groundstation WHERE station_id = %s;", (gs["station_id"],))
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO satellites_groundstation 
                    (station_id, name, latitude, longitude, elevation_m, status, bandwidth_capacity_gbps, created_at, updated_at) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW());
                    """,
                    (gs["station_id"], gs["name"], gs["latitude"], gs["longitude"], gs["elevation_m"], gs["status"], gs["bandwidth_capacity_gbps"])
                )
                seeded_count += 1
        
        if seeded_count > 0:
            conn.commit()
            print(f"Seeded {seeded_count} new ground stations successfully!")
        else:
            print("Ground stations are already fully seeded.")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Seeding failed: {e}")
        sys.exit(1)

def seed_satellite_in_postgres(pg_params, name, norad_id, altitude, inclination):
    try:
        conn = psycopg2.connect(**pg_params)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM satellites_satellite WHERE norad_id = %s;", (norad_id,))
        exists = cur.fetchone()
        if not exists:
            cur.execute(
                """
                INSERT INTO satellites_satellite 
                (name, norad_id, status, orbit_altitude_km, inclination_deg, created_at, updated_at) 
                VALUES (%s, %s, 'ACTIVE', %s, %s, NOW(), NOW());
                """,
                (name, norad_id, altitude, inclination)
            )
            conn.commit()
            print(f"Registered satellite {name} ({norad_id}) in PostgreSQL.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Failed to register satellite {norad_id}: {e}")

def get_tles():
    print("Fetching active TLEs from CelesTrak...")
    cache_path = os.path.join(os.path.dirname(__file__), "tle_cache.txt")
    
    # Try different groups in order (Starlink is dense and best for Dijkstra mesh routing)
    urls = [
        "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle",
        "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle",
        "https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=tle"
    ]
    
    for url in urls:
        try:
            print(f"Attempting download from {url}...")
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            text = response.text
            
            # Check for CelesTrak throttling warning or empty content
            if "GP data has not updated" not in text and len(text) > 1000:
                print(f"Successfully downloaded TLEs from {url}!")
                # Write to cache
                try:
                    with open(cache_path, "w") as f:
                        f.write(text)
                except Exception as cache_err:
                    print(f"Failed to write cache: {cache_err}")
                return text
            else:
                print(f"Received rate-limit message or invalid content from {url}.")
        except Exception as e:
            print(f"Download from {url} failed: {e}")
            
    # Fallback to local cache if download failed
    if os.path.exists(cache_path):
        print(f"Offline: Reading TLE data from local cache file '{cache_path}'...")
        try:
            with open(cache_path) as f:
                return f.read()
        except Exception as cache_read_err:
            print(f"Failed to read cache: {cache_read_err}")
            
    print("No cache found. Using fallback hardcoded TLE data.")
    return FALLBACK_TLES

def parse_tles(tle_text):
    lines = [line.strip() for line in tle_text.split('\n') if line.strip()]
    satellites = []
    ts = load.timescale()
    
    # Process lines in groups of 3
    i = 0
    while i < len(lines) - 2:
        name = lines[i]
        line1 = lines[i+1]
        line2 = lines[i+2]
        
        # Check if line1 and line2 are valid TLE lines
        if line1.startswith('1 ') and line2.startswith('2 '):
            try:
                # Extract norad_id
                norad_id = line1[2:7].strip()
                # Create EarthSatellite object
                sat = EarthSatellite(line1, line2, name, ts)
                satellites.append({
                    "name": name,
                    "norad_id": norad_id,
                    "sat_obj": sat,
                    "line1": line1,
                    "line2": line2
                })
            except Exception:
                pass
            i += 3
        else:
            i += 1
            
    # Return limited set for performance (increased to 150 for dense routing mesh)
    return satellites[:150]

def main():
    config = load_db_config()
    pg_params = config["postgres"]
    r_conf = config["redis"]
    m_conf = config["mongodb"]
    
    # Run Seeding
    seed_database(pg_params)
    
    # Connect databases
    print("Connecting to Redis and MongoDB from worker...")
    try:
        r = redis.Redis(host=r_conf["host"], port=r_conf["port"], db=r_conf["db"], decode_responses=True)
        r.ping()
        mongo_client = pymongo.MongoClient(m_conf["uri"])
        mongo_db = mongo_client[m_conf["db_name"]]
        print("Worker successfully connected to Redis and MongoDB!")
    except Exception as e:
        print(f"Worker database connection check failed: {e}")
        sys.exit(1)
        
    # Get TLEs
    tle_text = get_tles()
    sat_list = parse_tles(tle_text)
    
    print(f"Propagating {len(sat_list)} satellites...")
    
    # Seed Satellites in Postgres
    for sat in sat_list:
        # We estimate altitude ~550km and inclination from TLE if possible
        try:
            inclination = float(sat["line2"][8:16].strip())
        except Exception:
            inclination = 53.0
        seed_satellite_in_postgres(pg_params, sat["name"], sat["norad_id"], 550.0, inclination)
        
    ts = load.timescale()
    
    # Propagation loop
    print("Starting propagation loop...")
    while True:
        loop_start = time.time()
        now = datetime.now(timezone.utc)
        t = ts.from_datetime(now)
        
        # We pipeline Redis operations to reduce TCP overhead
        pipe = r.pipeline()
        
        for sat in sat_list:
            sat_id = sat["norad_id"]
            sat_name = sat["name"]
            sat_obj = sat["sat_obj"]
            
            try:
                # 1. Propagate orbit
                geocentric = sat_obj.at(t)
                subpoint = wgs84.subpoint(geocentric)
                
                lat = float(subpoint.latitude.degrees)
                lon = float(subpoint.longitude.degrees)
                alt = float(subpoint.elevation.km)
                
                velocity_vector = geocentric.velocity.km_per_s
                speed_kms = float((velocity_vector[0]**2 + velocity_vector[1]**2 + velocity_vector[2]**2) ** 0.5)
                
                                # Check for wrap-around lon bounds (-180 to 180)
                if lon > 180:
                    lon -= 360
                elif lon < -180:
                    lon += 360

                # Validate latitude range for Redis GEOADD (-85.05112878 to 85.05112878)
                if -85.05112878 <= lat <= 85.05112878:
                    # 2. Update Redis Geospatial set & metadata hash
                    pipe.geoadd("satellite_locations", [lon, lat, sat_id])
                    pipe.hset(f"satellite_meta:{sat_id}", mapping={
                        "name": sat_name,
                        "latitude": lat,
                        "longitude": lon,
                        "altitude_km": alt,
                        "speed_kms": speed_kms,
                        "updated_at": now.isoformat()
                    })
                else:
                    print(f"[REDIS] Skipping GEOADD for sat {sat_id}: latitude {lat:.6f} out of bounds")
                # Add default connection count if not exists
                pipe.setnx(f"satellite_connections:{sat_id}", random.randint(15, 45))
                
                # 3. Simulate high-frequency telemetry ingestion directly to MongoDB/Local server
                # Pushing a telemetry frame to Mongo logs
                telemetry_doc = {
                    "norad_id": sat_id,
                    "timestamp": now,
                    "battery_temp_c": round(random.uniform(20.0, 35.0), 2),
                    "battery_soc_pct": round(random.uniform(70.0, 99.0), 1),
                    "cpu_usage_pct": round(random.uniform(10.0, 65.0), 1),
                    "signal_strength_dbm": round(random.uniform(-90.0, -50.0), 1),
                    "throughput_mbps": round(random.uniform(50.0, 350.0), 2),
                    "status_code": "OK"
                }
                mongo_db.satellite_telemetry.insert_one(telemetry_doc)
                
                # Also push ingestion frame to FastAPI server ingestion API
                # to trigger active websocket broadcasts!
                # We do this asynchronously/locally to trigger live websocket updates.
                try:
                    requests.post("http://127.0.0.1:8001/api/telemetry/ingest/", json={
                        "norad_id": sat_id,
                        "timestamp": now.isoformat(),
                        "battery_temp_c": telemetry_doc["battery_temp_c"],
                        "battery_soc_pct": telemetry_doc["battery_soc_pct"],
                        "cpu_usage_pct": telemetry_doc["cpu_usage_pct"],
                        "signal_strength_dbm": telemetry_doc["signal_strength_dbm"],
                        "throughput_mbps": telemetry_doc["throughput_mbps"],
                        "status_code": "OK"
                    }, timeout=0.2)
                except Exception:
                    pass # FastAPI server might not be listening yet, skip
                    
            except Exception as e:
                print(f"Failed to propagate satellite {sat_id}: {e}")
                
        # Execute Redis updates
        try:
            pipe.execute()
        except Exception as e:
            print(f"Redis pipeline execute failed: {e}")
            
        # Limit tick rate to 2 seconds
        elapsed = time.time() - loop_start
        sleep_time = max(0.1, 2.0 - elapsed)
        time.sleep(sleep_time)

if __name__ == '__main__':
    main()
