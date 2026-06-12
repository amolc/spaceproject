import sys
import subprocess
import time
import psutil

def _kill_port(port):
    for p in psutil.process_iter(['pid']):
        try:
            for c in p.connections(kind='inet'):
                if c.laddr.port == port:
                    print(f"[PRE‑KILL] Terminating process {p.pid} listening on port {port}")
                    p.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

def check_databases():
    print("Verifying database connections...")
    result = subprocess.run(["./venv/bin/python3", "check_and_setup.py"])  # existing script handles DB checks
    if result.returncode != 0:
        print("\n[STARTUP ERROR] Database connection check failed.")
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
    check_databases()
    run_migrations()
    print("Launching Django Administrative Registry Server (Port 8000)...")
    try:
        # Pre‑kill any process already listening on the Django port
        _kill_port(8000)
        django_proc = subprocess.Popen(
            ["./venv/bin/python3", "manage.py", "runserver", "127.0.0.1:8000"],
            # Let Django output appear in console for debugging
            stdout=None,
            stderr=None,
        )
        print("Django server started. PID:", django_proc.pid)
        # Periodically report memory usage while the server runs
        try:
            while True:
                time.sleep(1)
                if django_proc.poll() is None:
                    proc = psutil.Process(django_proc.pid)
                    mem = proc.memory_info()
                    rss_mb = mem.rss / (1024 * 1024)
                    percent = proc.memory_percent()
                    print(f"[MEMORY] PID {django_proc.pid} ({django_proc.args[0]}) - RSS: {rss_mb:.2f} MB ({percent:.2f}%)")
                else:
                    print(f"\n[WARNING] Django process terminated with code {django_proc.returncode}.")
                    break
        except KeyboardInterrupt:
            print("\nShutting down Django server...")
            django_proc.terminate()
            django_proc.wait()
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nShutting down Django server...")
        django_proc.terminate()
        django_proc.wait()
        sys.exit(0)

if __name__ == '__main__':
    main()
