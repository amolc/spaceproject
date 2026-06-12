import os
import json
import asyncio
import math
import heapq
import pymongo
import redis
import psycopg
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Initialize FastAPI App
app = FastAPI(title="Space Internet High-Frequency API")

# Allow requests from any origin (e.g., localhost vs 127.0.0.1 mismatch)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global clients
redis_client = None
mongo_client = None
mongo_db = None
pg_conn_params = {}

# Active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # Clean up closed sockets on broadcast
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# Load connection settings from install.json
@app.on_event("startup")
def startup_db_connections():
    global redis_client, mongo_client, mongo_db, pg_conn_params
    
    install_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "install.json")
    if not os.path.exists(install_path):
        raise RuntimeError("install.json configuration not found. Run check_and_setup.py first.")
        
    with open(install_path) as f:
        config = json.load(f)
        
    # 1. Verify and connect to Postgres params
    pg_conn_params = config["postgres"]
    try:
        conn = psycopg.connect(**pg_conn_params)
        conn.close()
        print("FastAPI successfully connected to PostgreSQL!")
    except Exception as e:
        raise RuntimeError(f"FastAPI failed to connect to PostgreSQL: {e}")
        
    # 2. Verify and connect to Redis
    r_conf = config["redis"]
    try:
        redis_client = redis.Redis(host=r_conf["host"], port=r_conf["port"], db=r_conf["db"], decode_responses=True)
        redis_client.ping()
        print("FastAPI successfully connected to Redis!")
    except Exception as e:
        raise RuntimeError(f"FastAPI failed to connect to Redis: {e}")
        
    # 3. Verify and connect to MongoDB
    m_conf = config["mongodb"]
    try:
        mongo_client = pymongo.MongoClient(m_conf["uri"], serverSelectionTimeoutMS=2000)
        mongo_client.server_info()
        mongo_db = mongo_client[m_conf["db_name"]]
        print("FastAPI successfully connected to MongoDB!")
    except Exception as e:
        raise RuntimeError(f"FastAPI failed to connect to MongoDB: {e}")

# Ingestion Schema
class TelemetryPayload(BaseModel):
    norad_id: str
    timestamp: str
    battery_temp_c: float
    battery_soc_pct: float = Field(..., ge=0, le=100)
    cpu_usage_pct: float = Field(..., ge=0, le=100)
    signal_strength_dbm: float
    throughput_mbps: float = Field(..., ge=0)
    status_code: str = "OK"

