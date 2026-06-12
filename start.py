import sys
import os
import time
import subprocess
import psutil
def check_databases():
    print("Verifying database connections...")
    # Execute check_and_setup.py using virtualenv python
    result = subprocess.run(["./venv/bin/python3", "check_and_setup.py"])
    if result.returncode != 0:
        print("\n[STARTUP ERROR] Database connection check failed.")
        print("Please check that PostgreSQL, MongoDB, and Redis are running locally and try again.")
        sys.exit(1)
    print("All database connections verified successfully.")

def run_migrations():
    print("Running database migrations...")
    result = subprocess.run(["./venv/bin/python3", "manage.py", "migrate"])
    if result.returncode != 0:
        print("[STARTUP ERROR] Django database migrations failed.")
        sys.exit(1)
    print("Migrations completed.")

def main():
    print("=========================================================")
    print("   SPACE INTERNET & TELEMETRY TRACKING SYSTEM LAUNCHER   ")
    print("=========================================================\n")
    
    # 1. Run database connectivity verification
    check_databases()
    
    # 2. Run Django database migrations
    run_migrations()
    
    # 3. Launch the concurrent services
    processes = []
    try:
        # A. Start Django REST Registry Server
        print("Launching Django Administrative Registry Server (Port 8000)...")
        django_proc = subprocess.Popen(
            ["./venv/bin/python3", "manage.py", "runserver", "127.0.0.1:8000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        processes.append(django_proc)
        
        # B. Start FastAPI High-Performance API Server
        print("Launching FastAPI Real-Time API Server (Port 8001)...")
        fastapi_proc = subprocess.Popen(
            ["./venv/bin/python3", "-m", "uvicorn", "fastapi_app.main:app", "--host", "127.0.0.1", "--port", "8001"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        processes.append(fastapi_proc)
        
        # C. Start SGP4 Orbit Propagation Worker
        print("Launching Background SGP4 Orbit Propagation Worker...")
        worker_proc = subprocess.Popen(
            ["./venv/bin/python3", "worker/propagation_worker.py"]
        )
        processes.append(worker_proc)
        
        print("\nAll services started successfully!")
        print("-> Dashboard Web Interface is accessible at: http://127.0.0.1:8001/")
        print("-> Django Admin and API is accessible at:     http://127.0.0.1:8000/api/")
        print("Press Ctrl+C to terminate all servers.")
        
        # Keep launcher process alive
        while True:
            time.sleep(1)

            # Periodically report memory usage
            try:
                for p in processes:
                    if p.poll() is None:  # still running
                        proc = psutil.Process(p.pid)
                        mem = proc.memory_info()
                        rss_mb = mem.rss / (1024 * 1024)
                        percent = proc.memory_percent()
                        print(f"[MEMORY] PID {p.pid} ({p.args[0]}) - RSS: {rss_mb:.2f} MB ({percent:.2f}%)")
            except Exception as e:
                print(f"[MEMORY] Error retrieving memory usage: {e}")

            # Check if any process has terminated unexpectedly
            for p in processes:
                if p.poll() is not None:
                    print(f"\n[WARNING] Process {p.pid} terminated unexpectedly with code {p.returncode}.")
                    raise KeyboardInterrupt
                    
    except KeyboardInterrupt:
        print("\nShutting down all spaceinternet services...")
        for p in processes:
            try:
                p.terminate()
                p.wait(timeout=2)
                print(f"Terminated process: {p.pid}")
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        print("All services stopped.")
        sys.exit(0)

if __name__ == '__main__':
    main()
