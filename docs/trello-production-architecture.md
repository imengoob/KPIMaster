# Trello Production Architecture

This document describes a production-ready Trello integration for KPIMaster, tailored to the current FastAPI + Celery + Redis + Postgres stack in this repository.

## Current Baseline

The codebase already includes several strong primitives:

- `backend/app/services/trello/client.py`
  - async Trello client
  - Redis-backed rate limiting
  - retry and circuit breaker behavior
- `backend/app/services/trello/sync_service.py`
  - full sync and incremental sync
  - idempotent upserts for boards, lists, cards, and actions
- `backend/app/services/trello/webhook_service.py`
  - webhook registration
  - webhook signature verification
  - idempotent action handling
- `backend/app/infrastructure/workers/tasks.py`
  - Celery polling fallback and analytics jobs

The main production gaps are:

- credentials are stored in plaintext
- no first-class auth provider abstraction
- no token lifecycle metadata
- no dedicated repositories for Trello credentials and boards
- no webhook reconciliation / repair job
- no tenant-aware scheduling strategy for large multi-user scale

## Target Architecture

Use a ports-and-adapters shape with these layers:

1. API layer
   - FastAPI endpoints for connect, disconnect, board discovery, import, webhook receive, and status.

2. Application services
   - `TrelloAuthService`
   - `TrelloConnectionService`
   - `TrelloSyncOrchestrator`
   - `TrelloWebhookService`

3. Repositories
   - `TrelloCredentialRepository`
   - `TrelloBoardRepository`
   - `TrelloWebhookRepository`
   - `SyncJobRepository` for job leases and status

4. Infrastructure adapters
   - `TrelloClient`
   - `EncryptedSecretStore`
   - Celery task runner
   - Redis rate limiter / distributed lock

5. Persistence
   - Postgres for metadata
   - Redis for rate limiting, locks, dedupe windows, and queue coordination
   - KMS or Vault backed encryption for secrets at rest

## Recommended Data Model

Split credential metadata from secret material.

### `trello_connections`

- `id`
- `tenant_id` or `user_id`
- `project_id`
- `provider` (`token`, `oauth1`, `oauth2`)
- `member_id`
- `member_username`
- `status` (`active`, `reauth_required`, `revoked`, `error`)
- `last_validated_at`
- `last_sync_at`
- `last_webhook_at`
- `token_expires_at` nullable
- `created_at`
- `updated_at`

### `trello_connection_secrets`

- `connection_id`
- `encrypted_api_key`
- `encrypted_access_token`
- `encrypted_refresh_token` nullable
- `encrypted_token_secret` nullable
- `kms_key_id` or `vault_path`
- `secret_version`
- `rotated_at`

### `trello_sync_jobs`

- `id`
- `board_id`
- `job_type` (`full`, `incremental`, `reconcile`, `webhook_repair`)
- `status`
- `started_at`
- `finished_at`
- `attempt_count`
- `last_error`
- `worker_id`

This lets you rotate secrets independently, track auth state cleanly, and observe sync reliability.

## Authentication Strategy

### Best option

Prefer OAuth if your Trello app flow supports it for your product experience. If you stay on API key + token, treat the token as a long-lived secret and store it like a password.

### Persistence

Do not require users to re-enter Trello credentials every session.

Store:

- connection metadata in Postgres
- encrypted secret material in either:
  - AWS KMS envelope encryption
  - HashiCorp Vault transit engine
  - cloud secrets manager with per-tenant secret references

Avoid storing raw tokens directly in the DB without encryption.

### Token lifecycle

Trello tokens are often effectively long-lived, but the system should still support expiration or revocation.

Store and monitor:

- `token_expires_at`
- `last_validated_at`
- `last_auth_error_at`
- `status`

On every auth failure:

1. mark the connection as `reauth_required` only after repeated failures
2. stop noisy retries
3. surface the issue in UI and logs
4. preserve imported project data in read-only mode until reconnect

## Webhooks vs Polling

### Recommended production strategy

Use both.

