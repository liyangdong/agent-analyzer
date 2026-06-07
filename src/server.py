import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from prometheus_client import CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from src.metrics import create_metrics, update_all_metrics


class MetricsHandler(BaseHTTPRequestHandler):
    metrics: dict = {}
    registry: CollectorRegistry = None
    db_path: str = ""

    def do_GET(self):
        if self.path == "/metrics":
            update_all_metrics(self.db_path, self.metrics)
            data = generate_latest(self.registry)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/health":
            db_exists = os.path.exists(self.db_path)
            status = {"status": "ok" if db_exists else "degraded", "db_path": self.db_path}
            body = str(status).encode()
            self.send_response(200 if db_exists else 503)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_server(port: int, db_path: str, metrics: dict, registry: CollectorRegistry):
    handler = MetricsHandler
    handler.metrics = metrics
    handler.registry = registry
    handler.db_path = db_path
    server = HTTPServer(("0.0.0.0", port), handler)
    print(f"Metrics server listening on port {port}")
    return server
