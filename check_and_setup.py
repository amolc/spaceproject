import sys
import json
import psycopg
import redis
import pymongo

def check_postgres():
    # Try common default configurations on macOS
    configs = [
        {"host": "localhost", "port": 5432, "user": "postgres", "password": "10gXWOqeaf!", "dbname": "postgres"},
        {"host": "localhost", "port": 5432, "user": "postgres", "password": "10gXWOqeaf", "dbname": "postgres"},
        {"host": "localhost", "port": 5432, "user": "amolc", "password": "10gXWOqeaf!", "dbname": "postgres"},
        {"host": "localhost", "port": 5432, "user": "amolc", "password": "10gXWOqeaf", "dbname": "postgres"},
        {"user": "amolc", "dbname": "postgres"},
        {"user": "postgres", "dbname": "postgres"},
        {"host": "localhost", "port": 5432, "user": "postgres", "password": "", "dbname": "postgres"},
        {"host": "localhost", "port": 5432, "user": "amolc", "password": "", "dbname": "postgres"},
    ]
    
    conn = None
    active_config = None
    for config in configs:
        try:
            conn = psycopg.connect(**config)
            active_config = config
            print(f"Connected to PostgreSQL using: user={config['user']}, dbname={config['dbname']}")
            break
        except Exception as e:
            print(f"Failed to connect with config {config}: {e}")
            continue
            
    if not conn:
        print("Error: Could not connect to PostgreSQL with any default configuration.")
        return None
        
    try:
        conn.autocommit = True
        cur = conn.cursor()
        
        # Check if database spaceproject exists
        cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'spaceproject';")
        exists = cur.fetchone()
        
        if not exists:
            print("Creating database 'spaceproject'...")
            cur.execute("CREATE DATABASE spaceproject;")
            print("Database 'spaceproject' created successfully!")
        else:
            print("Database 'spaceproject' already exists.")
            
        cur.close()
        conn.close()
        
        # Update active config to point to spaceproject db
        target_config = active_config.copy()
        target_config["dbname"] = "spaceproject"
        return target_config
    except Exception as e:
        print(f"Error during PostgreSQL database setup: {e}")
        if conn:
            conn.close()
        return None

def check_redis():
    try:
        r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=2)
        r.ping()
        print("Connected to Redis on localhost:6379 successfully!")
        return {"host": "localhost", "port": 6379, "db": 0}
    except Exception as e:
        print(f"Error connecting to Redis: {e}")
        return None

def check_mongodb():
    try:
        client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
        # Force a connection check
        client.server_info()
        print("Connected to MongoDB on localhost:27017 successfully!")
        return {"uri": "mongodb://localhost:27017/", "db_name": "space_telemetry"}
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return None

def main():
    print("=== Database Setup & Verification ===")
    pg_config = check_postgres()
    redis_config = check_redis()
    mongo_config = check_mongodb()
    
    if not (pg_config and redis_config and mongo_config):
        print("\nVerification Failed. Please make sure PostgreSQL, MongoDB, and Redis are running locally.")
        sys.exit(1)
        
    config_data = {
        "postgres": pg_config,
        "redis": redis_config,
        "mongodb": mongo_config
    }
    
    with open("install.json", "w") as f:
        json.dump(config_data, f, indent=4)
        
    print("\nVerification Successful! Connection details saved to 'install.json'.")

if __name__ == '__main__':
    main()
