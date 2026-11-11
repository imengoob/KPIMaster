# KPIMaster App Graphs and Design Pack

This file contains visual graphs and design references for KPIMaster.

## 1) System Architecture Graph

```mermaid
flowchart TB
  Users[Users<br/>Client Vendor Developer PM Executive Admin]
  Web[Web App<br/>React TypeScript]
  Mobile[Mobile App<br/>React Native Expo]
  API[FastAPI API<br/>Auth Roles Project Scope]
  DB[(PostgreSQL)]
  Redis[(Redis)]
  Workers[Celery Worker and Beat]
  Integrations[Integrations<br/>Trello Jira Planner GitHub]
  WS[WebSocket Channels]

  Users --> Web
  Users --> Mobile
  Web --> API
  Mobile --> API
  API --> DB
  API --> Redis
  Workers --> DB
  Workers --> Redis
  Integrations --> API
  API --> WS
  WS --> Web
  WS --> Mobile
```

## 2) End-to-End Delivery Flow

```mermaid
sequenceDiagram
  participant D as Developer
  participant PM as PM or Delivery Lead
  participant E as Executive or Client
  participant UI as KPIMaster UI
  participant API as FastAPI
  participant W as Workers
  participant R as Realtime

  D->>UI: Update ticket progress
  UI->>API: POST ticket update
  API->>W: Trigger scoring and blocker checks
  W->>API: Publish KPI and blocker events
  API->>R: Push project update
  R->>PM: Show updated sprint health
  R->>E: Show updated delivery summary
```

## 3) Persona Journey Graph

```mermaid
journey
  title KPIMaster Cross Persona Journey
  section Developer
    Login and restore session: 5: Developer
    Update ticket status and notes: 4: Developer
    Review personal dashboard: 4: Developer
  section PM
    Review sprint KPIs: 5: PM
    Detect blocker and escalate: 4: PM
    Track team progress risk: 5: PM
  section Client and Executive
    Open client progress view: 5: Client, Executive
    Confirm scoped delivery status: 4: Client, Executive
    Review risk summary and trends: 4: Client, Executive
```

## 4) Product Surface Map

```mermaid
flowchart LR
  Auth[Auth<br/>Login Logout Session Restore]
  Dash[Dashboards<br/>Role Aware]
  Sprint[Sprint Monitor]
  Tickets[Tickets and Quality]
  Blockers[Blocker Detection and Escalation]
  Repo[Repository Mismatch]
  Integrate[Integrations]
  Assist[Assistant RAG Lite]
  Realtime[Realtime WebSocket]

  Auth --> Dash
  Dash --> Sprint
  Dash --> Tickets
  Dash --> Blockers
  Dash --> Repo
  Dash --> Integrate
  Dash --> Assist
  Sprint --> Realtime
  Tickets --> Realtime
  Blockers --> Realtime
  Repo --> Realtime
  Integrate --> Realtime
```

## 5) Data Model Snapshot

```mermaid
erDiagram
  USER ||--o{ PROJECT_ACCESS : can_view
  PROJECT ||--o{ SPRINT : contains
  PROJECT ||--o{ TICKET : tracks
  TICKET ||--o{ BLOCKER : may_create
  PROJECT ||--o{ KPI_SNAPSHOT : reports
  PROJECT ||--o{ REPOSITORY_MISMATCH : detects
  PROJECT ||--o{ INTEGRATION_ACCOUNT : connects
```

## 6) Design System Direction

### Visual goals

- Clear hierarchy for operational decisions
- Strong contrast for risk states
- Dense but readable KPI surfaces
- Touch-safe controls for mobile

### Color tokens

| Token | Hex | Usage |
| --- | --- | --- |
| `--bg` | `#0B1220` | Primary dark background |
| `--surface` | `#111B2E` | Cards and panels |
| `--text` | `#EAF1FF` | Main text |
| `--muted` | `#94A3B8` | Secondary text |
| `--ok` | `#16A34A` | Healthy status |
| `--warn` | `#D97706` | Watch status |
| `--danger` | `#DC2626` | Risk and blocker status |
| `--info` | `#0284C7` | Informational accents |

### Typography direction

- Headings: `Space Grotesk` or `Manrope`
- Body: `Inter` or `Plus Jakarta Sans`
- Numeric KPI values: tabular figures enabled

### Spacing and layout rules

- Base spacing scale: `4 8 12 16 24 32`
- Card radius: `8px`
- Minimum touch target on mobile: `44px`
- Dashboard grid: 12-column desktop, 4-column mobile

## 7) Mobile Navigation Blueprint

```mermaid
flowchart TB
  Login[Login]
  Home[Home Dashboard]
  Projects[Project Picker]
  Sprint[Sprint KPIs]
  Tickets[Tickets]
  Blockers[Blockers]
  Repo[Repository]
  Integrations[Integrations]
  Assistant[Assistant]
  Profile[Profile and Logout]

  Login --> Home
  Home --> Projects
  Home --> Sprint
  Home --> Tickets
  Home --> Blockers
  Home --> Repo
  Home --> Integrations
  Home --> Assistant
  Home --> Profile
```

## 8) Validation Dashboard Graph

```mermaid
pie title Persona Scenario Validation Coverage
  "Passed scenarios" : 31
  "Skipped external credential scenario" : 1
  "Failed scenarios" : 0
```

