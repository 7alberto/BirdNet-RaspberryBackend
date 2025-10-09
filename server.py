from flask import Flask, jsonify, send_file, abort, request
import h5py
import numpy as np
from datetime import datetime
import os
import psutil
import time 

app = Flask(__name__)
AUDIO_FOLDER = "/home/giaco/recordings"

@app.route('/api/system_metrics')
def get_system_metrics():
    cpu_usage = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    ram_usage = ram.percent
    disk = psutil.disk_usage('/')
    disk_usage = disk.percent

    try:
        temp_file = '/sys/class/thermal/thermal_zone0/temp'
        if os.path.exists(temp_file):
            with open(temp_file, 'r') as f:
                temp_raw = f.read()
                temperature = int(temp_raw) / 1000.0
        else:
            temperature = 'N/A' 
    except (IOError, ValueError):
         temperature = 'N/A'

    status_file = "./birdnet_logs/birdnet-live.status"
    is_recording = False
    max_inactive_seconds = 30

    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                last_timestamp_str = f.read().strip()
                last_timestamp = float(last_timestamp_str)
                current_time = time.time()
                print(current_time - last_timestamp)
                if current_time - last_timestamp <= max_inactive_seconds:
                    is_recording = True
        except:
            is_recording = False

    metrics = { 'cpu_usage': cpu_usage, 
                'ram_usage': ram_usage, 
                'disk_usage': disk_usage, 
                'temperature': temperature,
                'is_recording': is_recording }

    return jsonify(metrics)

@app.route('/api/birds/classifications')
def get_recent_classifications():
    try:
        since_ts = int(request.args.get("since", 0))
        until_ts = int(request.args.get("until", 0))
        if since_ts == 0 or until_ts == 0:
            return jsonify({"error": "Both since and until parameters are required"}), 400
        if since_ts > until_ts:
            return jsonify({"error": "since timestamp <= until timestamp"}), 400
        with h5py.File('results.h5', 'r') as f:
            if 'detections' not in f:
                return jsonify([])
            ds = f['detections']
            filtered_data = ds[(ds["start_time"] >= since_ts) & (ds["start_time"] <= until_ts)]
            results = []
            for record in filtered_data:
                results.append({
                    'filename': record['filename'].decode('utf-8'),
                    'start_time': record["start_time"],
                    'duration': record['duration'],
                    'species': record['species'].decode('utf-8'),
                    'confidence': float(record['confidence'])
                })
            return jsonify(results)
    except ValueError:
        return jsonify({'error': 'Invalid timestamp format. It must be a number.'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/birds/audio/<ts>")
def get_audio_by_timestamp(ts):
    audio_file_path = os.path.join(AUDIO_FOLDER, f"{ts}.wav")
    if not os.path.exists(audio_file_path):
        abort(404)
    return send_file(audio_file_path, as_attachment=False)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

