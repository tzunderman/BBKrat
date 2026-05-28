import sys
import time
import signal
from queue import Empty
from threading import Thread
from influxdb import InfluxDBClient

from controller import control, measurement_queue

def graceful_shutdown(signum, frame):
    print("Caught termination signal. Exiting.")
    sys.exit(0)

signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)

# ---------------- Grafana queue setup ----------------
client = InfluxDBClient(
    host='localhost',
    port=8086,
    database='BBKrat'
)


# ---------------- Thread setup ----------------
def influx_writer():
    batch: list[dict[str, str | int | dict[str, float]]] = []
    MAX_BATCH = 1000
    FLUSH_MIN = 200
    FLUSH_MAX_LATENCY = 1.0

    last_flush = time.monotonic()

    while True:
        try:
            # Wait for at least one point
            metric = measurement_queue.get(timeout=1)
            batch.append(metric)

            # Drain whatever is available right now (catch-up mechanism)
            while len(batch) < MAX_BATCH:
                try:
                    batch.append(measurement_queue.get_nowait())
                except Empty:
                    break

            now = time.monotonic()
            if len(batch) >= FLUSH_MIN or (now - last_flush) >= FLUSH_MAX_LATENCY:
                client.write_points(batch, time_precision="n")
                batch.clear()
                last_flush = now

        except Empty:
            # periodic flush even if low traffic
            if batch:
                client.write_points(batch, time_precision="n")
                batch.clear()
                last_flush = time.monotonic()

# Starting the threads
# Thread for reading the controller, sending PWM values to the Arduino,
# reading PWM and battery values from the Arduino queueing the
# values to be uploaded to influxdb
Thread(target=control, daemon=True).start()
# Uploading the values to influxdb
Thread(target=influx_writer, daemon=True).start()

while True:
    time.sleep(1)