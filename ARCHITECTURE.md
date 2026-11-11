# KPIMaster — Technical Architecture Document

> **Version:** 1.0.0  
> **Date:** April 11, 2026  
> **Authors:** Norma Tunisie Engineering Team  
> **Classification:** Internal Technical Reference  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Context & Goals](#2-system-context--goals)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Technology Stack Decisions](#4-technology-stack-decisions)
5. [Frontend Architecture](#5-frontend-architecture)
6. [Backend Architecture](#6-backend-architecture)
7. [Database Design](#7-database-design)
8. [Trello Integration Architecture](#8-trello-integration-architecture)
9. [Real-Time Communication Layer](#9-real-time-communication-layer)
10. [Background Processing (Celery)](#10-background-processing-celery)
11. [AI Assistant & Vector Layer](#11-ai-assistant--vector-layer)
12. [Security Architecture](#12-security-architecture)
13. [Observability & Monitoring](#13-observability--monitoring)
14. [Deployment Architecture](#14-deployment-architecture)
15. [Data Flow Walkthroughs](#15-data-flow-walkthroughs)
16. [Testing Strategy](#16-testing-strategy)
17. [Architectural Decision Records (ADRs)](#17-architectural-decision-records-adrs)
18. [Known Limitations & Future Roadmap](#18-known-limitations--future-roadmap)

---

## 1. Executive Summary

**KPIMaster** is an enterprise-grade, AI-augmented sprint monitoring platform developed by **Norma Tunisie**. It bridges the gap between project management tooling (Trello) and actionable engineering intelligence by providing real-time KPI dashboards, automated blocker escalation, developer progress tracking, and repository mismatch detection.

### Key Capabilities

| Capability | Description |
|---|---|
| **Live Board Sync** | Bidirectional Trello integration via webhooks + polling fallback |
| **KPI Computation** | Cycle time, lead time, velocity, completion rate, estimation accuracy |
| **Blocker Escalation** | 3-tier automatic escalation (Developer → Team Lead → Management) |
| **Quality Scoring** | 5-gate ticket quality scoring (0–100) with actionable gates |
| **Developer Intelligence** | Per-member progress, workload, and performance metrics |
| **Client Delivery View** | Client-ready developer progress dashboard with delivery status, freshness, and risk notes |
| **AI Chat Assistant** | RAG-based in-browser assistant with TF-IDF vector search + voice input |
| **Real-Time Push** | WebSocket-based event push for all mutations |
| **Repository Analysis** | Detects stalled branches and PR/status mismatches |

### Architecture Style

KPIMaster follows a **layered, event-driven monolith** pattern — a deliberate choice over microservices to optimise for development velocity and operational simplicity at the current scale, while preserving clean service boundaries that allow future decomposition.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     KPIMaster — System Layers                     │
├───────────────────┬─────────────────────────────────────────────────┤
│  Presentation     │  React 18 SPA (TypeScript + Tailwind CSS)       │
├───────────────────┼─────────────────────────────────────────────────┤
│  API Gateway      │  FastAPI (async, OpenAPI 3.1)                   │
├───────────────────┼─────────────────────────────────────────────────┤
│  Domain Services  │  Blocker · KPI · Ticket · Burndown · Trello     │
├───────────────────┼─────────────────────────────────────────────────┤
│  Domain Events    │  Redis Event Bus (pub/sub)                      │
├───────────────────┼─────────────────────────────────────────────────┤
│  Data Access      │  SQLAlchemy 2.0 (async) + Repository Pattern    │
├───────────────────┼─────────────────────────────────────────────────┤
│  Persistence      │  PostgreSQL 16  ·  Redis 7                      │
├───────────────────┼─────────────────────────────────────────────────┤
│  Background Jobs  │  Celery 5.4 + Beat Scheduler                    │
└───────────────────┴─────────────────────────────────────────────────┘
```

---

## 2. System Context & Goals

### 2.1 Context Diagram (C4 Level 1)

```
                         ┌──────────────────────────┐
                         │         Trello           │
                         │   (External PMS API)     │
                         └────────────┬─────────────┘
                                      │ REST API / Webhooks
                         ┌────────────▼─────────────┐
      ┌──────────┐        │                          │        ┌────────────┐
      │  Scrum   │ HTTPS  │      KPIMaster         │  WS    │  Browser   │
      │  Master  │◄──────►│   (Norma Tunisie)        │◄──────►│  (React)   │
      └──────────┘        │                          │        └────────────┘
      ┌──────────┐        │  FastAPI + PostgreSQL     │
      │Developer │◄──────►│  + Redis + Celery        │
      └──────────┘        │                          │
      ┌──────────┐        └──────────────────────────┘
      │  Manager │◄──────►            │
      └──────────┘                    │ SMTP / Slack
                         ┌────────────▼─────────────┐
                         │  Notification Channels    │
                         │  (Slack webhook, Email)   │
                         └──────────────────────────┘
```

### 2.2 Non-Functional Requirements

| NFR | Target | Implementation |
|---|---|---|
| **Latency** | P95 API response < 200 ms | Async I/O, indexed queries, Redis cache |
| **Throughput** | 500 concurrent users | 4 Uvicorn workers, async DB pool |
| **Consistency** | Eventual (sync lag ≤ 5 min) | Celery polling + webhook push |
| **Availability** | 99.5% uptime target | Health checks, Docker restart policy |
| **Scalability** | Horizontal Celery workers | Task routing, queue partitioning |
| **Observability** | Metrics, logs, traces | Prometheus, structlog |

---

## 3. High-Level Architecture

### 3.1 Component Interaction Map

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            BROWSER CLIENT                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │React Router │  │React Query   │  │Framer Motion │  │SprintAssistant   │  │
│  │(6 routes)   │  │(server state)│  │(animations)  │  │(TF-IDF RAG chat) │  │
│  └──────┬──────┘  └──────┬───────┘  └──────────────┘  └──────────────────┘  │
│         │                │  HTTP/WS                                           │
└─────────┼────────────────┼──────────────────────────────────────────────────┘
          │                │
┌─────────▼────────────────▼──────────────────────────────────────────────────┐
│                          FASTAPI APPLICATION                                 │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                     Middleware Stack                                  │   │
│  │   CORS  ──►  Prometheus Instrumentation  ──►  Exception Handler       │   │
│  └──────────────────────────┬────────────────────────────────────────────┘   │
│                             │                                                │
│  ┌──────────┐  ┌──────────┐ │ ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │/projects │  │/sprints  │ │ │/tickets  │  │/blockers │  │/trello      │  │
│  │/kpis     │  │/burndown │ │ │/developers│  │/repo     │  │/websockets  │  │
│  └─────┬────┘  └────┬─────┘ │ └────┬─────┘  └────┬─────┘  └──────┬──────┘  │
│        │            │       │      │              │               │          │
│  ┌─────▼────────────▼───────▼──────▼──────────────▼───────────────▼──────┐   │
│  │                       Service Layer                                    │   │
│  │  BlockerDetection · KPIService · TicketMonitoring · BurndownService    │   │
│  │  RepositoryAnalyzer · NotificationService                              │   │
│  │  TrelloSyncService · TrelloAnalyticsService · TrelloLiveProjectService │   │
│  │  DeveloperKPIService → internal KPI + client delivery reporting        │   │
│  └───────────────────────────────┬────────────────────────────────────────┘   │
│                                  │ Domain Events                              │
│  ┌───────────────────────────────▼────────────────────────────────────────┐   │
│  │                    Event Bus (Redis / In-Memory)                        │   │
│  │   ticket.* ─────────────────────────────────────────────────────────►  │   │
│  │   blocker.* ─────────────────────── WebSocket Manager ─────────────►  │   │
│  │   sprint.* ──────────────────────────────────────────────────────────►  │   │
│  └───────────────────────────────┬────────────────────────────────────────┘   │
│                                  │                                            │
│  ┌───────────────────────────────▼────────────────────────────────────────┐   │
│  │              Repository Layer (SQLAlchemy 2.0 Async)                   │   │
│  │      ProjectRepo · SprintRepo · TicketRepo · BlockerRepo               │   │
│  └───────────────────────────────┬────────────────────────────────────────┘   │
└──────────────────────────────────┼─────────────────────────────────────────────┘
                                   │
              ┌────────────────────┼─────────────────────┐
              │                    │                      │
   ┌──────────▼──────┐  ┌──────────▼──────┐  ┌──────────▼──────┐
   │  PostgreSQL 16   │  │    Redis 7       │  │  Trello API      │
   │  (Primary store) │  │  (Cache+Broker)  │  │  (External)      │
   └──────────────────┘  └──────────────────┘  └──────────────────┘
              ▲
   ┌──────────┴──────────────────────────────────────────────────┐
   │                  Celery Workers + Beat                       │
   │  scan_tickets · detect_blockers · compute_kpis              │
   │  trello_sync · trello_analytics · daily_report              │
   └──────────────────────────────────────────────────────────────┘
```

---

## 4. Technology Stack Decisions

### 4.1 Backend Stack

#### FastAPI (Python 3.12+)

**Decision:** Use FastAPI over Django REST Framework or Flask.

**Reasoning:**
- Native `async`/`await` support — critical for non-blocking Trello API calls, DB I/O, and WebSocket handling
- Automatic OpenAPI 3.1 schema generation from Pydantic models — zero-maintenance API contracts
- Dependency Injection system is first-class — clean testability with mock injection
- Pydantic v2 (Rust core) serialisation is 5–10× faster than v1 or Django serialisers
- Native WebSocket support without additional libraries

**Trade-offs accepted:**
- Less "batteries included" than Django (no admin panel, ORM, auth)
- Team must manage database migrations (Alembic) explicitly

#### SQLAlchemy 2.0 (Async)

**Decision:** SQLAlchemy 2.0 with `asyncpg` driver over Tortoise ORM or raw `asyncpg`.

**Reasoning:**
- Mature ecosystem, battle-tested at scale
- `AsyncSession` with `select()` syntax provides full async support without sacrificing the power of the ORM
- Alembic integration for migrations is industry standard
- `ON CONFLICT DO UPDATE` (upsert) support critical for Trello sync idempotency

**Connection Pool Configuration:**
```
QueuePool:  pool_size=5, max_overflow=10, pool_timeout=30s
NullPool:   used in test suite to prevent connection leaks
```

#### PostgreSQL 16

**Decision:** PostgreSQL over MySQL, SQLite, or CockroachDB.

**Reasoning:**
- `JSONB` columns for storing Trello labels, member lists, and action data without schema migrations
- `ON CONFLICT` (upsert) for idempotent Trello sync operations
- Strong `asyncpg` driver with native binary protocol
- Full-text search capabilities (future use)
- Logical replication support for future read replicas

#### Redis 7

**Decision:** Redis as both Celery broker and application cache.

**Reasoning:**
- Celery requires a message broker; Redis avoids running a separate RabbitMQ service
- Sub-millisecond pub/sub for the domain event bus
- AOF persistence ensures task durability across restarts
- Atomic operations for distributed locks (future use)

### 4.2 Frontend Stack

#### React 18 + TypeScript

**Decision:** React 18 SPA with strict TypeScript.

**Reasoning:**
- Concurrent features (`useTransition`, `Suspense`) improve perceived performance for slow data loads
- TypeScript strict mode eliminates an entire class of runtime errors; adapter types enforce backend/frontend contract
- Largest ecosystem for UI component libraries (Radix UI, shadcn/ui)

#### TanStack Query v5 (React Query)

**Decision:** React Query over Redux, Zustand, or SWR.

**Reasoning:**
- Purpose-built for server state — cache invalidation, background refetch, stale-while-revalidate
- `queryClient.invalidateQueries()` lets the Refresh button force-expire the entire cache with one call
- Built-in deduplication prevents duplicate inflight requests when multiple components need the same data
- Devtools make cache debugging trivial

**Stale Time Strategy:**

| Data Type | Stale Time | Rationale |
|---|---|---|
| KPIs / Sprint | 5 min | Computed data — expensive to recompute |
| Tickets / Blockers | 1 min | Action-sensitive — users expect near-realtime |
| Board Summary | 1 min | Changes on sync |
| Developers | 5 min | Rarely changes mid-sprint |

#### Vite + SWC

**Decision:** Vite with `@vitejs/plugin-react-swc` over Create React App or Next.js.

**Reasoning:**
- SWC compiler (Rust) provides ~20× faster TypeScript transpilation vs Babel
- HMR (Hot Module Replacement) is near-instant even for large component trees
- No SSR requirements — pure SPA serving is simpler and cheaper to deploy
- Native ESM dev server eliminates bundling overhead in development

---

## 5. Frontend Architecture

### 5.1 Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                       Pages Layer                            │
│  Dashboard · SprintMonitor · TicketAnalysis                  │
│  BlockerDetection · DeveloperProgress · RepositoryIntegration│
│  Settings                                                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ consumes
┌──────────────────────────▼──────────────────────────────────┐
│                     Hooks Layer                              │
│  useCurrentSprint · useSprintKpis · useBurndown             │
│  useBlockers · useTickets · useDevelopers · useRepo         │
│  (all backed by React Query)                                 │
└──────────────────────────┬──────────────────────────────────┘
                           │ calls
┌──────────────────────────▼──────────────────────────────────┐
│                  Service / Adapter Layer                     │
│  sprintApi · ticketApi · developerApi · trelloApi           │
│  adaptSprint() · adaptKpis() · adaptTicket() · ...          │
│  (Backend snake_case → UI camelCase transformation)          │
└──────────────────────────┬──────────────────────────────────┘
                           │ uses
┌──────────────────────────▼──────────────────────────────────┐
│                   Transport Layer                            │
│  apiFetch() — wraps native fetch with:                      │
│  • API_BASE_URL prefix                                       │
│  • Content-Type: application/json header                     │
│  • Throws typed ApiError on non-2xx responses               │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Data Flow: Dashboard Load

```
Browser                 React Query              FastAPI               PostgreSQL
   │                        │                      │                      │
   │  render Dashboard       │                      │                      │
   │──────────────────────►  │                      │                      │
   │                        │  queryKey: ["sprint"] │                      │
   │                        │─────────────────────►│                      │
   │                        │                      │  SELECT * FROM sprints│
   │                        │                      │─────────────────────►│
   │                        │                      │◄─────────────────────│
   │                        │  BackendSprint JSON  │                      │
   │                        │◄─────────────────────│                      │
   │  adaptSprint()         │                      │                      │
   │◄───────────────────────│                      │                      │
   │  render KPI tiles      │                      │                      │
   │                        │  queryKey: ["kpis"]  │                      │
   │                        │─────────────────────►│                      │
   │                        │                      │  SELECT + aggregate  │
   │                        │◄─────────────────────│                      │
   │  adaptKpis()           │                      │                      │
   │◄───────────────────────│                      │                      │
   │  render charts         │                      │                      │
```

### 5.3 Type Safety Architecture

The adapter pattern enforces a strict contract between the wire format and the UI model:

```typescript
// Wire format (snake_case — matches Pydantic schema exactly)
interface BackendKPIDashboard {
  project_id: number;
  current_kpis: BackendKPISnapshot | null;
  velocity_trend: number[];
  open_blockers: number;
}

// UI model (camelCase — consumed by components)
interface UIKpi {
  velocity: MetricValue;      // { value, change, type }
  cycleTime: MetricValue;
  completionRate: MetricValue;
}

// Adapter (one-way transformation, pure function, fully typed)
function adaptKpis(dash: BackendKPIDashboard): UIKpi { ... }
```

This separation means:
- Backend schema changes only affect the adapter — components are insulated
- Adapters are unit-tested independently from API calls
- TypeScript enforces exhaustive handling of all backend fields

### 5.4 State Management Strategy

```
┌─────────────────────────────────────────────────────────┐
│                    Application State                     │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │        React Query Cache (Server State)          │   │
│  │  sprint · kpis · tickets · blockers · board     │   │
│  │  developers · velocity · burndown · mismatches  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │       ProjectContext (Global Client State)       │   │
│  │  currentProject · allProjects · setProject()    │   │
│  │  Persisted to: localStorage + URL (?project=KEY)│   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │        Component-Local State (useState)          │   │
│  │  filter tabs · sort order · modal open state    │   │
│  │  refresh state (idle/syncing/done/error)         │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Intentional decision:** No global client-side state manager (no Redux, no Zustand). Server state lives in React Query; the only "global" client state is the selected project. Using a heavy state manager for this would be over-engineering.

---

## 6. Backend Architecture

### 6.1 Domain Layer Design

The domain layer contains the business logic free of infrastructure concerns:

```
backend/app/domain/
├── value_objects/
│   ├── ticket_status.py     — TicketStatus StrEnum + transition guards
│   └── priority.py          — EscalationLevel enum (L1/L2/L3)
└── events/
    ├── base.py              — BaseEvent(event_type, timestamp, id: UUID)
    ├── ticket_events.py     — TicketUpdated, TicketStalled, BlockerDetected, BlockerEscalated
    ├── sprint_events.py     — SprintStarted, SprintCompleted
    └── trello_events.py     — BoardSynced, CardMoved
```

#### TicketStatus Transition Machine

```
              ┌──────────┐
         ┌───►│ BACKLOG  │◄────────────────────┐
         │    └────┬─────┘                     │
         │         │ start_work()              │ reopen()
         │    ┌────▼─────┐                     │
         │    │  IN_PROG  │──────────────────►BLOCKED
         │    └────┬─────┘    block()          │
         │         │                     unblock()
         │    ┌────▼─────┐                     │
         │    │ IN_REVIEW │◄────────────────────┘
         │    └────┬─────┘
         │         │ approve()
         │    ┌────▼─────┐
         └────│   DONE   │ (terminal)
              └──────────┘
```

`TicketStatus.can_transition_to(target)` enforces these transitions at the domain level — the API layer calls this before persisting status changes.

### 6.2 Service Layer Responsibilities

Each service is stateless, receives an `AsyncSession` via constructor injection, and publishes domain events:

```
┌──────────────────────────────────────────────────────────────────┐
│                    Service Responsibilities                       │
│                                                                  │
│  BlockerDetectionService                                         │
│    run_detection_sweep(project_id)                               │
│    ├── load stalled tickets (idle > L1_THRESHOLD = 24h)          │
│    ├── compute escalation level (24h → L1, 48h → L2, 72h → L3)  │
│    ├── create/update Blocker records                             │
│    ├── publish BlockerDetectedEvent / BlockerEscalatedEvent      │
│    └── increment Prometheus OPEN_BLOCKERS_GAUGE                  │
│                                                                  │
│  TicketMonitoringService                                         │
│    scan_all_active_tickets(project_id)                           │
│    ├── load active tickets                                       │
│    ├── compute quality_score per ticket (5 gates × 20pts each)  │
│    │    gate_description (+20): len(description) >= 20          │
│    │    gate_assignee    (+20): assignee_id is not None         │
│    │    gate_priority    (+20): priority != "medium"            │
│    │    gate_estimation  (+20): estimated_hours is not None     │
│    │    gate_title       (+20): len(title.strip()) >= 10        │
│    ├── persist updated quality_score                             │
│    └── publish TicketUpdatedEvent                                │
│                                                                  │
│  KPIService                                                      │
│    compute_and_persist(project_id, sprint_id)                    │
│    ├── cycle_time_hours = avg(done_at - in_progress_at)          │
│    ├── lead_time_hours  = avg(done_at - created_at)              │
│    ├── velocity         = sum(story_points WHERE status=done)    │
│    ├── completion_rate  = completed_points / committed_points    │
│    ├── throughput       = count(done) in last 7 days             │
│    ├── estimation_acc   = 1 - abs(actual - estimated) / estimated│
│    └── persist KPISnapshot, publish KPIComputedEvent             │
└──────────────────────────────────────────────────────────────────┘
```

### 6.3 Repository Pattern

```python
# Generic base — provides type-safe CRUD for any model
class BaseRepository[ModelT: Base]:
    async def get_by_id(self, id: int) -> ModelT | None
    async def get_all(self, **filters) -> list[ModelT]
    async def count(self, **filters) -> int
    async def create(self, **attrs) -> ModelT
    async def update(self, instance, **attrs) -> ModelT
    async def delete(self, instance) -> None
    async def bulk_create(self, items: list[dict]) -> list[ModelT]

# Concrete example
class TicketRepository(BaseRepository[Ticket]):
    async def get_stalled_tickets(self, project_id, idle_hours) -> list[Ticket]
    async def get_by_sprint(self, sprint_id, status_filter) -> list[Ticket]
    async def touch_activity(self, ticket_id) -> None   # updates last_activity_at
    async def get_with_relations(self, ticket_id) -> Ticket  # joins developer, sprint
```

**Rationale for Repository pattern:**
- Services are decoupled from ORM specifics — they work against interfaces, not SQLAlchemy directly
- Query logic is co-located with the model it operates on
- Enables clean mock injection in tests without patching SQLAlchemy internals

### 6.4 Exception Hierarchy

```
KPIMasterError (base)
├── NotFoundError        → HTTP 404
├── ConflictError        → HTTP 409 (duplicate key, invalid transition)
├── DomainValidationError→ HTTP 422 (business rule violation)
└── InfrastructureError  → HTTP 502 (Trello API failure, DB timeout)
```

The global exception handler in `main.py` maps these to structured JSON error responses:

```json
{
  "error": "NotFoundError",
  "message": "Sprint with id=42 not found",
  "detail": null,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## 7. Database Design

### 7.1 Entity Relationship Diagram

```
┌─────────────┐      ┌────────────────┐      ┌─────────────────┐
│   projects  │1───N │    sprints     │1───N │  burndown_entries│
│─────────────│      │────────────────│      │─────────────────│
│ id (PK)     │      │ id (PK)        │      │ id (PK)         │
│ name        │      │ project_id (FK)│      │ sprint_id (FK)  │
│ key (UNIQ)  │      │ name           │      │ date            │
│ description │      │ goal           │      │ remaining_points│
│ repo_url    │      │ start_date     │      │ completed_points│
│ is_active   │      │ end_date       │      │ ideal_remaining │
└──────┬──────┘      │ status         │      └─────────────────┘
       │             │ committed_pts  │
       │             │ completed_pts  │      ┌─────────────────┐
       │             │ velocity       │      │  kpi_snapshots  │
       │             └───────┬────────┘      │─────────────────│
       │                     │               │ id (PK)         │
       │  ┌──────────────────┘               │ project_id (FK) │
       │  │                                  │ sprint_id (FK)  │
       │  │  ┌──────────────────────┐        │ cycle_time_h    │
       │  └─►│      tickets         │        │ lead_time_h     │
       │     │──────────────────────│        │ velocity        │
       │     │ id (PK)              │        │ completion_rate │
       │     │ project_id (FK)      │        │ throughput      │
       │     │ sprint_id (FK, NULL) │        │ computed_at     │
       │     │ assignee_id (FK)     │        └─────────────────┘
       │     │ reporter_id (FK)     │
       │     │ title                │      ┌────────────────────┐
       │     │ status               │1───N │      blockers       │
       │     │ priority             │      │────────────────────│
       │     │ story_points         │      │ id (PK)            │
       │     │ quality_score        │      │ ticket_id (FK)     │
       │     │ estimated_hours      │      │ description        │
       │     │ actual_hours         │      │ stall_hours        │
       │     │ last_activity_at     │      │ escalation_level   │
       │     └─────────┬────────────┘      │ detected_at        │
       │               │                   │ resolved_at        │
       │               │1───1              └────────────────────┘
       │     ┌─────────▼────────────┐
       │     │  repository_activity │
       │     │──────────────────────│
       │     │ branch_name          │
       │     │ commit_count         │
       │     │ pr_count             │
       │     │ pr_merged            │
       │     │ mismatch_type        │
       │     │ mismatch_reason      │
       │     └──────────────────────┘
       │
       │     ┌──────────────────────┐1───N ┌──────────────────────┐
       └────►│  trello_credentials  │      │    trello_boards     │
             │──────────────────────│      │──────────────────────│
             │ api_key (encrypted)  │      │ credential_id (FK)   │
             │ api_token            │      │ trello_id (UNIQ)     │
             │ is_active            │      │ name                 │
             └──────────────────────┘      │ short_url            │
                                           │ last_synced_at       │
                                           │ last_action_id       │
                                           └──────────┬───────────┘
                                                      │1───N
                              ┌───────────────────────┼──────────────────────┐
                              │                       │                      │
                    ┌─────────▼───────┐    ┌──────────▼──────┐   ┌──────────▼──────┐
                    │  trello_lists   │    │  trello_cards   │   │ trello_actions  │
                    │─────────────────│    │─────────────────│   │─────────────────│
                    │ trello_id (UNIQ)│    │ trello_id (UNIQ)│   │ trello_action_id│
                    │ name            │    │ name            │   │ card_id (FK)    │
                    │ list_type ENUM  │    │ list_id (FK)    │   │ action_type     │
                    │ pos             │    │ member_ids JSONB│   │ data JSONB      │
                    │ is_closed       │    │ labels JSONB    │   │ trello_member_id│
                    └─────────────────┘    │ due_date        │   └─────────────────┘
                                           │ is_stalled      │
                                           │ stalled_since   │
                                           │ entered_done_at │
                                           │ cycle_time_hours│
                                           └─────────────────┘
```

### 7.2 Critical Indexes

```sql
-- Ticket lookup by project + status (most frequent query pattern)
CREATE INDEX idx_tickets_project_status ON tickets(project_id, status);

-- Stall detection (daily Celery sweep)
CREATE INDEX idx_tickets_last_activity ON tickets(last_activity_at)
  WHERE status IN ('in_progress', 'in_review');

-- KPI computation
CREATE INDEX idx_tickets_sprint_status ON tickets(sprint_id, status);

-- Trello sync idempotency (upsert target)
CREATE UNIQUE INDEX idx_trello_cards_trello_id ON trello_cards(trello_id);
CREATE UNIQUE INDEX idx_trello_lists_trello_id ON trello_lists(trello_id);

-- Board list browsing (ordered by position)
CREATE INDEX idx_trello_lists_board_pos ON trello_lists(board_id, pos);
```

### 7.3 JSONB Usage

Two columns use PostgreSQL JSONB to avoid schema migrations for Trello's variable-shape data:

| Column | Model | Content | Queried? |
|---|---|---|---|
| `member_ids` | TrelloCard | `["trello_member_id_1", ...]` | No (app-side) |
| `labels` | TrelloCard | `[{"id": "...", "name": "...", "color": "..."}]` | No (app-side) |
| `data` | TrelloAction | Full action payload | No (app-side) |

Keeping these as JSONB rather than normalised tables avoids 3 join tables and schema migrations every time Trello adds a new label field.

### 7.4 Migration Strategy

Alembic migrations are numbered sequentially and explicitly named:

```
alembic/versions/
├── 0000_initial_schema.py        — All core domain tables
├── 0001_add_trello_integration.py — Trello models
└── 0002_add_trello_app_settings.py— Singleton settings row
```

**Upsert Pattern for Trello Sync:**

```python
stmt = (
    pg_insert(TrelloCard)
    .values(values)
    .on_conflict_do_update(
        index_elements=["trello_id"],   # unique constraint
        set_={
            "list_id":      stmt.excluded.list_id,
            "member_ids":   stmt.excluded.member_ids,
            "labels":       stmt.excluded.labels,
            # NB: list_type also updated — newly classified lists get
            # their type updated on every full sync
        },
    )
)
```

This pattern makes sync operations **idempotent** — replaying the same Trello payload is safe.

---

## 8. Trello Integration Architecture

### 8.1 Sync Strategy Overview

KPIMaster uses a **dual-mode sync** strategy to balance data freshness against Trello API rate limits:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Sync Strategy Decision Tree                   │
│                                                                 │
│  First connect?  ─── YES ──► Full Sync                         │
│       │                       - Fetch all lists                │
│       │                       - Fetch all open cards           │
│       │                       - Fetch last 1000 actions        │
│       │                       - Classify all lists             │
│       NO                                                        │
│       │                                                         │
│  User clicks Refresh? ─── YES ──► Incremental Sync             │
│       │                            - Fetch actions since       │
│       │                              last_action_id            │
│       │                            - Re-fetch affected cards   │
│       NO                            only                       │
│       │                                                         │
│  Celery beat tick (5 min) ────────► Incremental Sync           │
│                                      (same as above)           │
│                                                                 │
│  Trello Webhook fired ────────────► Real-time handler          │
│                                      - Handles card moves,     │
│                                        member changes          │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 List Classification Engine

The list classifier is the core of KPI accuracy. It uses ordered regex pattern matching:

```python
# Priority order matters: DONE checked first to avoid
# "archived" (done) being matched by "wip" pattern

_DONE_PAT    ─── done | completed | shipped | deployed | released | closed | archived | ...
_WIP_PAT     ─── in progress | doing | wip | dev | sprint | to test | verify | staging | ...
_BACKLOG_PAT ─── backlog | todo | to do | icebox | user stories | requirements | queue | ...
```

**Classification cascade for your board:**

```
User Stories  ──► matches _BACKLOG_PAT ("user stories") ──► ListType.BACKLOG
To Do         ──► matches _BACKLOG_PAT ("to do")        ──► ListType.BACKLOG
Sprint        ──► matches _WIP_PAT ("sprint")           ──► ListType.WIP
Doing         ──► matches _WIP_PAT ("doing")            ──► ListType.WIP
To Test       ──► matches _WIP_PAT ("to test")          ──► ListType.WIP
Done          ──► matches _DONE_PAT ("done")            ──► ListType.DONE
```

**KPI Impact of Classification:**

| ListType | KPI contribution |
|---|---|
| BACKLOG | Adds to `committed_points` (backlog depth) |
| WIP | Counted in `wip_count`, drives cycle time tracking |
| DONE | Drives `completed_points`, `velocity`, `completion_rate`, burndown |
| UNKNOWN | Ignored in all KPI calculations |

### 8.3 Webhook Processing Pipeline

```
Trello sends POST /api/v1/trello/webhooks/{id}/receive
          │
          ▼
┌─────────────────────────────────┐
│  1. Verify HMAC-SHA1 signature  │  ← api_token used as secret
│     (x-trello-webhook header)   │
└───────────────┬─────────────────┘
                │ signature valid?
                │ NO ──► HTTP 403
                │ YES
                ▼
┌─────────────────────────────────┐
│  2. Parse TrelloAPIWebhookPayload│
│     (Pydantic validation)        │
└───────────────┬─────────────────┘
                ▼
┌─────────────────────────────────┐
│  3. Dispatch to WebhookService   │
│     handle_payload()             │
│     - createCard   → upsert card │
│     - updateCard   → patch fields│
│     - moveCard     → update list │
│     - addMember    → patch ids   │
│     - removeMember → patch ids   │
└───────────────┬─────────────────┘
                ▼
┌─────────────────────────────────┐
│  4. Publish TrelloCardMovedEvent │
│     → WebSocket broadcast        │
│     → Frontend cache invalidated │
└─────────────────────────────────┘
```

### 8.4 Member ID Resolution

Trello member IDs are alphanumeric strings (e.g., `5f3b2c4d1a2b3c4d5e6f7g8h`). KPIMaster needs integer developer IDs for its relational schema. The resolution uses a deterministic SHA-1 hash:

```python
def _member_numeric_id(self, member_id: str | None) -> int | None:
    if not member_id:
        return None
    h = hashlib.sha1(member_id.encode()).digest()
    # Take first 6 bytes as a positive integer (max ~281 trillion)
    return int.from_bytes(h[:6], "big") & 0x7FFFFFFF
```

This produces a **stable, collision-resistant** integer from any Trello member ID string. The same function is called in both `list_developers()` and `_to_ticket_response()`, ensuring the developer IDs match between the developer list and ticket assignees — without requiring a join table.

---

## 9. Real-Time Communication Layer

### 9.1 WebSocket Architecture

```
Browser                FastAPI                  Event Bus
   │                      │                        │
   │  WS /api/v1/ws       │                        │
   │  ?project_id=42      │                        │
   │─────────────────────►│                        │
   │                      │ ws_manager.connect()   │
   │                      │ room: project_42        │
   │                      │─────────────────────►  │
   │                      │                        │
   │   ...later...        │                        │
   │                      │ ◄── ticket.updated ────│
   │                      │    {project_id: 42}     │
   │                      │                        │
   │                      │ broadcast_to_project(42)│
   │ ◄─────────────────── │                        │
   │  {"event":"ticket.   │                        │
   │   updated", ...}     │                        │
   │                      │                        │
   │  queryClient.        │                        │
   │  invalidateQueries() │                        │
```

### 9.2 WebSocket Manager Design

```python
class WebSocketManager:
    # Per-project rooms
    _rooms: dict[int, set[WebSocket]] = defaultdict(set)
    # Global listeners (admin dashboard)
    _global: set[WebSocket] = set()

    async def connect(ws: WebSocket, project_id: int | None)
    async def disconnect(ws: WebSocket, project_id: int | None)
    async def broadcast_to_project(project_id: int, payload: dict)
    async def broadcast_global(payload: dict)
```

**Rationale for room-based isolation:** Broadcasting all events to all connections would leak cross-project data and create noise. Each connection registers for exactly one project room.

### 9.3 Event Bus

```
┌────────────────────────────────────────────────────────────┐
│                   Event Bus Implementations                  │
│                                                             │
│  Development:  InMemoryEventBus                             │
│    - asyncio.Queue per channel                             │
│    - Wildcard subscription: "ticket.*" matches all ticket  │
│      events                                                 │
│    - No persistence (events lost on restart)               │
│                                                             │
│  Production:   RedisEventBus                                │
│    - Redis PubSub channels                                  │
│    - Pattern subscriptions: PSUBSCRIBE ticket.*            │
│    - Events survive application restarts                    │
│    - Supports multiple application replicas                 │
│                                                             │
│  Both implement:  EventBus (abstract base)                  │
│    publish(event: BaseEvent) → None                        │
│    subscribe(pattern: str, handler: Callable) → None       │
└────────────────────────────────────────────────────────────┘
```

---

## 10. Background Processing (Celery)

### 10.1 Task Schedule

```
Celery Beat Schedule
│
├── Every 5 min  ─── scan_tickets
│                     └── TicketMonitoringService.scan_all_active_tickets()
│                         Updates quality_score for all active tickets
│
├── Every 5 min  ─── trello_incremental_sync_all
│                     └── For each active board: incremental_sync()
│                         Pulls new actions since last_action_id
│
├── Every 10 min ─── detect_blockers
│                     └── BlockerDetectionService.run_detection_sweep()
│                         Creates/escalates blockers, fires notifications
│
├── Every 15 min ─── scan_repository_activity
│                     └── RepositoryAnalyzerService.scan_project()
│                         Detects branch staleness and PR mismatches
│
├── Every 15 min ─── trello_compute_analytics_all
│                     └── TrelloAnalyticsService.compute_board_analytics()
│                         Updates stall detection, cycle times on cards
│
├── Every 30 min ─── compute_kpis
│                     └── KPIService.compute_and_persist()
│                         Snapshots velocity, cycle time, completion rate
│
├── Every 1 hour ─── refresh_burndown
│                     └── BurndownService.refresh_burndown()
│                         Recomputes chart entries from current state
│
└── Daily 18:00  ─── generate_daily_report  [high_priority queue]
                      └── Aggregates day's metrics, sends email/Slack digest
```

### 10.2 Queue Routing

```
┌────────────────────────────────────────────────────────────┐
│                     Queue Architecture                       │
│                                                             │
│  "high_priority" queue                                      │
│    └── Daily report generation                             │
│        (time-sensitive, single worker max)                  │
│                                                             │
│  "default" queue                                            │
│    └── All periodic monitoring tasks                        │
│        (4 workers, shared pool)                             │
│                                                             │
│  Worker concurrency: 4 (prefork)                           │
│  Task acks: late (task not acked until completion)          │
│  Max retries: 3, backoff: exponential                       │
└────────────────────────────────────────────────────────────┘
```

### 10.3 Resilience Patterns

#### Circuit Breaker (Trello API)

```python
class CircuitBreaker:
    states: CLOSED → OPEN → HALF_OPEN → CLOSED

    CLOSED:     Normal operation. Failures increment counter.
    OPEN:       After threshold failures, all calls fail immediately.
                Opens for `timeout` seconds (default: 60s)
    HALF_OPEN:  One probe call allowed. Success → CLOSED, failure → OPEN again.
```

This prevents Celery workers from hammering the Trello API during outages, which would exhaust the rate limit and delay recovery.

#### Retry with Exponential Backoff

```python
@retry(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    exceptions=(httpx.HTTPError, asyncio.TimeoutError),
)
async def fetch_board_data(...): ...
```

---

## 11. AI Assistant & Vector Layer

### 11.1 Architecture (Pure In-Browser, No External API)

The SprintAssistant is a fully client-side RAG (Retrieval-Augmented Generation) system. This is a deliberate architectural choice to avoid:
- External API costs for every query
- Data privacy concerns (sprint data never leaves the browser)
- Network latency for chat responses

```
┌──────────────────────────────────────────────────────────────────────┐
│                  SprintAssistant (Browser-Side Only)                  │
│                                                                      │
│  ┌─────────────┐     ┌───────────────────────────────────────────┐  │
│  │  User Input  │     │             VectorDB (TF-IDF)              │  │
│  │  (text/voice)│     │                                           │  │
│  └──────┬───────┘     │  Documents indexed on data change:       │  │
│         │             │  ┌─────────────────────────────────────┐ │  │
│  ┌──────▼───────┐     │  │ type: "ticket"                      │ │  │
│  │ detectIntent │     │  │ text: "T-1234 | Login fails | done"  │ │  │
│  │   (12 rules) │     │  ├─────────────────────────────────────┤ │  │
│  └──────┬───────┘     │  │ type: "blocker"                     │ │  │
│         │             │  │ text: "T-5678 | API timeout | 48h"  │ │  │
│  ┌──────▼───────┐     │  ├─────────────────────────────────────┤ │  │
│  │ vectorDb     │     │  │ type: "developer"                   │ │  │
│  │  .search()   │◄────┤  │ text: "Alice | 5 done | blocked"    │ │  │
│  │ (cosine sim) │     │  ├─────────────────────────────────────┤ │  │
│  └──────┬───────┘     │  │ type: "sprint"                      │ │  │
│         │             │  │ text: "Sprint 12 | 60% done | 3d"   │ │  │
│  ┌──────▼───────┐     │  └─────────────────────────────────────┘ │  │
│  │generateResp()│     │  TF-IDF: log((N+1)/(df+1)) + 1           │  │
│  │ (template    │     │  Cosine similarity for ranking            │  │
│  │  + RAG data) │     └───────────────────────────────────────────┘  │
│  └──────┬───────┘                                                     │
│         │                                                             │
│  ┌──────▼───────┐                                                     │
│  │  renderMark  │     ┌────────────────────────────────────────────┐  │
│  │  down(text)  │     │         Voice Input (Web Speech API)        │  │
│  └──────────────┘     │   SpeechRecognition → text → same pipeline  │  │
│                        └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 11.2 TF-IDF Vector Search

The VectorDB uses smoothed IDF to handle new (unseen) terms gracefully:

```
IDF(term, t) = log( (N+1) / (df(t)+1) ) + 1

where:
  N     = total number of documents in the index
  df(t) = number of documents containing term t
  +1    = Laplace smoothing (prevents division by zero for new terms)

Cosine similarity for query q against document d:
  sim(q, d) = (q · d) / (||q|| × ||d||)

Pre-computed document norms at index build time → O(|q|) query time
```

**Intent detection runs before vector search** to route queries to the correct generator, preventing cosine similarity from returning irrelevant documents (e.g., a "velocity" query shouldn't surface blocker documents):

```
Query: "who is blocked right now?"
  ─► detectIntent() → "blockers"
  ─► vectorDb.search(query, topK=5, filterType="blocker")
  ─► generateBlockersList(results, context)
  ─► "There are 3 active blockers: T-234 (48h, Level 2), ..."
```

---

## 12. Security Architecture

### 12.1 API Security

```
┌──────────────────────────────────────────────────────────────┐
│                   Security Controls                           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  CORS                                                  │  │
│  │  • Explicit origins whitelist (not *)                  │  │
│  │  • Credentials: true for cookie-based auth (future)    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Trello Webhook Verification                           │  │
│  │  • HMAC-SHA1 over (body + callback_url)                │  │
│  │  • Secret = api_token (per-board, per-credential)      │  │
│  │  • Returns 403 on invalid signature                    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Input Validation                                      │  │
│  │  • All request bodies validated by Pydantic v2         │  │
│  │  • min_length/max_length on Trello credentials         │  │
│  │  • TicketStatus transition guards (domain layer)       │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  SQL Injection Prevention                              │  │
│  │  • SQLAlchemy ORM — all values parameterised           │  │
│  │  • No raw SQL strings constructed from user input      │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 12.2 Secrets Management

All sensitive values are environment variables, never committed to the repository:

| Secret | Env Var | Usage |
|---|---|---|
| DB credentials | `DATABASE_URL` | SQLAlchemy engine URL |
| Redis password | `REDIS_URL` | Celery broker + cache |
| Trello API key | `TRELLO_API_KEY` | Fallback for sync if not in DB |
| Trello token | `TRELLO_API_TOKEN` | Fallback for sync if not in DB |
| Slack webhook | `SLACK_WEBHOOK_URL` | Blocker notifications |
| SMTP password | `SMTP_PASSWORD` | Email notifications |

Trello credentials are additionally persisted in the `trello_credentials` table (per-project) and the `trello_app_settings` singleton table, encrypted at rest via PostgreSQL-level encryption (future).

---

## 13. Observability & Monitoring

### 13.1 Three Pillars

```
┌───────────────────────────────────────────────────────────────────────┐
│                      Observability Stack                               │
│                                                                       │
│  LOGS                          METRICS                  HEALTH        │
│  ─────                         ───────                  ──────        │
│  structlog (JSON)              Prometheus               GET /health   │
│                                                                       │
│  Format:                       Exported at:             Checks:       │
│  {                             GET /metrics             • DB ping     │
│    "event": "...",                                      • Redis ping  │
│    "level": "info",            Metrics:                 • Returns:    │
│    "timestamp": "...",         HTTP_REQUESTS_TOTAL      {"status":    │
│    "logger": "trello.sync",    HTTP_REQUEST_DURATION     "healthy",   │
│    "board_id": 42,             BLOCKER_DETECTIONS_TOTAL  "database":  │
│    "duration_ms": 234          OPEN_BLOCKERS_GAUGE        "connected",│
│  }                             TICKETS_SCANNED_TOTAL     "redis":     │
│                                KPI_COMPUTATION_DURATION   "connected"}│
└───────────────────────────────────────────────────────────────────────┘
```

### 13.2 Prometheus Metrics Detail

| Metric | Type | Labels | Measures |
|---|---|---|---|
| `http_requests_total` | Counter | method, path, status_code | Request volume by endpoint |
| `http_request_duration_seconds` | Histogram | method, path | Latency distribution |
| `blocker_detections_total` | Counter | mismatch_type | Blocker detection rate |
| `open_blockers` | Gauge | escalation_level | Current blocker depth by level |
| `tickets_scanned_total` | Counter | — | Quality scan throughput |
| `kpi_computation_duration_seconds` | Histogram | — | KPI computation cost |
| `repo_mismatches_total` | Counter | mismatch_type | Repository mismatch rate |

---

## 14. Deployment Architecture

### 14.1 Docker Compose Service Map

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Docker Compose Stack                            │
│                                                                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐  │
│  │  postgres   │    │   redis     │    │         api              │  │
│  │  (16-alpine)│    │  (7-alpine) │    │  (FastAPI + Uvicorn)     │  │
│  │             │    │             │    │  workers: 4              │  │
│  │  port: 5432 │    │  port: 6379 │    │  port: 8000              │  │
│  │  volume:    │    │  AOF: yes   │    │  healthcheck: /health    │  │
│  │  pg_data    │    │  volume:    │    │  depends_on: pg, redis   │  │
│  │             │    │  redis_data │    │                          │  │
│  │  healthcheck│    │             │    │  env: DATABASE_URL,      │  │
│  │  pg_isready │    │  healthcheck│    │       REDIS_URL,         │  │
│  └──────┬──────┘    │  redis-cli  │    │       TRELLO_*           │  │
│         │           │  ping       │    └──────────┬──────────────┘  │
│         │           └──────┬──────┘               │                  │
│         │                  │              ┌────────▼──────────────┐  │
│         │                  │              │        worker          │  │
│         │                  │              │  (Celery worker)       │  │
│         │                  │              │  concurrency: 4        │  │
│         │                  │              │  queues: default,high  │  │
│         │                  │              └────────┬──────────────┘  │
│         │                  │                       │                  │
│         │                  │              ┌────────▼──────────────┐  │
│         │                  │              │         beat           │  │
│         │                  │              │  (Celery Beat)         │  │
│         │                  │              │  Schedule: crontab     │  │
│         │                  │              └────────┬──────────────┘  │
│         │                  │                       │                  │
│         │                  │              ┌────────▼──────────────┐  │
│         └──────────────────┴──────────────►        flower          │  │
│                                           │  (Monitoring UI)       │  │
│                                           │  port: 5555            │  │
│                                           └───────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 14.2 Startup Sequence

```
1. postgres + redis start (healthcheck passes)
          │
          ▼
2. api starts
   ├── wait for postgres (depends_on: postgres.healthy)
   ├── wait for redis (depends_on: redis.healthy)
   ├── run alembic upgrade head (database migrations)
   ├── initialize WebSocket manager
   ├── initialize event bus (Redis or in-memory based on APP_ENV)
   └── register event subscriptions
          │
          ▼
3. worker starts (depends_on: api.healthy)
   └── connects to Redis broker, registers task handlers
          │
          ▼
4. beat starts (depends_on: worker.healthy)
   └── loads beat schedule, begins firing periodic tasks
          │
          ▼
5. flower starts (depends_on: worker.healthy)
   └── connects to broker, serves monitoring UI on :5555
```

### 14.3 Resource Requirements (Baseline)

| Service | CPU | Memory | Storage |
|---|---|---|---|
| api | 0.5–2 cores | 256–512 MB | — |
| worker | 1–4 cores | 512 MB–1 GB | — |
| beat | 0.1 cores | 64 MB | — |
| postgres | 0.5–2 cores | 512 MB–2 GB | 10 GB+ |
| redis | 0.25 cores | 128–256 MB | 1 GB (AOF) |
| **Total** | **2.35–10 cores** | **1.5–4 GB** | **11 GB** |

---

## 15. Data Flow Walkthroughs

### 15.1 Trello Refresh Flow (Refresh Button)

```
User                Browser              FastAPI             Trello API
 │                     │                    │                     │
 │  click Refresh      │                    │                     │
 │────────────────────►│                    │                     │
 │                     │  POST /trello/     │                     │
 │                     │  projects/42/sync  │                     │
 │                     │───────────────────►│                     │
 │                     │                    │  GET /boards/{id}/  │
 │                     │                    │  actions?since=X    │
 │                     │                    │────────────────────►│
 │                     │                    │◄────────────────────│
 │                     │                    │  [TrelloAPIAction]  │
 │                     │                    │                     │
 │                     │                    │  GET /cards/{id}    │
 │                     │                    │  (affected cards)   │
 │                     │                    │────────────────────►│
 │                     │                    │◄────────────────────│
 │                     │                    │                     │
 │                     │                    │  UPSERT cards       │
 │                     │                    │  (ON CONFLICT)      │
 │                     │  {boards_synced:1} │                     │
 │                     │◄───────────────────│                     │
 │                     │                    │                     │
 │                     │  queryClient       │                     │
 │                     │  .invalidateAll()  │                     │
 │                     │  (React Query)     │                     │
 │  UI re-renders      │                    │                     │
 │◄────────────────────│                    │                     │
```

### 15.2 Blocker Escalation Flow

```
Celery Beat (10 min)
       │
       ▼
detect_blockers task
       │
       ▼
BlockerDetectionService.run_detection_sweep(project_id)
       │
       ├── SELECT tickets WHERE status IN ('in_progress','in_review')
       │   AND last_activity_at < now() - interval '24 hours'
       │
       ├── for each stalled_ticket:
       │       stall_hours = (now - last_activity_at).total_seconds / 3600
       │
       │       if stall_hours >= 72:  level = 3  (Management)
       │       elif stall_hours >= 48: level = 2  (Team Lead)
       │       elif stall_hours >= 24: level = 1  (Developer)
       │
       │       blocker = create_or_update Blocker(
       │                   ticket_id, stall_hours, escalation_level,
       │                   detected_at = now()
       │                 )
       │
       │       if escalation_level increased:
       │           publish BlockerEscalatedEvent
       │           NotificationService.notify_blocker_detected(
       │               ticket_title, ticket_id, stall_hours, level
       │           )
       │           → POST to Slack webhook
       │           → send SMTP email
       │
       └── OPEN_BLOCKERS_GAUGE.labels(level).set(count)
```

### 15.3 KPI Computation Flow

```
TrelloLiveProjectService.build_dashboard(project_id)
       │
       ├── get_primary_board(project_id)
       │       → SELECT board WHERE credential.project_id = pid
       │             ORDER BY last_synced_at DESC LIMIT 1
       │
       ├── TrelloAnalyticsService.compute_board_analytics(board)
       │       → for each card in board:
       │             if entered_done_at AND entered_wip_at:
       │                 cycle_time += entered_done_at - entered_wip_at
       │             if entered_done_at:
       │                 lead_time  += entered_done_at - created_at
       │       → stall detection: flag cards idle > stall_threshold
       │
       ├── ensure_live_sprint(project_id, board)
       │       → committed_points = Σ story_points (all non-closed cards)
       │       → completed_points = Σ story_points WHERE list_type=DONE
       │       → upsert Sprint row (always "active", 14-day window)
       │
       └── build KPIDashboard:
               velocity         = sprint.completed_points
               completion_rate  = completed / committed
               cycle_time_hours = analytics.avg_cycle_time_hours
               lead_time_hours  = analytics.avg_lead_time_hours
               throughput       = analytics.throughput_cards
               open_blockers    = analytics.stalled_count
```

---

## 16. Testing Strategy

### 16.1 Test Pyramid

```
                      ┌──────────────┐
                      │   E2E Tests  │  playwright
                      │ (5-10 tests) │  Full browser scenarios
                      └──────┬───────┘
                             │
               ┌─────────────▼──────────────┐
               │    Integration Tests        │  @testing-library/react
               │   (20-30 tests)             │  Pages + mocked API
               └──────────────┬─────────────┘
                              │
          ┌───────────────────▼────────────────────┐
          │          Unit Tests                     │  vitest
          │     (50+ tests)                         │  Components, hooks, adapters
          │                                         │
          │  Components:  StatusBadge, KpiCard,     │
          │               LoadingSpinner, ErrorState │
          │  Hooks:       useSprintData,            │
          │               useRepositoryMismatches   │
          │  Adapters:    adaptSprint, adaptKpis,   │
          │               adaptTicket, adaptDeveloper│
          │  Contexts:    ProjectContext            │
          └─────────────────────────────────────────┘
```

### 16.2 Test Setup

**Frontend (Vitest + Testing Library):**
```typescript
// src/test/setup.ts
- jsdom environment
- @testing-library/jest-dom matchers
- fetch mocked globally
- React Query client reset between tests
- MSW (Mock Service Worker) handlers for API responses
```

**E2E (Playwright):**
```
tests/
├── dashboard.spec.ts    — Sprint overview, KPI rendering
├── blockers.spec.ts     — Escalation level display
├── tickets.spec.ts      — Filter, sort, quality scores
└── settings.spec.ts     — Trello import flow
```

### 16.3 Backend Test Strategy (Planned)

```python
# pytest configuration in pytest.ini
# Uses NullPool to avoid connection leaks between test sessions

# Test categories:
# Unit:        Services with mocked repositories
# Integration: Repositories against test PostgreSQL (Docker)
# API:         FastAPI TestClient with transactional rollback
```

---

## 17. Architectural Decision Records (ADRs)

### ADR-001: Layered Monolith over Microservices

**Status:** Accepted  
**Context:** The team needs to ship quickly and maintain a single codebase for a tool used by one Scrum team.  
**Decision:** Single FastAPI application with clean internal boundaries (services, repositories, domain events).  
**Consequences:**
- ✅ Single deployment unit, simple debugging, no distributed tracing needed
- ✅ Transactional boundaries are straightforward (single DB)
- ⚠️ If Trello sync needs to scale independently, it must be extracted later

### ADR-002: Trello as Primary Data Source (No Local Ticket Store for Trello Projects)

**Status:** Accepted  
**Context:** Teams already manage work in Trello; duplicating data creates synchronisation complexity.  
**Decision:** `TrelloLiveProjectService` adapts Trello data at query time; no separate Ticket rows are created for Trello cards.  
**Consequences:**
- ✅ No data drift between Trello and KPIMaster
- ✅ Single source of truth for card status
- ⚠️ KPI queries require Trello-specific join patterns

### ADR-003: In-Browser TF-IDF Vector DB for AI Assistant

**Status:** Accepted  
**Context:** Sending sprint data to an external LLM API raises data privacy and cost concerns.  
**Decision:** Pure TypeScript TF-IDF cosine similarity search, all computation in browser.  
**Consequences:**
- ✅ Zero API cost, zero data exfiltration risk
- ✅ Works offline (after initial page load)
- ⚠️ Quality of semantic search is lower than transformer-based embeddings
- ⚠️ Index must be rebuilt on each data change

### ADR-004: SHA-1 Hash for Trello Member ID → Integer Mapping

**Status:** Accepted  
**Context:** Trello member IDs are strings; the application's relational schema uses integer foreign keys.  
**Decision:** Deterministic `int.from_bytes(sha1(member_id)[:6], "big") & 0x7FFFFFFF`  
**Consequences:**
- ✅ Stable, collision probability ~1 in 2^47 (acceptable for team sizes < 100)
- ✅ No separate lookup table or migration needed
- ⚠️ If collision occurs, two members appear as one developer

### ADR-005: `due_complete` Not Used as Done Indicator

**Status:** Accepted  
**Context:** Trello's `due_complete` flag is optional; most teams never set it even for completed cards.  
**Decision:** A card is "Done" if and only if its list classifies as `ListType.DONE`. The `due_complete` flag is ignored for KPI and mismatch detection.  
**Consequences:**
- ✅ Eliminates hundreds of false-positive "mismatches"
- ✅ Aligns with how Scrum teams actually use Trello
- ⚠️ Teams using `due_complete` explicitly lose that signal

---

## 18. Known Limitations & Future Roadmap

### 18.1 Current Limitations

| Area | Limitation | Impact |
|---|---|---|
| **Trello Auth** | Credentials stored in plaintext in DB | Medium — encrypt at rest |
| **Single Board** | `get_primary_board()` returns one board per project | Multi-board sprints not supported |
| **No User Auth** | No login/logout — all projects visible to all users | Internal tool only |
| **Simulated Git** | `RepositoryAnalyzerService` simulates git data | Repo mismatches are not real |
| **AI Quality** | TF-IDF quality lower than embeddings | Chat responses can miss semantic context |
| **No Audit Log** | No history of who changed what | Cannot support SOC-2 compliance |

### 18.2 Roadmap

```
Phase 1 (Q2 2026) — Foundation Hardening
├── Encrypt Trello credentials at rest (Fernet symmetric)
├── Add JWT authentication (FastAPI-Users)
├── Connect real GitHub/GitLab API for repository data
└── Add multi-board support to live_project_service

Phase 2 (Q3 2026) — Intelligence Upgrade
├── Replace TF-IDF with transformers.js (all-MiniLM-L6-v2)
├── Add anomaly detection on velocity trends (Z-score)
├── Sprint retrospective auto-generation
└── Predictive blocker detection (regression on stall patterns)

Phase 3 (Q4 2026) — Scale & Compliance
├── Read replica for analytics queries
├── Audit log table (who changed what, when)
├── Role-based access control (Project Manager / Developer / Observer)
├── Extract Trello sync into a dedicated microservice
└── OpenTelemetry distributed tracing
```

---

## Appendix A — Project Structure Reference

```
sprint-tracker/
├── backend/
│   ├── app/
│   │   ├── api/v1/          — FastAPI routers (9 files)
│   │   ├── core/            — Logging, exceptions, Prometheus metrics
│   │   ├── domain/          — Value objects, domain events
│   │   ├── infrastructure/  — Event bus, WebSocket manager, Celery
│   │   ├── models/          — SQLAlchemy ORM models (15 files)
│   │   ├── repositories/    — Generic + concrete repositories (5 files)
│   │   ├── schemas/         — Pydantic v2 request/response schemas (11 files)
│   │   ├── services/        — Business logic services (9 files + trello/ sub-package)
│   │   ├── config.py        — Pydantic Settings from env
│   │   ├── database.py      — AsyncEngine, session factory
│   │   └── main.py          — FastAPI app factory, middleware, lifespan
│   ├── alembic/             — DB migrations (3 versions)
│   ├── docker-compose.yml   — 6-service container stack
│   └── requirements.txt     — Python dependencies
│
├── src/
│   ├── components/          — Reusable React components (+ 40 shadcn/ui)
│   ├── contexts/            — ProjectContext (global project state)
│   ├── hooks/               — useSprintData + 2 utility hooks
│   ├── pages/               — 8 route pages
│   ├── services/api/        — Type-safe API layer + adapters (7 files)
│   ├── test/                — Unit + integration tests
│   ├── App.tsx              — Route configuration
│   ├── main.tsx             — React 18 root
│   └── index.css            — Tailwind + CSS variables
│
├── public/
│   ├── favicon.svg          — KPIMaster brand mark (inline SVG)
│   └── robots.txt
│
├── index.html               — Entry HTML, OG meta tags
├── vite.config.ts           — Vite + SWC configuration
├── tailwind.config.ts       — Custom design tokens
├── tsconfig.app.json        — TypeScript strict config
└── ARCHITECTURE.md          — This document
```

---

## Appendix B — API Quick Reference

```
Base URL: http://localhost:8000/api/v1

Projects
  GET    /projects                    List all projects
  POST   /projects                    Create project
  GET    /projects/{id}               Get project detail
  GET    /projects/{id}/sprints/current  Active sprint
  GET    /projects/{id}/sprints/velocity Velocity history (last 5)

Sprints
  GET    /sprints/{id}/burndown        Burndown chart data
  POST   /sprints/{id}/burndown/refresh Recompute burndown

Tickets
  GET    /tickets?project_id=X        List tickets (paginated)
  POST   /tickets/scan                Trigger quality scan
  GET    /tickets/{id}/quality        Ticket quality report

KPIs
  GET    /kpis?project_id=X           KPI dashboard
  POST   /kpis/compute?project_id=X  Force recompute

Blockers
  GET    /blockers?project_id=X       Enriched blocker list
  GET    /blockers/summary            Count by escalation level
  POST   /blockers/detect             Trigger detection sweep

Trello
  GET    /trello/settings             Saved credentials
  POST   /trello/settings             Save credentials
  POST   /trello/available-boards     List accessible boards
  POST   /trello/import-boards        Import + full sync
  POST   /trello/projects/{id}/sync   Incremental sync (Refresh button)
  GET    /trello/projects/{id}/board-summary  Per-list card counts + KPIs
  POST   /trello/boards/{id}/reclassify-lists Re-apply classification

Repository
  GET    /repository-mismatches?project_id=X  All cards + stall flags

WebSocket
  WS     /ws?project_id=X            Real-time event stream

Health
  GET    /health                      Database + Redis status
  GET    /metrics                     Prometheus metrics
```

---

*Document maintained by the Norma Tunisie engineering team. For questions, contact the KPIMaster project lead.*

*Powered by **Norma Tunisie** — Building intelligent development tools for modern engineering teams.*
