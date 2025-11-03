import psutil
import csv
import time
import os
from datetime import datetime

INTERVAL_MINUTES = 5    # intervallo di raccolta (minuti)
FILE_NAME = "recorded_metrics.csv"  # cartella dove salvare i CSV

def get_system_metrics():
    try:
        cpu_usage = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
    except Exception as e:
        print(f"[WARN] Error while reading metrics: {e}")
        cpu_usage, ram, disk = "N/A", "N/A", "N/A"

    # Temperatura: funziona su Raspi, su PC è N/A
    temperature = "N/A"
    temp_file = "/sys/class/thermal/thermal_zone0/temp"
    if os.path.exists(temp_file):
        try:
            with open(temp_file, 'r') as f:
                temperature = int(f.read()) / 1000.0
        except Exception:
            pass

    return {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'cpu_usage': cpu_usage,
        'ram_usage': ram,
        'disk_usage': disk,
        'temperature': temperature
    }

def write_to_csv(data):
    try:
        file_exists = os.path.exists(FILE_NAME)
        with open(FILE_NAME, mode='a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(data)
    except Exception as e:
        print(f"[WARN] Error while writing on CSV: {e}")

def main():
    print(f"Recording every {INTERVAL_MINUTES} minutes")
    print(f"File will be saved in the '{FILE_NAME}' folder")

    while True:
        try:
            metrics = get_system_metrics()
            write_to_csv(metrics)
            print(f"[{metrics['timestamp']}] CPU {metrics['cpu_usage']}% | RAM {metrics['ram_usage']}% | Disk {metrics['disk_usage']}% | Temp {metrics['temperature']}")
        except Exception as e:
            print(f"[ERROR] Loop crashed: {e}")
        time.sleep(INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()
