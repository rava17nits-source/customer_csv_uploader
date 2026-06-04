import json
import logging
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


HTTP_REQUESTS = Counter(
    "customer_import_http_requests_total",
    "Total HTTP requests handled by the customer import service.",
    ["method", "endpoint", "status"],
)
HTTP_LATENCY = Histogram(
    "customer_import_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "endpoint"],
)
IMPORT_ROWS = Counter(
    "customer_import_rows_total",
    "Customer import rows processed.",
    ["outcome"],
)
IMPORT_JOBS = Counter(
    "customer_import_jobs_total",
    "Customer import jobs completed.",
    ["status"],
)


class JSONLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": int(time.time()),
        }
        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True)


def configure_logging(app) -> None:
    log_dir = Path(app.config["LOG_DIR"])
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = JSONLogFormatter()
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_dir / "service.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    app.logger.handlers.clear()
    app.logger.addHandler(stream_handler)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False


def register_observability(app) -> None:
    @app.before_request
    def start_request_timer():
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        g.request_started_at = time.perf_counter()

    @app.after_request
    def record_request(response):
        endpoint = request.endpoint or "unknown"
        status = str(response.status_code)
        elapsed = time.perf_counter() - getattr(g, "request_started_at", time.perf_counter())
        HTTP_REQUESTS.labels(request.method, endpoint, status).inc()
        HTTP_LATENCY.labels(request.method, endpoint).observe(elapsed)
        response.headers["X-Request-ID"] = g.request_id
        app.logger.info(
            "request completed",
            extra={"request_id": g.request_id},
        )
        return response

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
