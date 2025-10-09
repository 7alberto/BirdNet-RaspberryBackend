# Record to 15 second files with arecord, then analyze.

from subprocess import Popen
import sys
import signal
from datetime import datetime, timedelta
from pprint import pprint
import numpy as np
import h5py

import json
import os
import logging
from collections import defaultdict

import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


RECORDING_DIR = "./recordings"
STATUS_FILE_PATH = "./birdnet_logs/birdnet-live.status"
custom_model_path = "./custom_classifier/model.tflite"
custom_labels_path = "./custom_classifier/model_Labels.txt"

def get_mic_card():
    try:
        with open("/proc/asound/cards", "r") as f:
            for line in f:
                if "sndrpihifiberry" in line:
                    return line.strip().split()[0]
    except FileNotFoundError:
        print("Error: /proc/asound/cards not found. Could not set the microphone")
    except Exception as e:
        print(f"Error while retrieving mic info: {e}")
    return None

def update_recording_status(status_file_path):
    try:
        with open(status_file_path, "w") as f:
            f.write(str(time.time()))
    except Exception as e:
        print(f"Error while trying to write on status file: {e}")

# sudo systemctl stop birdnet.service
# journalctl -u birdnet.service -f
def save_to_hdf5(data, h5_path="results.h5"):
    # timestamp = datetime.fromtimestamp(float(timestamp_str))
    dt = np.dtype([
        ("filename", "S50"),
        ("start_time", "f8"),
        ("duration", "f8"),
        ("species", "S50"),
        ("confidence", "f8"),
    ])
    detections = [
        (data["filename"],
         data['timestamp'] + det['start_time'],
         det["end_time"] - det["start_time"],
         det["label"].encode('utf-8'), 
         det["confidence"])
        for det in data.get('detections', [])
    ]

    logging.info("Saving h5 file...")
    with h5py.File(h5_path, "a") as f:
        if "detections" not in f:
            f.create_dataset("detections", data=np.array(detections, dtype=dt), maxshape=(None,), chunks=True)
        else:
            ds = f["detections"]
            old_size = ds.shape[0]
            ds.resize((old_size + len(detections),))
            ds[old_size:] = np.array(detections, dtype=dt)

        f.attrs["sample_rate"] = 48000

def unify_detections(detections):
    summary = defaultdict(list)
    # !: assumendo che sia ordinato per start_time
    for det in detections:
        summary[det["label"]].append((det["start_time"], det['confidence']))
    # print('summary: ', summary)
    final = []
    for species, records in summary.items():
        start_time = records[0][0]
        last_time = start_time
        total_conf = records[0][1]
        count = 1
        for (current_time, conf) in records[1:]:
            diff = current_time - last_time
            if diff > 6:
                final.append({
                    'label': species,
                    'confidence': total_conf / count,
                    'start_time': start_time,
                    'end_time': last_time + 3.0,
                })
                start_time = current_time
                last_time = current_time
                count = 1
                total_conf = conf
                continue
            last_time = current_time
            total_conf += conf
            count += 1
        # ultimo segmento rimast
        final.append({
            'label': species,
            'confidence': total_conf / count,
            'start_time': start_time,
            'end_time': last_time + 3.0
        })
    return final


def on_analyze_complete(recording):
    # print("detections: ", recording.detections)
    unified_detections = unify_detections(recording.detections)

    data = {
        "detections": unified_detections,
        "filename": int(os.path.basename(recording.path).split('.')[0]),
        "timestamp": int(os.path.basename(recording.path).split('.')[0]),
    }

    # print("rielaborazione: ", data['detections'])

    # json_path = recording.path.replace(".wav", f".{recording.analyzer.name}.json")
    # with open(json_path, "w") as f:
    #     json.dump(data, f, indent=2)
    #     logging.info(f"Saved detection in: {json_path}")
    save_to_hdf5(data)

def on_analyze_file_complete(recording_list):
    update_recording_status(STATUS_FILE_PATH)


def on_error(recording, error):
    logging.error("An exception occurred: {} in {}".format(error, recording.path))

def preanalyze(recording):
    filename = recording.filename
    timestamp_str = filename.split('.')[0]
    dt = datetime.fromtimestamp(float(timestamp_str))
    recording.date = dt

def main():
    recording_dir = RECORDING_DIR
    DURATION_SECS = 12

    card_number = get_mic_card()
    if card_number is None:
        print("Microphone not found!")
        return
    print("Using Microphone from card: ", card_number)

    def signal_handler(sig, frame):
        logger.info("Received termination signal, stopping processes...")
        if RECORD_PROCESS:
            RECORD_PROCESS.terminate()
            RECORD_PROCESS.wait()
            logger.info("arecord process terminated")
        logger.info("Exiting live_birdnet...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    arecord_command_list = [
        "arecord",
        "-D", f"plughw:{get_mic_card()},0",
        "-f", "S16_LE",
        "-c", "2",
        "-r", "48000",
        "-t", "wav",
        "--max-file-time", f"{DURATION_SECS}",
        "--use-strftime",
        f"{recording_dir}/%s.wav",
    ]

    RECORD_PROCESS = Popen(arecord_command_list)
    logger.info(f"arecord started with PID: {RECORD_PROCESS.pid}")
    logger.info(f"Recording to directory: {recording_dir}")
    logger.info(f"Audio duration: {DURATION_SECS} seconds")


    from birdnetlib.watcher import DirectoryWatcher
    from birdnetlib.analyzer_lite import LiteAnalyzer
    from birdnetlib.analyzer import Analyzer
    from birdnetlib import Recording


    logging.info("Starting Analyzers...")
    analyzer = Analyzer(classifier_labels_path=custom_labels_path, classifier_model_path=custom_model_path)
    analyzers = [analyzer]

    logging.info("Starting Watcher")

    directory = recording_dir
    watcher = DirectoryWatcher(
        directory,
        analyzers=analyzers,
        sensitivity=1
    )
    watcher.recording_preanalyze = preanalyze
    watcher.on_analyze_complete = on_analyze_complete
    watcher.on_analyze_file_complete = on_analyze_file_complete
    watcher.on_error = on_error
    watcher.watch()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.error("KeyboardInterrupt")
    except Exception as e:
        logging.error("Exception")
        logging.error(e)
