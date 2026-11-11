# Personas and Integrations

This document describes how KPIMaster is expected to behave for each major user persona and each supported integration provider. Use it as the product-level map for QA, demo preparation, onboarding, and future feature work.

## Persona Model

The application stores the user's role on the `users.role` column. The frontend maps the role into navigation and default pages in `src/contexts/AuthContext.tsx`, `src/App.tsx`, and `src/components/AppSidebar.tsx`. The backend enforces company, project, and developer visibility through `backend/app/api/authz.py`.

Terminology note:

- **Vendor** is the product term for outsourcing companies.
- `esn_admin` and `esn_delivery_manager` are legacy role names that still represent vendor users.
- `companies.tenant_type` should normally be `client` or `vendor`.
- Some compatibility code still accepts `tenant_type="esn"` for older records, but new seeds and registrations should use `vendor`.

| Persona | Roles | Main goal | Default route |
| --- | --- | --- | --- |
| Solution owner | `super_admin`, Norma solution-owner company user | Operate across all clients, vendors, projects, and developers. | `/dashboard` |
| Client admin | `company_admin`, `client_admin` | Manage client-side project visibility and monitor delivery. | `/dashboard` |
| Client PM | `company_manager`, `client_pm` | Track sprint execution, tickets, blockers, and vendor performance. | `/dashboard` |
| Client executive | `client_exec` | Review delivery health, progress, risk, and vendor responsiveness. | `/dashboard` |
| Vendor admin | `esn_admin` | Track vendor developers and client assignments. | `/developers` |
| Vendor delivery manager | `esn_delivery_manager` | Monitor active delivery risks and developer performance. | `/developers` |
| Developer | `developer` | Track personal KPIs, assigned work, and client visibility requests. | `/developers` |
| Auditor | `auditor_readonly` | Inspect project and delivery state without operational changes. | `/dashboard` |

## Role And Page Matrix

| Page | Solution owner | Client users | Vendor users | Developer | Auditor |
| --- | --- | --- | --- | --- | --- |
| `/dashboard` | Full | Company projects | Not primary | Redirected away by company-only guard | Read-oriented |
| `/sprint` | Full | Company projects | Not primary | Not primary | Read-oriented |
| `/tickets` | Full | Company projects | Not primary | Not primary | Read-oriented |
| `/blockers` | Full | Company projects | Vendor engagements | Not primary | Read-oriented |
| `/developers` | Full | Visible engagement developers | Vendor developers | Team and own context | Read-oriented |
| `/developer-dashboard` | Full | Optional | Optional | Personal dashboard | Read-oriented |
| `/developer-history` | Full | Optional | Optional | Client history and visibility requests | Read-oriented |
| `/client-progress` | Full | Client-facing project view | Not primary | Not primary | Read-oriented |
| `/vendor-dashboard` | Full | Optional | Vendor delivery view | Not primary | Read-oriented |
| `/repository` | Full | Company projects | Optional | Not primary | Read-oriented |
| `/integrations` | Full | Connect/manage provider accounts | Usually hidden by sidebar | Not primary | Read-oriented if exposed |
| `/settings` | Full | Company/project configuration | Hidden in sidebar | Hidden in sidebar | Read-oriented if exposed |
| `/responsiveness` | Full | Company projects | Vendor developers | Not primary | Read-oriented |
| `/recruiting-network` | Full | Client vendor discovery | Optional | Not primary | Read-oriented |

## Expected Persona Behavior

### Solution owner

- Can see every project and developer.
- Can use all dashboard, delivery, integration, and settings pages.
- Can validate end-to-end flows across clients and vendors.
- Should be the primary role for broad demos and release verification.

### Client admin and client PM

- Can see projects linked to their company through `company_project_access` or engagement relationships.
- Can monitor project KPIs, sprint status, ticket quality, blockers, repository mismatches, and client progress.
- Can manage settings and integration setup where the UI exposes those actions.
- Should not see unrelated vendor-only or unrelated client data.

### Client executive

- Can review high-level delivery status without needing implementation detail.
- Expected pages include dashboard and client progress.
- The UI should emphasize summary health, completion, risk, responsiveness, and blocker count.

### Vendor admin and vendor delivery manager

