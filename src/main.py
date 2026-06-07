import os
import sys
import time
import signal
import threading
import yaml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from prometheus_client import CollectorRegistry

from src.models import init_db
from src.ingest import scan_directory
from src.metrics import create_metrics, update_all_metrics
from src.server import start_server


class OtelFileHandler(FileSystemEventHandler):
    def __init__(self, db_path, config, processed_cache):
        self.db_path = db_path
        self.snapshot_count = config.get("snapshot_message_count", 20)
        self.threshold_pct = config.get("expansion_threshold_pct", 50.0)
        self.processed_cache = processed_cache

    def on_created(self, event):
        if event.src_path.endswith(".json"):
            from src.ingest import parse_otlp_file
            try:
                mtime = os.path.getmtime(event.src_path)
                cache_key = f"{event.src_path}:{mtime}"
                if cache_key in self.processed_cache:
                    return
                parse_otlp_file(event.src_path, self.db_path,
                                self.snapshot_count, self.threshold_pct)
                self.processed_cache.add(cache_key)
            except Exception as e:
                print(f"Error processing {event.src_path}: {e}", file=sys.stderr)


def load_config(config_path="config.yaml"):
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def main():
    config = load_config()
    db_path = config["sqlite_path"]
    otel_dir = config["otel_data_dir"]
    poll_interval = config.get("poll_interval_seconds", 5)
    metrics_port = config.get("metrics_port", 9090)
    snapshot_count = config.get("snapshot_message_count", 20)
    threshold_pct = config.get("expansion_threshold_pct", 50.0)

    init_db(db_path)

    registry = CollectorRegistry()
    metrics = create_metrics(registry)

    processed_cache = set()

    server = start_server(metrics_port, db_path, registry)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    event_handler = OtelFileHandler(db_path, config, processed_cache)
    observer = Observer()
    observer.schedule(event_handler, otel_dir, recursive=False)
    observer.start()

    def shutdown(signum, frame):
        observer.stop()
        observer.join()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"Watching {otel_dir} for OTLP files, metrics on :{metrics_port}")

    try:
        while True:
            try:
                scan_directory(otel_dir, db_path, processed_cache,
                               snapshot_count, threshold_pct)
                update_all_metrics(db_path, metrics)
            except Exception as e:
                print(f"Polling error: {e}", file=sys.stderr)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
