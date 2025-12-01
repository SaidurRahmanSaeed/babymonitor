# monitor_resources.py
import csv
import time
from datetime import datetime
from pathlib import Path
import subprocess

import psutil

LOG_PATH = Path("logs/resource_log.csv")


def get_cpu_temp_c() -> float:
    """
    Try vcgencmd first; fallback to /sys/class/thermal if needed.
    """
    try:
        out = subprocess.check_output(
            ["vcgencmd", "measure_temp"],
            text=True
        ).strip()
        # out looks like: temp=42.0'C
        return float(out.split("=")[1].split("'")[0])
    except Exception:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return int(f.read()) / 1000.0
        except Exception:
            return -1.0


def monitor(interval_sec=5):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Write header if file doesn't exist
    new_file = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["timestamp", "cpu_percent", "memory_percent", "temp_c"])

        print("[Monitor] Logging every", interval_sec, "seconds. Ctrl+C to stop.")
        try:
            while True:
                ts = datetime.now().isoformat(timespec="seconds")
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
                temp = get_cpu_temp_c()
                writer.writerow([ts, cpu, mem, temp])
                f.flush()
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            print("\n[Monitor] Stopped.")


if __name__ == "__main__":
    monitor(interval_sec=5)
