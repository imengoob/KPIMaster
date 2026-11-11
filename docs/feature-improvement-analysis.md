# KPIMaster Feature Improvement Analysis

Date: 2026-05-19

## Executive Summary

KPIMaster already has a strong foundation for sprint intelligence: project-scoped dashboards, KPI snapshots, blocker detection, ticket quality scoring, repository mismatch checks, responsiveness analytics, multi-provider integrations, role-aware pages, mobile views, and a lightweight sprint assistant.

The most valuable feature improvement is a **Sprint Action Center with approval-based playbooks**.

Today the platform is good at showing what is wrong. The next product leap is to make the corrective workflow explicit: one prioritized queue of recommended actions, assigned owners, due times, approvals, status changes, and audit history. This would move KPIMaster from "delivery intelligence dashboard" toward "delivery operating system."

## Current Product Read

### What the project already does well

- Normalizes delivery data across Trello, Jira, Microsoft Planner, and GitHub-style provider concepts.
- Keeps project context central through `ProjectContext` and project-scoped API queries.
- Enforces role and tenant boundaries across frontend routes and backend dependencies.
- Computes sprint KPIs, burndown, ticket quality, blockers, developer progress, repository mismatches, and responsiveness analytics.
- Offers persona-specific views for clients, vendors, developers, executives, auditors, and platform operators.
- Includes mobile equivalents for the main operational flows.
- Uses Celery and scheduled workers for background scans and syncs.
- Provides notification infrastructure through log, Slack, and email channels.
- Includes an in-browser RAG-lite assistant that can summarize current sprint context without requiring an external LLM.

### Product gap

KPIMaster's positioning asks: "Are we on track to deliver, why are we at risk, and what should happen next?"

The first two parts are well covered. The third part is only partially implemented.

Signals are spread across pages:

- `/blockers` shows escalation levels and dispatch buttons.
- `/ticket-analysis` shows quality problems.
- `/repository` shows ticket/code mismatches.
- `/responsiveness` shows reaction-time issues.
- `/integrations` shows provider health and sync state.
- The floating assistant answers questions, but it does not open or track operational actions.

The result is that a PM or delivery manager still has to decide manually which page matters first, what action to take, who owns it, whether the action was acknowledged, and whether it actually reduced risk.

## Recommended Feature

### Sprint Action Center

A role-aware Action Center that converts KPIMaster signals into tracked operational actions.

Instead of only showing separate warnings, KPIMaster would generate a prioritized queue such as:

| Action | Source signal | Owner | SLA | Status |
| --- | --- | --- | --- | --- |
| Ask developer for update on stalled card | Blocker L1 | Developer | 4h | Open |
| Escalate unresolved payment dependency | Blocker L3 | Delivery lead | 1h | Awaiting approval |
| Add acceptance criteria to low-quality ticket | Ticket quality | PM | Before sprint planning | Open |
| Link PR to ticket or update ticket status | Repository mismatch | Developer | Same day | Open |
| Reconnect expired Jira integration | Integration health | Admin | 2h | Open |
| Prepare executive risk summary | KPI trend + blockers | Client PM | Weekly | Open |

The feature should not be a generic task list. It should be generated from existing KPIMaster intelligence and tied back to source records.

## Evidence From The Current Project

- `README.md` defines the core product question as delivery health, risk cause, and next action.
- `src/App.tsx` shows the current app already has separate role-aware pages for dashboard, sprint, tickets, blockers, repository, integrations, responsiveness, developer views, and recruiting.
- `src/components/SprintAssistant.tsx` and `src/services/ragEngine.ts` show the assistant is currently a contextual Q&A layer over visible dashboard data. It does not create, assign, approve, or resolve workflow items.
- `backend/app/api/v1/blockers.py` exposes blocker action endpoints, but the current action path mainly updates escalation level and `last_escalated_at`.
- `docs/feature-deep-dive.md` describes blocker timeline/history behavior that is not fully represented by a dedicated action-event model yet.
- `backend/app/services/notification_service.py` already has Slack, email, and log channels that can support action dispatch.
- `backend/app/integrations/base.py` already defines normalized provider write operations, which gives a future Action Center a clean path to create or update external tasks with policy controls.
- `backend/app/services/repository_analyzer_service.py` provides mismatch rules that can become another action source while repository ingestion continues to mature.

