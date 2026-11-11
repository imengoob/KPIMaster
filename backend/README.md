# KPIMaster — Intelligent Support Agent for Ticket & Sprint Monitoring

Production-grade FastAPI backend with event-driven architecture, real-time WebSockets, and AI-ready analytics.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          API Layer (FastAPI)                         │
│  /projects  /sprints  /tickets  /blockers  /kpis  /ws  /metrics     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                        Service Layer                                 │
│  TicketMonitoring  BlockerDetection  KPI  Burndown  RepoAnalyzer     │
└──────────┬──────────────────────────────────────┬───────────────────┘
           │                                      │
┌──────────▼───────────┐             ┌────────────▼──────────────────┐
│   Repository Layer   │             │      Infrastructure Layer      │
│  BaseRepo + concrete │             │  EventBus  CircuitBreaker       │
│  async SQLAlchemy    │             │  Retry  WebSocketManager        │
└──────────┬───────────┘             └────────────┬──────────────────┘
           │                                      │
┌──────────▼───────────┐             ┌────────────▼──────────────────┐
│    PostgreSQL (async) │             │  Redis Pub/Sub  Celery Beat    │
│    Connection Pool    │             │  Background Workers            │
└──────────────────────┘             └───────────────────────────────┘
```

### Domain-Driven Structure

```
backend/
├── app/
│   ├── main.py                    # App factory, lifespan, middleware
│   ├── config.py                  # Pydantic Settings (env-driven)
│   ├── database.py                # Async SQLAlchemy engine + session
│   │
│   ├── domain/                    # Pure business logic — no I/O
│   │   ├── value_objects/
│   │   │   ├── ticket_status.py   # TicketStatus with transition guards
│   │   │   └── priority.py        # Priority, TicketType, SprintStatus enums
│   │   └── events/
│   │       ├── base.py            # Immutable BaseEvent (Pydantic)
│   │       ├── ticket_events.py   # TicketUpdated, TicketStalled, BlockerDetected
│   │       └── sprint_events.py   # SprintStarted, SprintCompleted, HealthDegraded
│   │
│   ├── models/                    # SQLAlchemy 2.0 ORM models
│   │   ├── project.py
│   │   ├── sprint.py
│   │   ├── developer.py
│   │   ├── ticket.py
│   │   ├── blocker.py
│   │   ├── repository_activity.py
│   │   ├── kpi_snapshot.py
│   │   └── burndown_entry.py
│   │
│   ├── schemas/                   # Pydantic v2 request/response schemas
│   │
│   ├── repositories/              # Data access — all SQL lives here
│   │   ├── base.py                # Generic async CRUD
│   │   ├── ticket_repository.py   # Stall detection queries, bulk updates
│   │   ├── sprint_repository.py   # Active sprint lookup
│   │   └── blocker_repository.py  # Open blockers, summary stats
│   │
│   ├── services/                  # Business logic orchestration
│   │   ├── ticket_monitoring_service.py   # Quality scoring (0-100)
│   │   ├── blocker_detection_service.py   # 3-level escalation state machine
│   │   ├── kpi_service.py                 # Cycle time, velocity, etc.
│   │   ├── burndown_service.py            # Daily burndown chart generation
│   │   ├── repository_analyzer_service.py # Git mismatch detection
│   │   └── notification_service.py        # Slack / Email / Log dispatcher
│   │
│   ├── infrastructure/
│   │   ├── event_bus/
│   │   │   ├── base.py                    # AbstractEventBus interface
│   │   │   ├── redis_event_bus.py         # Redis Pub/Sub (production)
│   │   │   └── in_memory_event_bus.py     # In-process (dev/test)
│   │   ├── workers/
│   │   │   ├── celery_app.py              # Celery app + beat schedule
│   │   │   └── tasks.py                   # All periodic task definitions
│   │   ├── circuit_breaker.py             # CLOSED/OPEN/HALF_OPEN state machine
│   │   ├── retry.py                       # Exponential backoff + jitter
│   │   └── websocket_manager.py           # WS connection pool with rooms
│   │
│   ├── api/
│   │   ├── dependencies.py                # FastAPI DI bindings
│   │   └── v1/
│   │       ├── router.py                  # Aggregates all sub-routers
│   │       ├── projects.py
│   │       ├── sprints.py
│   │       ├── tickets.py
│   │       ├── developers.py
│   │       ├── blockers.py
│   │       ├── kpis.py
│   │       ├── repository_activity.py
│   │       └── websockets.py              # WS endpoints
│   │
│   └── core/
│       ├── exceptions.py                  # Domain exception hierarchy
│       ├── logging_config.py              # structlog (JSON in prod)
│       └── metrics.py                     # Prometheus counters/histograms
│
├── alembic/                               # DB migrations
├── scripts/seed.py                        # Demo data (3 projects, ~80 tickets)
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Quick Start

### 1. Prerequisites

- Docker + Docker Compose, OR Python 3.12+ with PostgreSQL and Redis running locally

### 2. Environment setup

```bash
cd backend/
cp .env.example .env
# Edit .env if needed (default values work with docker-compose)
```

### 3. Docker (recommended)

```bash
docker-compose up -d postgres redis
docker-compose up -d api worker beat flower

# Run migrations
docker-compose exec api alembic upgrade head

# Seed demo data
docker-compose exec api python scripts/seed.py

# Validate migrated schema and seeded demo data
docker-compose exec api python scripts/validate_data_quality.py --profile demo
```

### 4. Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL and Redis (adjust URLs in .env)
alembic upgrade head
python scripts/seed.py
python scripts/validate_data_quality.py --profile demo