- Webhooks are the primary near real-time path.
- Polling is the safety net.

### Webhook path

Use board-level Trello webhooks for:

- card creation
- card movement
- comments
- label changes
- assignment changes

On webhook receipt:

1. verify signature
2. dedupe by Trello action ID
3. update only impacted entities
4. enqueue a lightweight follow-up sync for affected cards if needed

### Polling fallback

Keep incremental polling every 3 to 10 minutes depending on tenant tier and board activity.

Use polling for:

- webhook delivery gaps
- backfill after worker downtime
- webhook registration drift
- periodic reconciliation

### Reconciliation job

Run a slower full consistency job every 6 to 24 hours:

- verify webhook still exists
- verify board metadata
- replay recent actions if needed
- detect missed cards or list changes

## Scaling Strategy

### Multi-user, multi-board

Do not run one giant global sync loop forever.

Instead:

- enqueue work per board
- shard tasks by tenant or board ID
- use Redis locks to prevent concurrent syncs on the same board
- maintain a per-API-key rate budget

### Queue design

Recommended Celery queues:

- `trello_webhooks`
- `trello_incremental`
- `trello_full_sync`
- `trello_reconcile`

### Concurrency controls

Use:

- one distributed lock per board sync
- one rate limiter bucket per Trello API key
- queue priorities so webhook follow-ups run before background reconciliation

## Error Handling and Resilience

### Retry policy

Retry:

- timeouts
- transient network failures
- 429 rate limits
- 5xx responses

Do not blindly retry:

- invalid credentials
- revoked token
- missing board permissions

### Recommended backoff

- exponential backoff with jitter
- cap retries
- dead-letter or mark failed after repeated attempts

### Observability

Track metrics:

- sync duration by board
- webhook latency
- webhook failure count
- rate-limit sleeps
- auth failure count
- stale board count
- queue lag by task type

## Clean Architecture Layout

Recommended package structure:

```text
backend/app/
  api/v1/trello.py
  services/trello/
    auth_service.py
    connection_service.py
    sync_service.py
    webhook_service.py
    reconciliation_service.py
  repositories/
    trello_connection_repository.py
    trello_board_repository.py
    trello_webhook_repository.py
    trello_sync_job_repository.py
  infrastructure/
    security/
      secret_store.py
      kms_secret_store.py
    workers/
      tasks.py
```

## Example FastAPI Implementation

### 1. Secret store interface

```python
from typing import Protocol


class SecretStore(Protocol):
    async def encrypt(self, plaintext: str) -> str: ...
    async def decrypt(self, ciphertext: str) -> str: ...
```

### 2. Connection repository

```python
from sqlalchemy import select

from app.models.trello_credential import TrelloCredential


class TrelloCredentialRepository:
    def __init__(self, session):
        self.session = session

    async def get_active_for_project(self, project_id: int) -> TrelloCredential | None:
        result = await self.session.execute(
            select(TrelloCredential).where(
                TrelloCredential.project_id == project_id,
                TrelloCredential.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def save(self, credential: TrelloCredential) -> TrelloCredential:
        self.session.add(credential)
        await self.session.flush()
        await self.session.refresh(credential)
        return credential
```

### 3. Auth service

```python
from dataclasses import dataclass

from app.models.trello_credential import TrelloCredential
from app.services.trello.client import TrelloClient


@dataclass
class TrelloConnectionResult:
    member_id: str
    username: str


class TrelloAuthService:
    def __init__(self, secret_store, credential_repo):
        self.secret_store = secret_store
        self.credential_repo = credential_repo

    async def connect_project(self, project_id: int, api_key: str, api_token: str) -> TrelloConnectionResult:
        async with TrelloClient(api_key=api_key, api_token=api_token) as client:
            me = await client.get_me()

        credential = await self.credential_repo.get_active_for_project(project_id)
        encrypted_token = await self.secret_store.encrypt(api_token)

        if credential is None:
            credential = TrelloCredential(
                project_id=project_id,
                api_key=api_key,
                api_token=encrypted_token,
                is_active=True,
            )
        else:
            credential.api_key = api_key
            credential.api_token = encrypted_token
            credential.is_active = True

        await self.credential_repo.save(credential)
        return TrelloConnectionResult(member_id=me.id, username=me.username)
```

