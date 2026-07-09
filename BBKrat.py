from __future__ import annotations

import sys
import time
import signal
from queue import Empty
from multiprocessing import Process, Queue
from influxdb import InfluxDBClient

from controller import control

def graceful_shutdown(signum, frame):
    print("Caught termination signal. Exiting.")
    sys.exit(0)

signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)

# ---------------- Grafana queue setup ----------------
client = InfluxDBClient(
    host='localhost',
    port=8086,
    database='BBKrat',
    use_udp=True,
    udp_port=8094
)

measurement_queue: Queue[dict[str, str | int | dict[str, float]]] = Queue(maxsize=2048)

# ---------------- Thread setup ----------------
def influx_writer(queue: Queue[dict[str, str | int | dict[str, float]]]):  # FIX: Accept queue as a parameter
    batch: list[dict[str, str | int | dict[str, float]]] = []
    MAX_BATCH = 1000
    FLUSH_MIN = 200
    FLUSH_MAX_LATENCY = 1.0
    MAX_BATCH_SIZE = 5000

    last_flush = time.monotonic()
    last_error_time = None

    while True:
        try:
            # Wait for at least one point
            metric = queue.get(timeout=1)
            batch.append(metric)

            # Drain whatever is available right now
            while len(batch) < MAX_BATCH:
                try:
                    batch.append(queue.get_nowait())
                except Empty:
                    break

            now = time.monotonic()
            if len(batch) >= FLUSH_MIN or (now - last_flush) >= FLUSH_MAX_LATENCY:
                try:
                    client.write_points(batch, time_precision="n")
                    batch.clear()
                    last_flush = now
                    last_error_time = None
                except Exception as e:
                    now = time.monotonic()
                    if last_error_time is None or (now - last_error_time) > 5:
                        print(f"Failed to write to InfluxDB: {e}")
                        last_error_time = now

                    if len(batch) > MAX_BATCH_SIZE:
                        print(f"WARNING: batch size {len(batch)} exceeded {MAX_BATCH_SIZE}. Dropping oldest points.")
                        batch = batch[-MAX_BATCH_SIZE:]  # keep only the most recent points
                    
                    # Back off slightly to avoid hammering InfluxDB
                    time.sleep(0.1)

        except Empty:
            # periodic flush even if low traffic
            if batch:
                try:
                    client.write_points(batch, time_precision="n")
                    batch.clear()
                    last_flush = time.monotonic()
                    last_error_time = None
                except Exception as e:
                    now = time.monotonic()
                    if last_error_time is None or (now - last_error_time) > 5:
                        print(f"Failed to write to InfluxDB (periodic): {e}")
                        last_error_time = now
                    
                    if len(batch) > MAX_BATCH_SIZE:
                        print(f"WARNING: batch size {len(batch)} exceeded {MAX_BATCH_SIZE}. Dropping oldest points.")
                        batch = batch[-MAX_BATCH_SIZE:]
                    
                    time.sleep(0.1)

# Starting the threads
# Thread for reading the controller, sending PWM values to the Arduino,
# reading PWM and battery values from the Arduino queueing the
# values to be uploaded to influxdb
Process(target=control, args=[measurement_queue], daemon=True).start()
# Uploading the values to influxdb
Process(target=influx_writer, args=[measurement_queue], daemon=True).start()

while True:
    time.sleep(1)