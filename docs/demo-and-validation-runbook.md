# Demo and Validation Runbook

Use this runbook when preparing KPIMaster for a demo, release review, or end-to-end validation pass.

Related references:

- [Documentation Hub](./README.md)
- [Mobile App Guide](../mobile/README.md)
- [Persona Scenario Test Matrix](./persona-scenario-test-matrix.md)

## Demo Goal

The demo should prove that KPIMaster works for the main personas and that sprint, delivery, developer, repository, and integration flows are connected end to end.

The minimum demo-ready outcome is:

- frontend builds and loads
- backend starts and passes health checks
- database migrations run
- demo data exists
- login works
- role-specific navigation works
- all demo-critical pages load without fatal errors
- Trello, Jira, GitHub, and Microsoft Planner integration entry points behave correctly for the configured environment
- Playwright E2E tests pass for the critical flows

Strict data rule: demo-critical E2E flows should use the real frontend, real backend, and real local database state. Do not replace internal app API responses with fake Playwright payloads to make a scenario pass. If a live third-party credential is missing, document the gap and validate the app wiring or safe failure state instead.

## Quick Start For A Local Demo

From the backend folder:

```sh
cd backend
cp .env.example .env
docker-compose up -d postgres redis api
docker-compose exec -T api alembic upgrade head
docker-compose exec -T api python scripts/seed.py
docker-compose exec -T api python scripts/validate_data_quality.py --profile demo
```

From the repository root:

```sh
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

Open the Vite URL printed in the terminal and sign in with:

```text
username: e2e
password: E2ePassword1!
```

## Focused Norma/Tawssil Demo

If the demo story is about Norma as the client, Tawssil as the vendor, and Hejer as the developer, seed the focused flow:

```sh
cd backend
docker-compose exec -T api python seed_demo_flow.py
```

Accounts:

| Username | Password | Role | What to show |
| --- | --- | --- | --- |
| `norma_admin` | `Password123!` | `client_admin` | Client delivery visibility for Norma Base Project. |
| `tawssil_admin` | `Password123!` | `esn_admin` | Vendor visibility into assigned developer work. |
| `hejer_dev` | `Password123!` | `developer` | Personal developer progress and assigned ticket context. |

## Pre-Demo Health Checks

Run these before presenting:

```sh
curl -sf http://localhost:8000/health
npm run build
npm run test
(cd backend && docker-compose exec -T api python scripts/validate_data_quality.py --profile demo)
VITE_API_BASE_URL=http://localhost:8000 npm run test:e2e
```

Expected local E2E behavior:

- With no `E2E_GITHUB_TOKEN`, the live GitHub connection test is skipped. This is intentional and safer than faking a GitHub account.
- With `E2E_GITHUB_TOKEN` set to a valid PAT, the GitHub connection test should run against GitHub and pass.
- Jira and Microsoft Planner E2E validates OAuth start and outbound handoff URL generation locally. Full callback completion requires real OAuth app credentials and redirect URIs.
- Trello board discovery/import requires a real Trello API key and token.

Backend test pass:

```sh
cd backend
docker-compose exec -T api python -m pytest tests -q
```

Backend coverage pass:

```sh
cd backend
docker-compose exec -T api python -m pytest tests --cov=app --cov-report=term-missing
```

## Mobile Validation Pass (Expo)

Run this when the release/demo scope includes the React Native app.

Choose API base URL by runtime:

- Android emulator with backend on local docker-compose: `http://10.0.2.2:8000`
- Android emulator with isolated audit stack: `http://10.0.2.2:18000`
- Physical device on same network: `http://YOUR_LAN_IP:18000`

Mobile quality checks:

```sh
cd mobile
npm install
npm run typecheck
npm run lint
npm run test
```

Mobile app launch:

```sh
cd mobile
EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000 npm run start
```

Local APK verification:

```sh
cd mobile
EXPO_PUBLIC_API_BASE_URL=http://YOUR_LAN_IP:18000 npm run build:android:apk:local
```

Expected result: APK build succeeds and core persona flows (login, project switch, dashboard, tickets, blockers, integrations, assistant) remain usable on mobile screens.

## Demo Walkthrough

### 1. Authentication