## Why This Is The Best Next Feature

### 1. It strengthens the core value proposition

The existing docs repeatedly frame KPIMaster around time-to-action, accountability, and "what should happen next." A dedicated Action Center turns that narrative into a visible product surface.

### 2. It reuses most of the existing architecture

The project already has:

- Signal producers: blockers, ticket quality, repository mismatches, responsiveness, integration health, KPI scans.
- Background workers: Celery scheduled jobs.
- Role context: frontend navigation and backend authz.
- Notification channels: Slack, email, logs.
- Real-time patterns: event bus and WebSocket manager.
- Provider write APIs: generic `TaskProvider.create_task()` and `TaskProvider.update_task()`.
- Assistant context: RAG-lite summarization over current dashboard data.

The feature is an orchestration layer over current capabilities, not a rewrite.

### 3. It closes an implementation/documentation mismatch

`docs/feature-deep-dive.md` says blocker actions should be persisted in a timeline/history with events. In the current backend, `POST /blockers/{blocker_id}/action` mainly raises `escalation_level` and sets `last_escalated_at`. There is no visible action history model for who acted, what was sent, who owns follow-up, or whether the action was acknowledged.

The Action Center can close this gap in a product-relevant way instead of adding audit logging as a standalone technical chore.

### 4. It gives every persona a clearer workflow

- Client PM: one morning queue for project risks and communication drafts.
- Vendor delivery manager: one team queue for stalled work, responsiveness, and repo mismatch cleanup.
- Developer: personal queue for blocked tickets, missing updates, low-quality assigned tickets, and PR/ticket consistency.
- Executive: read-only queue of critical unresolved risks and owner status.
- Auditor: evidence trail of action creation, assignment, escalation, acknowledgment, and resolution.
- Platform operator: integration and data-quality action queues across workspaces.

### 5. It can become premium product differentiation

Competitors can show dashboards. Fewer tools combine sprint intelligence, role-aware workflows, approval paths, and auditability in one delivery operating surface.

## Proposed MVP

### MVP scope

Build one new web page: `/actions`.

The first version should generate actions from four existing signal types:

1. Active blockers.
2. Poor ticket quality.
3. Repository mismatches.
4. Integration health or sync failures.

Each action should include:

- `id`
- `project_id`
- `source_type`
- `source_id`
- `title`
- `description`
- `recommended_action`
- `priority`
- `owner_user_id` or `owner_role`
- `status`
- `approval_required`
- `due_at`
- `created_at`
- `updated_at`
- `resolved_at`

Suggested statuses:

- `open`
- `acknowledged`
- `in_progress`
- `awaiting_approval`
- `approved`
- `rejected`
- `resolved`
- `dismissed`

### MVP user experience

The page should be a dense operational queue, not a marketing-style dashboard.

Useful controls:

- Tabs for `My actions`, `Project actions`, `Critical`, and `Resolved`.
- Filters for source, priority, status, owner, project, and due window.
- Action rows with source badge, owner, SLA, and next button.
- Detail drawer showing source evidence and timeline.
- Buttons for acknowledge, assign, approve, dispatch, resolve, dismiss.
- Role-aware disabled states for users who can see but not execute an action.

### MVP backend APIs

Suggested routes:

```text
GET    /api/v1/actions
GET    /api/v1/actions/{id}
POST   /api/v1/actions/generate
PATCH  /api/v1/actions/{id}
POST   /api/v1/actions/{id}/acknowledge
POST   /api/v1/actions/{id}/approve
POST   /api/v1/actions/{id}/reject
POST   /api/v1/actions/{id}/dispatch
POST   /api/v1/actions/{id}/resolve
POST   /api/v1/actions/{id}/dismiss
```

### MVP data model

Add two tables:

```text
action_items
  id
  project_id
  source_type
  source_id
  source_url
  title
  description
  recommended_action
  priority
  owner_user_id
  owner_role
  status
  approval_required
  due_at
  resolved_at
  metadata_json
  created_at
  updated_at

action_events
  id
  action_item_id
  actor_user_id
  event_type
  previous_status
  next_status
  note
  payload_json
  created_at
```

The `action_events` table is important. It gives the product a real operational timeline and supports audit, executive reporting, and SLA metrics.

### Generation rules

Start deterministic and explainable.