### 4. Client factory

Never pass encrypted tokens directly to `TrelloClient`. Use a factory that decrypts just-in-time.

```python
class TrelloClientFactory:
    def __init__(self, secret_store):
        self.secret_store = secret_store

    async def from_credential(self, credential):
        token = await self.secret_store.decrypt(credential.api_token)
        return TrelloClient(api_key=credential.api_key, api_token=token)
```

### 5. Background sync orchestration

```python
from redis.asyncio import Redis


class TrelloSyncOrchestrator:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def acquire_board_lock(self, board_id: int) -> bool:
        return bool(await self.redis.set(f"trello:sync-lock:{board_id}", "1", ex=300, nx=True))
```

Use this in Celery tasks before calling `full_sync` or `incremental_sync`.

### 6. Webhook-first flow

FastAPI endpoint:

```python
@router.post("/webhooks/{trello_webhook_id}/receive", status_code=200)
async def receive_trello_webhook(trello_webhook_id: str, request: Request, session: DbSession):
    raw = await request.body()
    webhook = await session.scalar(
        select(TrelloWebhook).where(TrelloWebhook.trello_webhook_id == trello_webhook_id)
    )
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    credential = await session.scalar(
        select(TrelloCredential)
        .join(TrelloBoard, TrelloBoard.credential_id == TrelloCredential.id)
        .where(TrelloBoard.id == webhook.board_id)
    )
    # Decrypt before signature verification if the token or secret is encrypted.
```

### 7. Periodic reconciliation task

```python
@celery_app.task(name="app.infrastructure.workers.tasks.trello_reconcile_board")
def trello_reconcile_board(board_id: int) -> dict:
    async def _run():
        async with get_db_context() as session:
            # load board + credential + webhook
            # verify webhook exists
            # compare last_webhook_at vs last_sync_at
            # run incremental sync or full repair if stale
            return {"board_id": board_id, "reconciled": True}

    return asyncio.run(_run())
```

## Security Best Practices

1. Encrypt Trello tokens at rest.
2. Mask tokens in logs, traces, and admin responses.
3. Restrict DB access because encrypted blobs are still sensitive.
4. Rotate encryption keys with version metadata.
5. Store callback signing data separately from display metadata.
6. Validate webhook signatures before parsing payloads deeply.
7. Apply least privilege to worker, API, and DB credentials.
8. Do not expose raw tokens back to the frontend after initial connect.
9. Add audit logging for connect, disconnect, reconnect, and webhook registration events.

## Recommended Changes for This Repo

### High priority

1. Encrypt `TrelloCredential.api_token` instead of storing plaintext.
2. Add `TrelloCredentialRepository`.
3. Add `TrelloAuthService` and `TrelloClientFactory`.
4. Add board-level distributed locks in Celery sync tasks.
5. Add webhook reconciliation and stale-webhook repair jobs.
6. Add connection status fields: `last_validated_at`, `last_auth_error_at`, `reauth_required`.

### Medium priority

1. Split secret material into a dedicated table.
2. Add Prometheus or OpenTelemetry metrics around sync jobs.
3. Add dead-letter handling or failure counters for repeatedly failing boards.
4. Route Trello jobs onto dedicated Celery queues.

### Nice to have

1. Per-tenant sync scheduling based on board activity.
2. Adaptive polling intervals.
3. Admin dashboard for connection health and webhook drift.

## Recommended Strategy Summary

For production, the best pattern is:

- persist credentials once, encrypted
- decrypt only at execution time
- use webhooks as the primary near real-time path
- keep incremental polling as a safety net
- run periodic reconciliation for correctness
- queue all heavy sync work in background workers
- enforce board locks and rate-limit budgets centrally

That combination gives you durability, user convenience, resilience, and scale without depending on webhooks alone.