1. Open `/login`.
2. Sign in as `e2e`.
3. Confirm the app routes to the dashboard or role default page.
4. Refresh the page.
5. Confirm the session restores through `/api/v1/auth/me`.
6. Sign out.
7. Sign back in.

Expected result: authentication is stable and no stale data from a previous user appears.

### 2. Project and dashboard

1. Open `/dashboard`.
2. Use the project switcher.
3. Select `PHX`, `ATL`, or `NOV`.
4. Confirm KPI cards and delivery content update.
5. Append a project query param such as `?project=PHX`.

Expected result: selected project drives visible data consistently.

### 3. Sprint monitor

1. Open `/sprint`.
2. Confirm active sprint, burndown, velocity, and sprint health content render.
3. Switch projects.
4. Confirm the sprint data changes or a clean empty state appears.

Expected result: no fatal error state, and the page is useful for live demo discussion.

### 4. Ticket analysis

1. Open `/tickets`.
2. Confirm tickets render with status, priority, type, and assignment context.
3. Inspect a project with seeded tickets.
4. Confirm empty project state is clear if no imported project data exists.

Expected result: tickets are readable and connected to project selection.

### 5. Blocker detection

1. Open `/blockers`.
2. Confirm blockers are visible for seeded projects.
3. Trigger available blocker actions.
4. Confirm success or error feedback is clear.

Expected result: escalation states and actions are understandable.

### 6. Developer progress

1. Open `/developers`.
2. Confirm team-level developer cards or table rows render.
3. Select a developer if the UI supports detail expansion.
4. Confirm KPI, progress, risk, and activity information appears.

Expected result: client/vendor/developer interpretations remain clear.

### 7. Client progress

1. Open `/client-progress`.
2. Confirm the page shows delivery summary, assigned developers, progress, blockers, and risk notes.
3. Switch projects.

Expected result: the page is suitable for customer-facing progress review.

### 8. Vendor dashboard

1. Sign in as `hexadev_admin` or `novaforge_delivery`.
2. Open `/vendor-dashboard`.
3. Confirm vendor-specific delivery status is visible.
4. Confirm unrelated client data is not exposed.

Expected result: vendor users see only appropriate vendor scope.

### 9. Developer dashboard and history

1. Sign in as `alice_account`, `david_account`, or `grace_account`.
2. Open `/developer-dashboard`.
3. Open `/developer-history`.
4. Confirm personal KPI and visibility-request pages load.

Expected result: developer pages feel personal and scoped.

### 10. Repository integration

1. Open `/repository`.
2. Confirm repository mismatch data loads for projects with seeded repository activity.
3. Run a manual repository scan if available.
4. Confirm date or platform filters do not break the page.

Expected result: repository state helps explain delivery mismatch risk.

### 11. Integrations hub

1. Open `/integrations`.
2. Confirm Trello, Jira, Microsoft Planner, and GitHub provider cards render.
3. Confirm connected accounts appear if configured.
4. Test provider health where credentials exist.
5. Test safe error states where credentials are missing.

Expected result: integration entry points are visible, actions are understandable, and failures are demo-safe.

### 12. Trello-specific settings

1. Open `/settings`.
2. Confirm Trello settings load.
3. If credentials are available, list boards and import one.
4. Open dashboards after import.

Expected result: imported board data becomes selectable as a project and does not require a page reload beyond normal query refresh.

### 13. Responsiveness analytics

1. Open `/responsiveness`.
2. Confirm metrics and developer rows render.
3. Change date range if available.
4. Confirm charts or metrics update without layout breakage.

Expected result: responsiveness page is clear for manager and vendor review.

### 14. Sprint assistant

1. Open the assistant.
2. Ask about blockers, sprint progress, and developer risk.
3. Confirm answers are based on indexed project data.

Expected result: assistant is helpful and does not block normal page navigation.

## Persona Validation Matrix

| Persona | Account | Must pass |
| --- | --- | --- |
| Solution owner / broad demo user | `e2e` | Dashboard, project switcher, all main pages, integrations, settings, E2E smoke. |
| Client admin | `horizon_admin` | Client projects, dashboard, sprint, tickets, blockers, client progress, repository. |
| Client executive | `horizon_exec` | Summary pages, client progress, dashboard readability. |
| Client PM | `retail_pm` | Retail One project visibility and project-level flows. |
| Vendor admin | `hexadev_admin` | Vendor dashboard, developer progress, responsiveness, blockers. |
| Vendor delivery manager | `novaforge_delivery` | Vendor scope and delivery manager workflows. |
| Developer | `alice_account` | Developer dashboard, team developers, client history. |