uvicorn app.main:app --reload --port 8000
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Create a user account |
| POST | `/api/v1/auth/login` | Obtain JWT bearer token |
| GET | `/api/v1/auth/me` | Get current authenticated user |
| GET | `/api/v1/projects` | List all projects |
| POST | `/api/v1/projects` | Create a project |
| GET | `/api/v1/projects/{id}/sprints/current` | Active sprint for a project |
| GET | `/api/v1/sprints/{id}/burndown` | Burndown chart data |
| GET | `/api/v1/tickets` | List tickets (filterable) |
| GET | `/api/v1/tickets/{id}/quality` | Quality score + recommendations |
| POST | `/api/v1/tickets/scan` | Trigger manual quality scan |
| GET | `/api/v1/blockers` | Open blockers |
| POST | `/api/v1/blockers/detect` | Trigger blocker detection sweep |
| POST | `/api/v1/blockers/{id}/resolve` | Resolve a blocker |
| GET | `/api/v1/kpis?project_id=1` | KPI dashboard |
| GET | `/api/v1/developers/{id}/progress/{sprint_id}` | Per-developer progress |
| GET | `/api/v1/developers/client-progress?project_id=1` | Client-facing delivery dashboard |
| GET | `/api/v1/repository-mismatches?project_id=1` | Git/ticket mismatches |
| GET | `/api/v1/trello/projects/{project_id}/comment-insights` | Comment analysis KPIs + ticket insights |
| GET | `/api/v1/trello/projects/{project_id}/tickets/{ticket_id}/comment-insights` | Single ticket discussion insight |
| WS | `/api/v1/ws/projects/{id}` | Real-time project feed |
| WS | `/api/v1/ws/global` | Global event stream |
| GET | `/health` | Health check (DB + Redis) |
| GET | `/metrics` | Prometheus metrics |

---

## Event-Driven System

Events published to Redis Pub/Sub:

| Event | Trigger |
|-------|---------|
| `ticket.updated` | Any ticket field change |
| `ticket.stalled` | No activity for 24h+ |
| `blocker.detected` | New blocker created by engine |
| `blocker.escalated` | Level promotion (Dev → Lead → Mgmt) |
| `repo.activity.updated` | Git scan detects mismatch |
| `sprint.started` | Sprint transitions to ACTIVE |
| `sprint.completed` | Sprint transitions to COMPLETED |
| `sprint.health_degraded` | Burndown deviates > 20% from ideal |

Handlers registered in `main.py` fan events out to:
1. WebSocket clients subscribed to the project
2. `NotificationService` (Slack/Email/Log)

---

## Background Workers (Celery Beat)

| Task | Schedule | Description |
|------|----------|-------------|
| `scan_tickets` | Every 5 min | Quality scan, update scores |
| `detect_blockers` | Every 10 min | 3-level escalation sweep |
| `compute_kpis` | Every 30 min | KPI snapshot for all active sprints |
| `refresh_burndown` | Every 1 hour | Upsert burndown entries |
| `scan_repository_activity` | Every 15 min | Git mismatch detection |
| `trello_comment_monitor` | Every 30 min | Comment analysis alerts + reminders |
| `generate_daily_report` | Daily @ 18:00 UTC | Full report + notifications |

---

## KPI Definitions

| KPI | Formula |
|-----|---------|
| **Cycle Time** | Avg hours from IN_PROGRESS → DONE |
| **Lead Time** | Avg hours from ticket creation → DONE |
| **Velocity** | Sum of story points for DONE tickets in sprint |
| **Completion Rate** | Completed points / Committed points |
| **Estimation Accuracy** | 1 − mean(|actual − estimated| / estimated) |
| **Throughput** | DONE tickets / elapsed sprint days |
| **Bug Rate** | Bug tickets / total tickets |

## Client-Facing Developer Progress

The backend now exposes a dedicated client-ready delivery snapshot at `/api/v1/developers/client-progress`.

It reuses the existing Trello-backed developer KPI service and returns:
- project-level delivery summary metrics
- on-track / at-risk / behind developer counts
- delivered vs total story points
- active blockers and average cycle time
- per-developer progress rows with activity freshness and a short delivery-risk note

---

## Scalability Notes

- **Stateless API**: All state in PostgreSQL + Redis. Safe to run N replicas behind a load balancer.
- **Idempotent workers**: All Celery tasks are safe to retry. Blockers use `(ticket_id, resolved=NULL)` uniqueness. Burndown uses upsert.
- **Connection pooling**: SQLAlchemy `QueuePool` with `pool_pre_ping` and configurable `pool_size`.
- **Circuit breaker**: Wraps outbound HTTP calls (Slack, GitHub API) with CLOSED/OPEN/HALF_OPEN state.
- **Retry with jitter**: `tenacity`-based decorator with exponential backoff + full jitter to avoid thundering herd.
- **Event bus abstraction**: Swap `InMemoryEventBus` ↔ `RedisEventBus` with zero service code changes.

---

## Observability

- **Structured logs**: `structlog` in JSON format (production) / colourised dev output
- **Prometheus metrics** at `/metrics`:
  - `sprintpulse_http_requests_total` — labelled by method/path/status
  - `sprintpulse_http_request_duration_seconds` — P50/P95/P99 latency
  - `sprintpulse_open_blockers_total` — by escalation level
  - `sprintpulse_events_published_total` — by event type
  - `sprintpulse_blocker_detections_total`
  - `sprintpulse_repo_mismatches_total`
  - `sprintpulse_kpi_computation_duration_seconds`
- **Health check** at `/health` — reports DB + Redis status for k8s readiness/liveness probes
- **Celery monitoring** via Flower at `http://localhost:5555`
