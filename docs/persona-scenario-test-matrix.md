# KPIMaster Persona Scenario Test Matrix

Date: 2026-05-19

Environment:
- Frontend: Vite dev server and production build
- Backend: isolated Docker stack on `http://localhost:18000`
- Database: PostgreSQL 16 seeded demo data
- Cache/queue: Redis 7 with Celery worker and beat

Legend:
- PASS: scenario executed successfully for the persona or verified by automated coverage
- PASS-GUARD: persona is intentionally redirected, blocked, or shown a scoped empty state
- SKIP-EXT: requires live third-party credentials that were not available in this environment

Seeded persona coverage:

| Persona | Accounts exercised | Primary ownership expectation |
| --- | --- | --- |
| Client | `horizon_admin` | Client navigation, company dashboards, project-scoped delivery visibility |
| Vendor | `hexadev_admin` | Vendor navigation, assigned developer delivery visibility |
| Developer | `alice_account`, `david_account`, `grace_account` | Personal dashboard/history, blocked from company-owned pages |
| Project manager / delivery lead | `retail_pm`, `novaforge_delivery` | PM or delivery-lead dashboards scoped to assigned organization/project |
| Executive | `horizon_exec` | Executive-safe client progress and KPI visibility |
| Admin | E2E registered admin-like account plus seeded platform data | Full shell smoke coverage, settings/integration access, project workspace flows |

## Cross-Persona Process Matrix

This matrix validates product processes that cross persona boundaries. The goal is to confirm that one persona's action changes only the correct downstream views and that restricted personas are guarded safely.