## Integration Validation Matrix

| Provider | Success state | Failure state | E2E expectation |
| --- | --- | --- | --- |
| Trello | Connect, list boards, import board, sync, dashboard refresh. | Invalid key/token, no boards, sync failure. | Provider card/settings page load locally; live board list/import requires real Trello credentials. |
| Jira | OAuth start URL, callback, account appears, boards/issues sync. | Missing config, invalid state, token failure. | Real backend returns Atlassian authorization URL; full callback needs configured OAuth credentials. |
| GitHub | PAT connect, health check, repository/task sync. | Invalid token, insufficient scopes, API failure. | Live connect test runs only with `E2E_GITHUB_TOKEN`; otherwise skipped, not mocked. |
| Microsoft Planner | OAuth start URL, callback, account appears, plans/tasks sync. | Missing config, invalid state, token failure. | Real backend returns Microsoft authorization URL; full callback needs configured OAuth credentials. |

## E2E Coverage Map

| Spec | Flow |
| --- | --- |
| `e2e/auth.spec.ts` | Sign out and sign back in. |
| `e2e/dashboard.spec.ts` | Dashboard shell, project selection, empty state. |
| `e2e/sprint-monitor.spec.ts` | Sprint monitor page. |
| `e2e/ticket-analysis.spec.ts` | Sprint and ticket pages with real project data. |
| `e2e/blocker-detection.spec.ts` | Blocker page and empty-state resilience. |
| `e2e/delivery-views.spec.ts` | Developer, client, and repository delivery views. |
| `e2e/repository-integration.spec.ts` | Repository integration dashboard. |
| `e2e/integrations-settings.spec.ts` | Trello settings, provider cards, optional live GitHub connect via `E2E_GITHUB_TOKEN`, Jira/Microsoft OAuth handoff. |
| `e2e/platform-filter.spec.ts` | Global platform filter behavior using real seeded project data. |
| `e2e/sprint-assistant.spec.ts` | Sprint assistant open and interaction. |
| `e2e/recruiting-network.spec.ts` | B2B recruiting and developer visibility request flows using real API-created local records. |

## Release Readiness Checklist

- `docker-compose ps` shows backend dependencies running.
- `alembic upgrade head` completes.
- Standard or focused seed completes.
- `/health` returns healthy or explicitly degraded but usable status.
- Frontend build succeeds.
- Frontend unit tests pass.
- Backend tests pass.
- Playwright E2E tests pass.
- Mobile typecheck/lint/tests pass when mobile app is in scope.
- APK build check passes (`mobile` local Gradle build or EAS profile) when Android delivery is in scope.
- No demo-critical page shows a fatal error state.
- Each persona can access its own page set.
- Each provider card is visible and behaves correctly for configured credentials.
- Known missing provider credentials are explained as environment setup, not app failure.
- Remaining risks are documented before the demo.

If a suite reports `31 passed, 1 skipped` and the skipped test is the live GitHub connection test, the local app/API/database validation passed but GitHub was not live-validated. Set `E2E_GITHUB_TOKEN` and rerun if GitHub live connection must be part of the demo claim.

## Strict Demo Rule

Do not mark the project demo-ready if any of these are true:

- login is unstable
- project switcher is broken
- seeded data is missing
- dashboard, sprint, ticket, blocker, developer, client progress, repository, integrations, or settings pages crash
- a persona sees clearly unauthorized data
- integration failures appear as blank screens or unhandled exceptions
- E2E tests fail for the path being demoed

## Recommended Final Command Set

Run this final pass when time is short:

```sh
curl -sf http://localhost:8000/health
npm run build
npm run test
VITE_API_BASE_URL=http://localhost:8000 npm run test:e2e
(cd mobile && npm run typecheck && npm run lint && npm run test)
```

Then manually sign in as:

- `e2e`
- one client account
- one vendor account
- one developer account

Open their default pages and the most important demo pages before presenting.
