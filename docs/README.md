# KPIMaster Documentation Hub

This page is the entry point for KPIMaster documentation.

## Start Here

- [Project README](../README.md): product overview, stack summary, route map, setup, and test commands.
- [Architecture](../ARCHITECTURE.md): full technical architecture and design decisions.
- [Backend Guide](../backend/README.md): backend structure, APIs, workers, and operational behavior.
- [Mobile App Guide](../mobile/README.md): React Native + Expo setup, mobile quality checks, and APK generation.

## Product and Persona Docs

- [Personas and Integrations](./personas-and-integrations.md): role model and provider mapping.
- [Persona Productivity Guide](./persona-productivity-guide.md): role-by-role workflows and productivity outcomes.
- [Feature Deep Dive](./feature-deep-dive.md): detailed behavior for core product capabilities.
- [Persona Scenario Test Matrix](./persona-scenario-test-matrix.md): executed cross-persona validation matrix with pass/fail status.
- [App Graphs and Design Pack](./app-graphs-and-designs.md): visual graphs, flows, and design system reference.

## Demo, Validation, and Operations

- [Demo and Validation Runbook](./demo-and-validation-runbook.md): end-to-end demo and release validation flow.
- [Technical & Operations Manual](./technical-operations-manual.md): runtime operations, observability, and troubleshooting.
- [Platform Details](./platform-details.md): system context and platform-level behavior.
- [Trello Production Architecture](./trello-production-architecture.md): Trello reliability and production integration details.

## Business and Presentation Assets

- [Business Document](./business-document.md): business strategy, KPIs, and delivery model.
- [Client Presentation Pack](./client-presentation-pack.md): slide-ready storytelling and client-facing narrative.

## Quick Validation Commands

Frontend web:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

Backend (Docker API container):

```bash
cd backend
docker-compose exec -T api python -m pytest tests -q
curl -sf http://localhost:8000/health
```

Mobile:

```bash
cd mobile
npm run typecheck
npm run lint
npm run test
```

Local APK generation (Expo prebuild + Gradle):

```bash
cd mobile
export EXPO_PUBLIC_API_BASE_URL=http://YOUR_LAN_IP:18000
npm run build:android:apk:local
```