| Scenario ID | Scenario category | Primary persona | Secondary / affected persona(s) | Preconditions | Steps to execute | Expected result | Actual result | Pass / Fail | UI surfaces involved | Backend/API behavior involved | Realtime/WebSocket expectation | Notes / bugs found | Fix required? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CP-001 | Login / logout / session restore | Admin | All authenticated personas | Seeded backend and auth API are available. | Register/login through API, persist browser storage, open dashboard, sign out, sign back in. | Session restores from token; logout clears access; protected routes require login. | Auth setup and sign-out/sign-in E2E passed. | PASS | `/login`, `/dashboard`, protected route shell | `/api/v1/auth/register`, `/api/v1/auth/login`, current-user/session calls | No broadcast expected. | None. | No |
| CP-002 | Role-based navigation and unauthorized access | Guest / Developer | Admin, Client, Vendor, PM, Executive | Seeded persona accounts exist. | Open protected routes as guest; log in as developer and attempt company-owned pages; log in as client/vendor roles. | Guest is sent to login; developer sees developer-owned routes; client/vendor/PM/executive see scoped nav. | Persona navigation E2E passed for guest, client admin, executive, PM, vendor admin, delivery manager, and developers. | PASS | Sidebar, route guards, `/developer-dashboard`, `/client-progress`, `/vendor-dashboard` | Auth user profile and role metadata | No broadcast expected. | None. | No |
| CP-003 | Admin project access and project-scoped data | Admin | Client, Vendor, Developer, Executive | Projects, companies, partnerships, and users are seeded. | Validate project switcher and route ownership; compare client/vendor/developer page access. | Each persona sees only assigned project/company data; forbidden pages redirect or show guards. | Project-scoped dashboard, delivery views, recruiting network, and persona navigation tests passed. | PASS | Project selector, dashboard, delivery views, recruiting network | Project list, company membership, developer visibility, partnership APIs | Project-specific updates should target only subscribed project/global listeners. | None. | No |
| CP-004 | Sprint KPI review and executive summary | PM / delivery lead | Executive, Client, Vendor | Live or seeded sprint exists. | PM opens sprint monitor/dashboard; executive/client views inspect summarized delivery status. | PM sees operational sprint KPIs; executive/client see appropriate summarized progress. | Sprint monitor, dashboard, client progress, and vendor delivery E2E/unit coverage passed. | PASS | `/sprint-monitor`, `/dashboard`, `/client-progress`, `/vendor-dashboard` | Sprint, KPI, burndown, vendor/client reporting APIs | KPI mutation events should broadcast to project/global subscribers. | None. | No |
| CP-005 | Ticket list and ticket detail flow | PM / delivery lead | Developer, Vendor, Client | Seeded tickets or live-project empty state are available. | Open ticket analysis and sprint monitor; verify ticket rows/content or clear empty state. | Ticket quality and status data render without broken loading, empty, or error states. | Ticket analysis E2E and frontend unit tests passed. | PASS | `/ticket-analysis`, `/sprint-monitor`, dashboard ticket widgets | Tickets, quality scoring, sprint adapter APIs | Ticket status changes should broadcast project-scoped updates. | None. | No |
| CP-006 | Developer activity updates downstream views | Developer | PM, Vendor, Client, Executive | Developer is assigned to a seeded project. | Open developer dashboard/history; verify related delivery pages reflect approved assignment/progress. | Developer-owned activity is visible to allowed vendor/client/PM views and hidden from unauthorized scopes. | Developer dashboard/history, client progress, vendor dashboard, recruiting network, and visibility request E2E passed. | PASS | `/developer-dashboard`, `/developer-history`, `/client-progress`, `/vendor-dashboard`, `/recruiting-network` | Developer progress, visibility request, partnership APIs | Developer activity events should broadcast to project listeners. | None. | No |
| CP-007 | Blocker detection and escalation | Developer / PM | Vendor, Client, Executive | Blocker detection data or safe empty state exists. | Open blocker detection and dashboard views; inspect blocked/stalled ticket state. | PM/vendor see actionable blocker details; client/executive see delivery risk at the right level. | Blocker detection E2E passed; worker scan tasks ran without structured logging or event-loop errors. | PASS | `/blocker-detection`, dashboard blocker cards, vendor/client summaries | Blocker, ticket scan, notification/task APIs | Blocker-created events should broadcast to project/global listeners. | None. | No |
| CP-008 | Blocker resolution propagation | PM / delivery lead | Developer, Vendor, Client, Executive | A blocker exists or empty-state path is available. | Refresh/sync blocker surfaces and verify resolved/empty states do not look broken. | Resolution or no-blocker state is clear; dashboards do not show stale critical alerts. | Empty/no-blocker and blocker page states covered by unit/E2E tests; worker logs clean. | PASS | `/blocker-detection`, dashboard risk widgets | Blocker resolution/status APIs and worker tasks | Resolution events should broadcast project-scoped updates. | No manual live mutation was performed in this environment; automated coverage validates states and worker stability. | No |
| CP-009 | Ticket quality scoring | PM / delivery lead | Developer, Vendor, Client | Ticket quality engine has seeded or adapted ticket content. | Open ticket analysis; verify poor-quality/open ticket signals and dashboard aggregates. | Quality issues are visible to operational personas and summarized appropriately elsewhere. | Ticket analysis E2E plus adapter/unit coverage passed. | PASS | `/ticket-analysis`, dashboard quality widgets | Ticket analysis and scoring adapters | Quality recomputation should broadcast project-scoped update if persisted. | None. | No |
| CP-010 | Repository mismatch monitoring | PM / Admin | Developer, Vendor, Executive | Repository integration page is available. | Open repository monitoring as admin/PM/vendor-capable persona; verify restricted personas are guarded. | Technical mismatch signals are visible to operational roles; executive sees high-level risk only through summary surfaces. | Repository integration E2E and delivery-view smoke tests passed. | PASS | `/repository-integration`, `/repository` | Repository integration and mismatch APIs | Repository mismatch updates should broadcast project-scoped update. | None. | No |
| CP-011 | Integration sync success and provider handoff | Admin | PM, Client, Vendor, Executive | Integration hub is available; live backend stack is healthy. | Open integrations hub, Trello settings, Jira OAuth handoff, Microsoft Planner OAuth handoff. | Provider cards load; OAuth handoff returns external authorization URL; downstream pages show data or clear guards. | Trello settings, provider cards, Jira handoff, Microsoft handoff, platform-filter guard tests passed. | PASS | `/integrations`, `/settings`, platform filter, provider guards | Integration account, OAuth handoff, Trello settings, provider sync APIs | Sync events should broadcast project/global integration status updates. | None. | No |
| CP-012 | Integration failure / missing credential states | Admin | All personas | GitHub live token is not configured; demo mode still available. | Run optional live GitHub connection E2E and provider guard flows. | Missing external credentials should skip or show graceful setup/error state, not fail the suite. | GitHub PAT test skipped because `E2E_GITHUB_TOKEN` was absent; other integration flows passed. | PASS / SKIP-EXT | `/integrations`, provider cards, error/empty banners | Provider connection APIs | Failed sync/status updates should broadcast safe error state when applicable. | External live credentials were not available. | No, credential needed |
| CP-013 | Assistant / RAG-lite queries across roles | Client / PM / Developer | All personas | Dashboard data is loaded or empty-state data is available. | Open floating assistant and ask a sprint/ticket question. | Assistant indexes visible dashboard data in-browser and responds without external AI dependency. | Sprint assistant E2E passed; hook dependency warnings were fixed. | PASS | Floating assistant, dashboard pages | No external AI API; reads frontend query data | No broadcast expected. | None. | No |
| CP-014 | WebSocket / realtime infrastructure | Backend event producer | All open browser personas | API stack, event bus, and WebSocket manager are available. | Connect global/project WebSocket endpoints and broadcast through manager tests. | Global listeners receive global/project events; project listeners receive only scoped project events. | Backend WebSocket endpoint and manager tests passed; Docker worker/API health remained green. | PASS | Realtime listeners backing dashboard refresh behavior | `/api/v1/ws/global`, `/api/v1/ws/projects/{id}`, event bus, WebSocketManager | Project and global broadcast isolation expected. | Browser E2E validates UI after refresh; backend tests validate socket mechanics directly. | No |
| CP-015 | Empty states | New workspace / restricted persona | Admin, Client, Vendor, Developer | Fresh E2E account has no projects; platform filter can select unsupported provider. | Open dashboard/project switcher and Trello-only pages with non-Trello filter. | Empty and guard states are visible, readable, and actionable. | Dashboard empty project, live-project empty state, no-project, no-record, and platform guard tests passed. | PASS | Dashboard, project switcher, provider guard, reporting pages | Project list and provider-scoped APIs return empty/guard responses | No broadcast expected. | None. | No |
| CP-016 | Error states | Any persona | All personas | Queries can fail or be mocked into error state. | Execute unit tests for dashboard, vendor, responsiveness, blockers, tickets, and settings error paths. | User sees explicit recovery/error UI instead of blank or broken screens. | Frontend unit error-state coverage passed. | PASS | ErrorState components across dashboards/settings | API error wrappers and React Query errors | No broadcast expected. | None. | No |
| CP-017 | Desktop and mobile responsiveness | Mobile user | All personas | App shell is available on desktop and mobile widths. | Open dashboard shell and navigation on mobile; run full browser suite on desktop viewport. | Navigation, text, controls, and content remain visible with no off-screen sidebar issue. | Added mobile drawer/layout test; full Playwright suite passed after responsive shell fix. | PASS | App shell, sidebar, header, main content | No special API behavior beyond normal page queries | No broadcast expected. | Previous mobile sidebar overflow was fixed. | No |