- Can see developers managed by their vendor company.
- Can see engagement-level delivery health for linked client projects.
- Sidebar focuses on vendor dashboard, developer progress, responsiveness, and blockers.
- Should not gain access to client projects with no vendor engagement or project access.

### Developer

- Should land in a developer-centered experience.
- Can see personal dashboard and team developer view.
- Can inspect client history and approve or reject visibility requests.
- Backend access should be scoped to the linked `developer_id` unless explicitly allowed by a visibility or engagement rule.

### Auditor

- Should have enough visibility for audit and reporting workflows.
- Should not perform destructive or operational actions unless the backend explicitly allows them.

## Authorization Rules To Preserve

- Super admins and the Norma solution-owner company can operate globally.
- Company users must have direct company/project access or engagement-based access.
- Vendor users see vendor-managed developers and vendor-linked project work.
- Developer users can only access their own developer KPI subject unless a specific visibility workflow grants more context.
- Integration accounts are user-owned. A user can only manage accounts where `integration_accounts.user_id` matches their authenticated user.

## Integration Model

External tools are normalized through the `TaskProvider` interface:

```text
IntegrationAccount
  |
  | ProviderRegistry.build(account)
  v
TaskProvider implementation
  |-- validate_credentials()
  |-- get_boards()
  |-- get_tasks(board_id)
  |-- get_comments(task_id)
  |-- create_task(board_id, data)
  |-- update_task(task_id, data)
  `-- sync_board(board_id)
