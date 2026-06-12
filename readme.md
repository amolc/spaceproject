# Space Internet & Telemetry Tracking System

This is the central repository for the **Space Internet Service Provider & Telemetry Tracking System** (`spaceinternet`). The system consists of a relational registry (PostgreSQL), high-frequency telemetry logs storage (MongoDB), and a real-time geospatial coordinate propagation cache (Redis).

---

## Documentation Index
* [Master Architecture Specification](file:///Users/amolc/2026/spaceproject/docs/architecture.md)
* [Relational Registry Component Detail](file:///Users/amolc/2026/spaceproject/docs/satellite_registry.md)
* [Real-Time Orbital Tracking Detail](file:///Users/amolc/2026/spaceproject/docs/satellite_locations.md)
* [High-Frequency Telemetry Detail](file:///Users/amolc/2026/spaceproject/docs/satellite_telemetry.md)
* [System Testing Specification Detail](file:///Users/amolc/2026/spaceproject/docs/testing.md)
* [Gap Analysis & Open Questions](file:///Users/amolc/2026/spaceproject/docs/questions.md)
* [Project Enhancements & Suggestions](file:///Users/amolc/2026/spaceproject/docs/suggestions.md)
* [Automatic Satellite Data Ingestion Guide](file:///Users/amolc/2026/spaceproject/docs/satellite_data_sources.md)

---

## How to Create and Set Up the Project

Follow these steps to initialize and build the `spaceinternet` project from scratch.

### 1. Prerequisites
Ensure the following services are installed and running locally or in your environment:
* **Python** (version 3.10 or higher recommended)
* **PostgreSQL**
* **MongoDB**
* **Redis**

### 2. Initialize Virtual Environment & Dependencies
1. Create a Python virtual environment:
   ```bash
   python3 -m venv venv
   ```
2. Activate the virtual environment:
   ```bash
   source venv/bin/activate
   ```
3. Install required packages (Django, Django REST Framework, FastAPI, Uvicorn, database drivers, and helper libraries):
   ```bash
   pip install django djangorestframework psycopg2-binary pymongo redis fastapi uvicorn
   ```

### 3. Initialize the Django Project
1. Create the Django project in the current directory:
   ```bash
   django-admin startproject spaceinternet .
   ```
2. Create Django applications for each database/domain component:
   * **satellites** (Handles PostgreSQL metadata registry):
     ```bash
     python manage.py startapp satellites
     ```
   * **telemetry** (Handles MongoDB telemetry log ingestion):
     ```bash
     python manage.py startapp telemetry
     ```
   * **connections** (Handles Redis geospatial caching and connection counters):
     ```bash
     python manage.py startapp connections
     ```

### 3.1 Initialize the FastAPI App
Create a separate module directory `fastapi_app` for real-time, low-overhead ASGI processing:
1. Create `fastapi_app/main.py`:
   ```python
   from fastapi import FastAPI
   from fastapi.middleware.cors import CORSMiddleware
   
   app = FastAPI(title="Space Internet High-Frequency API")
   
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["*"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   
   @app.get("/api/orbit/nearest/")
   async def get_nearest(lat: float, lon: float):
       # High-speed Redis geospatial range lookup implementation
       pass
   ```

### 4. Database Setup & Configurations

#### A. PostgreSQL Configuration
Update `spaceinternet/settings.py` with your database credentials:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'space_internet',
        'USER': 'your_postgres_user',
        'PASSWORD': 'your_postgres_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

#### B. MongoDB Configuration
Create a service client config (e.g., `telemetry/mongo_client.py`):
```python
from pymongo import MongoClient
from django.conf import settings

client = MongoClient('mongodb://localhost:27017/')
db = client['space_telemetry']
```

#### C. Redis Configuration
Create a connection utility (e.g., `connections/redis_client.py`):
```python
import redis

def get_redis_client():
    return redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
```

### 5. Define Models & Serializers
1. Define your Postgres models (`Satellite`, `GroundStation`) in `satellites/models.py`. Refer to [satellite_registry.md](file:///Users/amolc/2026/spaceproject/docs/satellite_registry.md) for details.
2. Build DRF serializers and views in `satellites/serializers.py` and `satellites/views.py`.
3. Set up telemetry pipelines and API controllers under `telemetry/` and geospatial querying under `connections/`.

### 6. Apply Database Migrations & Run
1. Generate and execute PostgreSQL schema migrations:
   ```bash
   python manage.py makemigrations satellites
   python manage.py migrate
   ```
2. Start the Django development server (administrative CRUD & ORM on port 8000):
   ```bash
   python manage.py runserver 127.0.0.1:8000
   ```
3. Start the FastAPI development server (high-throughput endpoints & WebSockets on port 8001):
   ```bash
   uvicorn fastapi_app.main:app --host 127.0.0.1 --port 8001 --reload
   ```
   The administrative endpoints will be accessible at `http://127.0.0.1:8000/api/` and the high-speed telemetry/routing endpoints at `http://127.0.0.1:8001/api/`.
