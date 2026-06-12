#!/usr/bin/env python3
import sys
import subprocess
import time
import psutil

# Helper to pre‑kill any existing propagation worker process
def _kill_worker():
    for p in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmd = p.info.get('cmdline') or []
            if any('propagation_worker.py' in part for part in cmd):
                print(f"[PRE‑KILL] Terminating existing propagation worker PID {p.pid}")
                p.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue


def main():
    print("Launching Background SGP4 Orbit Propagation Worker...")
    try:
        # Pre‑kill any existing propagation worker process
        _kill_worker()
        worker_proc = subprocess.Popen(
            ["./venv/bin/python3", "worker/propagation_worker.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("Propagation worker started. PID:", worker_proc.pid)
        # Periodic memory reporting loop
        try:
            while True:
                time.sleep(1)
                if worker_proc.poll() is None:
                    proc = psutil.Process(worker_proc.pid)
                    mem = proc.memory_info()
                    rss_mb = mem.rss / (1024 * 1024)
                    percent = proc.memory_percent()
                    print(f"[MEMORY] PID {worker_proc.pid} ({worker_proc.args[0]}) - RSS: {rss_mb:.2f} MB ({percent:.2f}%)")
                else:
                    print(f"\n[WARNING] Propagation worker terminated with code {worker_proc.returncode}.")
                    break
        except KeyboardInterrupt:
            print("\nShutting down propagation worker...")
            worker_proc.terminate()
            worker_proc.wait()
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nShutting down propagation worker...")
        worker_proc.terminate()
        worker_proc.wait()
        sys.exit(0)

if __name__ == '__main__':
    main()