## Persona Category Matrix

| Scenario category | Expected result | Client | Vendor | Developer | PM / delivery lead | Executive | Admin | Actual notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Login / logout / session restore | Users can authenticate, preserve session state, and sign out/in cleanly. | PASS | PASS | PASS | PASS | PASS | PASS | `auth.setup.ts` registers and restores a session; `auth.spec.ts` validates sign-out/sign-in. |
| Role-based navigation | Sidebar and landing route match persona ownership. | PASS | PASS | PASS | PASS | PASS | PASS | `persona-navigation.spec.ts` verified client, vendor, developer, PM, executive, and guest routing. |
| Dashboard visibility | Each persona sees only relevant dashboard surfaces. | PASS | PASS | PASS | PASS | PASS | PASS | Company dashboards, vendor views, and developer-owned dashboards render or redirect correctly. |
| Project selection and scoped data | Project switcher and project data stay scoped to accessible workspaces. | PASS | PASS | PASS-GUARD | PASS | PASS | PASS | Dashboard/project E2E covers empty and live scoped states; developer guard prevents company-page access. |
| Sprint KPI review | Sprint monitor and KPI cards load or show clear empty states. | PASS | PASS | PASS-GUARD | PASS | PASS | PASS | Sprint monitor, dashboard, and backend KPI tests passed. |
| Ticket list and detail flows | Ticket analysis surfaces real tickets or clear empty/error states. | PASS | PASS | PASS-GUARD | PASS | PASS | PASS | `ticket-analysis.spec.ts` and unit coverage validate loading, error, and real-ticket rendering. |
| Blocker detection / escalation / resolution | Blocker page renders live blockers or safe empty states; backend tasks run without worker errors. | PASS | PASS | PASS-GUARD | PASS | PASS | PASS | `blocker-detection.spec.ts`, worker logs, and backend task tests passed. |
| Ticket quality analysis | Quality scoring data is visible from ticket analysis and dashboard flows. | PASS | PASS | PASS-GUARD | PASS | PASS | PASS | Ticket analysis E2E plus adapter/unit tests passed. |
| Repository mismatch monitoring | Repository integration page renders mismatch-monitoring surfaces where allowed. | PASS | PASS | PASS-GUARD | PASS | PASS | PASS | `repository-integration.spec.ts` and delivery view smoke tests passed. |
| Integration states and sync behavior | Provider cards, OAuth handoffs, Trello settings, and sync refresh behave safely. | PASS | PASS | PASS-GUARD | PASS | PASS | PASS / SKIP-EXT | Jira and Microsoft OAuth handoffs passed; live GitHub PAT test skipped because `E2E_GITHUB_TOKEN` was absent. |
| Assistant / RAG-lite queries | Assistant opens, indexes visible data, and responds without external AI dependency. | PASS | PASS | PASS | PASS | PASS | PASS | `sprint-assistant.spec.ts` passed; hook dependency warnings were removed. |
| WebSocket / realtime behavior | WebSocket endpoints accept connections and project/global broadcasts are isolated. | PASS | PASS | PASS | PASS | PASS | PASS | Backend WebSocket endpoint and manager tests passed; Docker stack health stayed green. |
| Empty states | Empty project/workspace/provider states are readable and actionable. | PASS | PASS | PASS | PASS | PASS | PASS | E2E and unit tests cover fresh workspace, no project, no records, and platform guards. |
| Error states | API/query errors show explicit UI feedback instead of broken screens. | PASS | PASS | PASS | PASS | PASS | PASS | Unit tests cover dashboard, vendor, responsiveness, tickets, blockers, and settings error states. |
| Unauthorized access | Protected routes require login; persona-forbidden pages redirect or guard. | PASS | PASS | PASS | PASS | PASS | PASS | Guest and developer unauthorized access paths passed in `persona-navigation.spec.ts`. |
| Mobile and desktop responsiveness | Layout keeps text and controls visible on mobile and desktop. | PASS | PASS | PASS | PASS | PASS | PASS | Added mobile drawer/layout test; full Playwright suite passed after responsive shell fix. |

Verification commands:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
docker run --rm -v "$PWD/backend:/app" -w /app python:3.12-slim bash -lc "pip install -q -r requirements.txt -r requirements-test.txt && pytest tests"
curl -sf http://localhost:18000/health
VITE_API_BASE_URL=http://localhost:18000 npm run test:e2e
```

Results:
- Frontend unit tests: 201 passed
- Backend tests: 290 passed
- Browser E2E: 31 passed, 1 skipped optional live GitHub-token test
- Health check: database and Redis healthy
- Worker log scan: no task failures, event-loop errors, structured logging errors, or missing session-factory errors
