"""
Prometheus-compatible metrics registry.

Metrics are exposed at GET /metrics (text format).
Import metric objects directly — they are singletons registered at import time.
"""
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client import multiprocess as _mp

from app.config import settings

# ---------------------------------------------------------------------------
# Registry — use the default global registry
# ---------------------------------------------------------------------------
REGISTRY = CollectorRegistry(auto_describe=False)

# ---------------------------------------------------------------------------
# HTTP metrics
# ---------------------------------------------------------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "sprintpulse_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "sprintpulse_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Business metrics
# ---------------------------------------------------------------------------
ACTIVE_SPRINTS_GAUGE = Gauge(
    "sprintpulse_active_sprints_total",
    "Number of currently active sprints",
    registry=REGISTRY,
)

OPEN_BLOCKERS_GAUGE = Gauge(
    "sprintpulse_open_blockers_total",
    "Number of unresolved blockers",
    ["escalation_level"],
    registry=REGISTRY,
)

TICKETS_SCANNED_TOTAL = Counter(
    "sprintpulse_tickets_scanned_total",
    "Tickets processed by the monitoring engine",
    registry=REGISTRY,
)

EVENTS_PUBLISHED_TOTAL = Counter(
    "sprintpulse_events_published_total",
    "Domain events published to the event bus",
    ["event_type"],
    registry=REGISTRY,
)

BLOCKER_DETECTIONS_TOTAL = Counter(
    "sprintpulse_blocker_detections_total",
    "Number of blockers detected by the engine",
    ["escalation_level"],
    registry=REGISTRY,
)

KPI_COMPUTATION_DURATION_SECONDS = Histogram(
    "sprintpulse_kpi_computation_duration_seconds",
    "Time taken to compute KPIs for a sprint",
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
    registry=REGISTRY,
)

NOTIFICATIONS_SENT_TOTAL = Counter(
    "sprintpulse_notifications_sent_total",
    "Notifications dispatched by channel",
    ["channel", "status"],
    registry=REGISTRY,
)

REPO_MISMATCHES_TOTAL = Counter(
    "sprintpulse_repo_mismatches_total",
    "Ticket-repository mismatches detected",
    ["mismatch_type"],
    registry=REGISTRY,
)

COMMENT_INSIGHTS_TOTAL = Counter(
    "sprintpulse_comment_insights_total",
    "Comment insight findings produced by the Trello comment analysis engine",
    ["kind"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Helper — render metrics for the /metrics endpoint
# ---------------------------------------------------------------------------
def get_metrics_response() -> tuple[bytes, str]:
    """Returns (body_bytes, content_type) for the /metrics route."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