# Telemetry Ingestion Endpoint
@app.post("/api/telemetry/ingest/")
async def ingest_telemetry(payload: TelemetryPayload):
    if mongo_db is None or redis_client is None:
        raise HTTPException(status_code=500, detail="Database services not initialized")
    
    try:
        # 1. Insert into MongoDB log store
        doc = payload.dict()
        doc["timestamp"] = pymongo.datetime.datetime.fromisoformat(payload.timestamp.replace("Z", "+00:00"))
        mongo_db.satellite_telemetry.insert_one(doc)
        
        # 2. Broadcast via WebSockets for real-time dashboard plotting
        # Include current connection stats from Redis if available
        conn_count = redis_client.get(f"satellite_connections:{payload.norad_id}")
        conn_count = int(conn_count) if conn_count else 0
        
        broadcast_data = {
            "type": "telemetry",
            "norad_id": payload.norad_id,
            "data": {
                "battery_temp_c": payload.battery_temp_c,
                "battery_soc_pct": payload.battery_soc_pct,
                "cpu_usage_pct": payload.cpu_usage_pct,
                "signal_strength_dbm": payload.signal_strength_dbm,
                "throughput_mbps": payload.throughput_mbps,
                "status_code": payload.status_code,
                "connection_count": conn_count
            }
        }
        await manager.broadcast(broadcast_data)
        
        return {"status": "success", "message": "Telemetry ingested"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest telemetry: {str(e)}")

# Get Ground Stations from Postgres
def get_ground_stations():
    conn = psycopg.connect(**pg_conn_params)
    cur = conn.cursor()
    cur.execute("SELECT station_id, name, latitude, longitude, bandwidth_capacity_gbps, status FROM satellites_groundstation WHERE status='ONLINE';")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    stations = []
    for r in rows:
        stations.append({
            "station_id": r[0],
            "name": r[1],
            "lat": r[2],
            "lon": r[3],
            "capacity": r[4]
        })
    return stations

# Dijkstra routing calculator helper
def dijkstra(graph, start, end):
    queue = [(0, start, [])]
    seen = set()
    while queue:
        (cost, node, path) = heapq.heappop(queue)
        if node in seen:
            continue
        seen.add(node)
        path = path + [node]
        if node == end:
            return cost, path
        for next_node, weight in graph.get(node, {}).items():
            if next_node not in seen:
                heapq.heappush(queue, (cost + weight, next_node, path))
    return float('inf'), []

# Geolocation distance utility
def calculate_distance_km(lat1, lon1, lat2, lon2):
    R = 6371.0 # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Geospatial Routing Lookup Endpoint
@app.get("/api/orbit/nearest/")
async def get_nearest_routing(lat: float, lon: float, radius: float = 3000.0):
    if redis_client is None:
        raise HTTPException(status_code=500, detail="Redis connection unavailable")
        
    try:
        # 1. Fetch nearest visible satellites from Redis geospatial search
        # returns list of members e.g. [norad_id, distance]
        nearby = redis_client.georadius("satellite_locations", lon, lat, radius, unit="km", withdist=True)
        
        # 2. Build Routing Graph
        graph = {}
        
        # Initialize nodes
        graph["client"] = {}
        graph["sink"] = {}
        
        # Add client -> visible satellite edges
        for item in nearby:
            sat_id = item[0]
            dist = float(item[1])
            # Check connection count for load balancing cost
            conn_count = redis_client.get(f"satellite_connections:{sat_id}")
            conn_cost = int(conn_count) * 15 if conn_count else 0
            graph["client"][sat_id] = dist + conn_cost
            
        # Get active satellites from locations ZSET
        all_active_sats = redis_client.zrange("satellite_locations", 0, -1, withscores=False)
        sat_positions = {}
        for sat_id in all_active_sats:
            pos = redis_client.geopos("satellite_locations", sat_id)
            if pos and pos[0]:
                sat_positions[sat_id] = (pos[0][1], pos[0][0]) # lat, lon
                
        # Inter-Satellite Links (ISL): connect adjacent satellites if within 2200 km
        for sat1, pos1 in sat_positions.items():
            if sat1 not in graph:
                graph[sat1] = {}
            for sat2, pos2 in sat_positions.items():
                if sat1 == sat2:
                    continue
                dist = calculate_distance_km(pos1[0], pos1[1], pos2[0], pos2[1])
                if dist < 4500.0:
                    conn_count = redis_client.get(f"satellite_connections:{sat2}")
                    conn_cost = int(conn_count) * 15 if conn_count else 0
                    graph[sat1][sat2] = dist + conn_cost
                    
        # Ground Stations -> Sink Node
        stations = get_ground_stations()
        for gs in stations:
            gs_id = gs["station_id"]
            if gs_id not in graph:
                graph[gs_id] = {}
            graph[gs_id]["sink"] = 0.0 # 0 cost to virtual sink
            
            # Connect visible satellites to ground stations (within 3500 km)
            # Find which satellites are near this ground station
            gs_nearby = redis_client.georadius("satellite_locations", gs["lon"], gs["lat"], 3500.0, unit="km", withdist=True)
            for item in gs_nearby:
                sat_id = item[0]
                dist = float(item[1])
                if sat_id not in graph:
                    graph[sat_id] = {}
                graph[sat_id][gs_id] = dist
                
        # Run Dijkstra to find shortest path from client terminal to the virtual sink (landing gs)
        cost, path = dijkstra(graph, "client", "sink")
        
        # Clean path to remove virtual sink
        final_path = path[:-1] if "sink" in path else path
        
        # Build path coordinates for 3D visualization
        path_coords = []
        path_coords.append({"name": "Terminal", "lat": lat, "lon": lon, "type": "terminal"})
        for node in final_path[1:]:
            if node in sat_positions:
                lat_s, lon_s = sat_positions[node]
                path_coords.append({"name": f"Sat {node}", "lat": lat_s, "lon": lon_s, "type": "satellite", "norad_id": node})
            else:
                # Ground Station
                gs_info = next((g for g in stations if g["station_id"] == node), None)
                if gs_info:
                    path_coords.append({"name": gs_info["name"], "lat": gs_info["lat"], "lon": gs_info["lon"], "type": "ground_station", "station_id": node})
                    
        return {
            "client": {"lat": lat, "lon": lon},
            "visible_satellites": [{"norad_id": s[0], "distance_km": round(float(s[1]), 2)} for s in nearby],
            "routing_cost": round(cost, 2) if cost != float('inf') else None,
            "routing_path": final_path[1:] if len(final_path) > 1 else [],
            "path_coordinates": path_coords
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Routing calculation failed: {str(e)}")

# WebSocket Connection Feed
@app.websocket("/ws/live/")
async def websocket_live_feed(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Periodic coordinate stream loop
        while True:
            # Fetch all active coordinates from Redis
            if redis_client is not None:
                sats = redis_client.zrange("satellite_locations", 0, -1)
                data_frame = []
                for sat_id in sats:
                    pos = redis_client.geopos("satellite_locations", sat_id)
                    meta = redis_client.hgetall(f"satellite_meta:{sat_id}")
                    conns = redis_client.get(f"satellite_connections:{sat_id}")
                    if pos and pos[0]:
                        data_frame.append({
                            "norad_id": sat_id,
                            "name": meta.get("name", f"Sat {sat_id}"),
                            "lon": pos[0][0],
                            "lat": pos[0][1],
                            "altitude_km": float(meta.get("altitude_km", 550.0)),
                            "speed_kms": float(meta.get("speed_kms", 7.6)),
                            "updated_at": meta.get("updated_at", ""),
                            "connection_count": int(conns) if conns else 0
                        })
                
                # Broadcast tracking frame
                await websocket.send_json({
                    "type": "coordinates",
                    "satellites": data_frame
                })
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

# Serve static dashboard frontend files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    
    @app.get("/", response_class=HTMLResponse)
    async def get_index():
        index_file = os.path.join(frontend_dir, "index.html")
        if os.path.exists(index_file):
            with open(index_file) as f:
                return f.read()
        return HTMLResponse("index.html not found", status_code=404)