```

Normalized records are represented as boards, tasks, and comments. This lets the rest of the application reason about Trello cards, Jira issues, Microsoft Planner tasks, and GitHub issues or pull requests through shared concepts.

## Supported Provider Matrix

| Provider | Backend adapter | Connection | Current UI entry | Critical validation | Live credential requirement |
| --- | --- | --- | --- | --- | --- |
| Trello | `backend/app/integrations/providers/trello/adapter.py` plus Trello services | API key + token | `/integrations`, `/settings` | Connect, health check, board list, import board, sync, Trello-specific analytics, webhooks | Real API key and user token |
| Jira | `backend/app/integrations/providers/jira/adapter.py` | OAuth 2.0 | `/integrations` | Start OAuth, callback, store account, health check, board/project list, issue sync | Atlassian OAuth app credentials and callback URL |
| Microsoft Planner | `backend/app/integrations/providers/microsoft/adapter.py` | OAuth 2.0 | `/integrations` | Start OAuth, callback, store account, health check, plan list, task sync | Microsoft OAuth app credentials and callback URL |
| GitHub | `backend/app/integrations/providers/github/adapter.py` | Personal access token | `/integrations`, repository flows | Connect, health check, repository/issue/PR mapping, sync, repository mismatch visibility | Real PAT; E2E uses `E2E_GITHUB_TOKEN` when available |

Do not mark a provider as live-validated unless real credentials were used against that provider. Local E2E can validate app wiring, provider cards, OAuth handoff URL generation, safe error states, and real database-backed workflows without proving the external account itself.

## Trello Flow

1. User opens `/integrations` or `/settings`.
2. User connects Trello with API key and token.
3. Backend validates credentials and stores encrypted secrets.
4. User lists Trello boards.
5. User imports a board.
6. Backend creates or links a KPIMaster project.
7. Backend syncs normalized tasks and, for Trello-specific pages, Trello board/list/card/action tables.
8. Dashboards, developer progress, client progress, blocker detection, responsiveness, and ticket analysis can consume imported data.
9. Webhook endpoints can receive Trello board updates when configured with a public callback URL.

Critical tests:

- Missing key/token fails with a clear error.
- Invalid credentials return an actionable health failure.
- Board list renders empty, loading, success, and error states.
- Import creates/selects a project and refreshes project context.
- Sync logs record success and failure.
- Imported cards map to statuses, story points, labels, assignees, and activity timestamps.

## Jira Flow

1. User clicks Jira connect in `/integrations`.
2. Frontend calls `/api/v1/integrations/oauth/jira/start`.
3. Backend returns an Atlassian authorization URL and state.
4. User completes consent in Atlassian.
5. Atlassian redirects to `/api/v1/integrations/oauth/jira/callback`.
6. Backend exchanges the code, stores encrypted tokens, and redirects to the frontend.
7. User sees the connected Jira account.
8. User can list accessible projects/boards and sync issues through the generic integration API.

Critical tests:

- Start endpoint requires an authenticated user.
- Missing OAuth config fails clearly.
- Callback validates state.
- Tokens are encrypted before storage.
- Provider health reflects valid and invalid credentials.
- Sync stores normalized issues without provider-specific fields leaking into UI assumptions.

## GitHub Flow

1. User opens `/integrations`.
2. User connects GitHub with a personal access token.
3. Backend validates the token through the GitHub adapter.
4. Connected account appears in the provider list.
5. Repository, issue, pull-request, or mismatch data can be synced or analyzed.
6. Repository pages surface ticket/repository mismatches.

Critical tests:

- Invalid token fails safely.
- Valid token creates an active integration account.
- Health check validates credentials.
- Sync logs capture provider failure details.
- Repository mismatch queries can be filtered by project, date range, and platform.
- Playwright only runs the live GitHub connect test when `E2E_GITHUB_TOKEN` is set; otherwise it is skipped instead of mocked.

## Microsoft Planner Flow

1. User clicks Microsoft Planner connect in `/integrations`.
2. Frontend calls `/api/v1/integrations/oauth/microsoft/start`.
3. Backend returns a Microsoft authorization URL and state.
4. User completes consent.
5. Microsoft redirects to `/api/v1/integrations/oauth/microsoft/callback`.
6. Backend stores encrypted tokens and tenant metadata.
7. User lists plans and syncs tasks through the generic integration API.

Critical tests:

- OAuth start and callback behavior matches Jira expectations.
- Tenant metadata is persisted in `extra_data`.
- Plan/task fields normalize into shared board/task models.
- Disconnect clears encrypted tokens and marks the account inactive.

## Cross-Persona Integration Expectations

| Scenario | Expected behavior |
| --- | --- |
| Client admin connects Trello | Account belongs to that user and imported project becomes visible to allowed company users. |
| Client admin imports Jira project | Imported work should appear in dashboard pages where provider filters include Jira. |
| Vendor admin views client project | Access depends on engagement or project access, not just having a vendor role. |
| Developer opens integration page directly | The app may render route access, but backend account ownership and data access still protect secrets and data. |
| Super admin validates integrations | Can inspect all high-level platform pages, but integration account APIs remain scoped to the authenticated account unless designed otherwise. |
| Disconnected provider | Account is inactive, tokens are cleared, board/task calls should fail or disappear from active lists. |

## Real Data Versus Test Doubles

- Playwright E2E tests should use the real frontend, backend, auth, and local database for demo-critical flows.
- E2E setup may create temporary real local records through the API, for example client companies, partnerships, and visibility grants.
- E2E should not fulfill internal app API responses with fake payloads for core demo paths.
- Unit and component tests may still mock `fetch`, hooks, or React context because they are verifying isolated frontend behavior rather than full-system readiness.
- Backend pytest may monkeypatch outbound third-party HTTP calls where deterministic unit coverage is required. That is not a substitute for live provider validation.

## Data Consistency Expectations

- A selected project in the sidebar should drive all page queries consistently.
- Date filters and platform filters should be propagated to analytics and developer/repository APIs that support them.
- Imported provider tasks should not overwrite unrelated local project data.
- Sync operations should be idempotent where possible.
- Sync logs should be written for both success and failure.
- Provider-specific failures should not crash unrelated dashboard pages.

## Validation Checklist

- Every persona can sign in with a seeded or manually created account.
- Every persona lands on the expected default page.
- Persona sidebar items match role expectations.
- Protected routes redirect unauthenticated users to `/login`.
- Company-only pages redirect developers away.
- Client users cannot view unrelated client/vendor projects.
- Vendor users cannot view unrelated client work.
- Developer users cannot read another developer's KPI data.
- Trello connect, board list, import, sync, and dashboard refresh work.
- Jira OAuth handoff and callback work with configured credentials.
- GitHub connect and health check work with a valid token.
- Microsoft OAuth handoff and callback work with configured credentials.
- E2E tests cover each demo-critical persona and integration state.