| Source | Rule | Action |
| --- | --- | --- |
| Blocker L1 | Active blocker at level 1 | Ask developer for status update |
| Blocker L2 | Active blocker at level 2 | Notify delivery lead and request plan |
| Blocker L3 | Active blocker at level 3 | Create management escalation |
| Ticket quality | Score below 60 | Improve description, estimate, priority, or assignee |
| Repository mismatch | In-progress ticket without commits | Ask assignee to link branch/PR or update ticket |
| Repository mismatch | Done ticket with unmerged PR | Reconcile done status before client reporting |
| Integration health | Credentials invalid or sync failed | Ask integration owner to reconnect or retry |

Each generated action should use a stable deduplication key:

```text
project_id + source_type + source_id + recommended_action
```

This prevents duplicate action spam during scheduled scans.

## Assistant Upgrade Path

After the Action Center exists, upgrade the assistant from Q&A to command-assisted workflow.

Example assistant prompts:

- "What should I do first today?"
- "Create actions for unresolved L2 blockers."
- "Draft a client update for critical actions."
- "Why is this project red?"
- "Show actions waiting on vendor response."

The assistant should not directly perform sensitive operations by default. It should prepare suggested actions and route them through the same approval/status model.

This matches the existing roadmap idea of "deeper assistant actions with policy-based approval paths."

## Success Metrics

Measure the feature by operational outcomes, not just usage.

Recommended metrics:

- Median time from signal detection to action creation.
- Median time from action creation to first acknowledgment.
- Median time from action creation to resolution.
- Percentage of L2/L3 blockers with an owner assigned.
- Percentage of critical actions overdue.
- Number of duplicate or dismissed generated actions.
- Reduction in manual status-report preparation time.
- Number of actions exported into executive/client summaries.

## Implementation Plan

### Phase 1 - Action foundation

- Add `action_items` and `action_events` models and migration.
- Add repository/service layer for action CRUD and timeline writes.
- Add deterministic generator for blockers, ticket quality, and repository mismatches.
- Add backend tests for deduplication, authz, and status transitions.

### Phase 2 - Web Action Center

- Add `/actions` route and sidebar item.
- Build queue table, filters, detail drawer, and role-aware action buttons.
- Add TanStack Query hooks for action list/detail/mutations.
- Add empty states for projects with no generated actions.

### Phase 3 - Notifications and dispatch

- Connect action dispatch to `NotificationService`.
- Track dispatch attempts in `action_events`.
- Add Slack/email payload templates.
- Add audit-safe notes for sent prompts and escalations.

### Phase 4 - Assistant and reporting

- Index action items in the existing RAG-lite assistant.
- Add answer templates for action priority, owner status, and overdue actions.
- Add export-ready action summary for client PM and executive views.

## Risks And Controls

| Risk | Control |
| --- | --- |
| Users get too many generated actions | Deduplicate by source and recommendation, cap low-priority actions, group similar quality issues |
| Sensitive actions are executed by the wrong role | Reuse backend authz and require approvals for escalations or provider writes |
| The feature becomes a generic task manager | Keep every action tied to a KPIMaster source signal |
| Notifications become noisy | Send only on status changes, priority thresholds, or explicit dispatch |
| Generated recommendations feel opaque | Show source evidence and rule name in the action detail drawer |
| Audit history becomes incomplete | Write `action_events` for every state transition and dispatch attempt |

## Other Feature Ideas Considered

### Predictive sprint risk scoring

Useful and already aligned with roadmap notes, but it depends on clean historical data and tuned models. It is a stronger Phase 2 intelligence feature after the action/event trail exists.

### Executive evidence packs

Commercially useful, especially for clients and steering meetings. It becomes much stronger if built on top of action history, because the report can show not only risk but ownership and progress.

### Real GitHub/GitLab repository ingestion

Technically important, especially because repository mismatch simulation still appears in parts of the backend. However, it mainly improves one signal source. The Action Center improves the whole product workflow across signal types.

### Advanced LLM assistant

Attractive, but the current assistant is intentionally local and deterministic. Adding workflow state first gives a future assistant something meaningful and auditable to operate on.

## Final Recommendation

Prioritize the **Sprint Action Center with approval-based playbooks** as the next major feature.

It fits the current architecture, supports every persona, strengthens the product story, closes a real implementation gap around action history, and creates the foundation for future predictive risk scoring, executive packs, and assistant-driven operations.
