#!/usr/bin/env python3
import sys
import subprocess
import time
import psutil

# Helper to pre‑kill any process listening on a given port (reuse same logic as in start_django)
def _kill_port(port):
    for p in psutil.process_iter(['pid']):
        try:
            for c in p.connections(kind='inet'):
                if c.laddr.port == port:
                    print(f"[PRE‑KILL] Terminating process {p.pid} listening on port {port}")
                    p.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

def main():
    print("Launching FastAPI Real-Time API Server (Port 8001)...")
    try:
        _kill_port(8001)
        fastapi_proc = subprocess.Popen(
            ["./venv/bin/python3", "-m", "uvicorn", "fastapi_app.main:app", "--host", "127.0.0.1", "--port", "8001"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("FastAPI server started. PID:", fastapi_proc.pid)
        # Periodic memory reporting
        try:
            while True:
                time.sleep(1)
                if fastapi_proc.poll() is None:
                    proc = psutil.Process(fastapi_proc.pid)
                    mem = proc.memory_info()
                    rss_mb = mem.rss / (1024 * 1024)
                    percent = proc.memory_percent()
                    print(f"[MEMORY] PID {fastapi_proc.pid} ({fastapi_proc.args[0]}) - RSS: {rss_mb:.2f} MB ({percent:.2f}%)")
                else:
                    print(f"\n[WARNING] FastAPI process terminated with code {fastapi_proc.returncode}.")
                    break
        except KeyboardInterrupt:
            print("\nShutting down FastAPI server...")
            fastapi_proc.terminate()
            fastapi_proc.wait()
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nShutting down FastAPI server...")
        fastapi_proc.terminate()
        fastapi_proc.wait()
        sys.exit(0)

if __name__ == '__main__':
    main()
