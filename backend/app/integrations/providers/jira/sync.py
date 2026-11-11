"""
Jira sync service — pulls issues from Jira and persists them to the DB.

Strategy
────────
  • Full sync   : JQL `project = KEY ORDER BY created ASC` — all issues
  • Incremental : JQL `project = KEY AND updated >= "{last_sync}" ORDER BY updated ASC`
  • Both modes upsert into a generic `integration_tasks` log table (future)
    and emit domain events for the internal event bus.

For now the sync result is returned as a dict summary (count, errors).
A future migration can add a proper `jira_issues` mirror table.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.integrations.base import NormalizedTask
from app.integrations.providers.jira.adapter import JiraAdapter
from app.models.integration_account import IntegrationAccount
from app.models.integration_sync_log import IntegrationSyncLog, SyncStatus, SyncType

logger = get_logger(__name__)


class JiraSyncService:
    """Orchestrates full and incremental syncs for one Jira IntegrationAccount."""

    def __init__(self, session: AsyncSession, account: IntegrationAccount) -> None:
        self._session = session
        self._account = account

    # ── Public API ────────────────────────────────────────────────────────────

    async def full_sync(self, board_id: str) -> dict[str, Any]:
        """Pull all non-done issues for `board_id` (project key)."""
        return await self._run_sync(board_id, incremental=False)

    async def incremental_sync(self, board_id: str) -> dict[str, Any]:
        """Pull issues updated since the account's last_sync_at."""
        return await self._run_sync(board_id, incremental=True)

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _run_sync(self, board_id: str, incremental: bool) -> dict[str, Any]:
        from app.integrations.encryption import safe_decrypt

        log = IntegrationSyncLog(
            account_id=self._account.id,
            provider=self._account.provider,
            board_id=board_id,
            sync_type=SyncType.INCREMENTAL if incremental else SyncType.FULL,
            started_at=datetime.now(timezone.utc),
        )
        self._session.add(log)
        await self._session.flush()

        try:
            adapter = JiraAdapter(
                access_token=safe_decrypt(self._account.encrypted_access_token) or "",
                cloud_id=self._account.extra_data.get("cloud_id", ""),
                account_id=self._account.id,
                refresh_token=safe_decrypt(self._account.encrypted_refresh_token),
            )

            if incremental and self._account.last_sync_at:
                since = (self._account.last_sync_at - timedelta(minutes=5)).strftime(
                    "%Y-%m-%d %H:%M"
                )
                jql = (
                    f'project = "{board_id}" AND updated >= "{since}" '
                    f'ORDER BY updated ASC'
                )
            else:
                jql = f'project = "{board_id}" ORDER BY created ASC'

            # Attempt to sync Agile sprints alongside to capture sprint boundaries
            from app.models.project import Project
            from sqlalchemy import select
            proj_res = await self._session.execute(select(Project).where(Project.key == board_id))
            db_proj = proj_res.scalar_one_or_none()
            if db_proj:
                await self._sync_sprints(adapter, board_id, db_proj.id)

            issues = await adapter._client.search_issues(jql)
            tasks  = [adapter._map_issue(i, board_id) for i in issues]

            # Update account sync timestamp
            self._account.last_sync_at = datetime.now(timezone.utc)
            self._session.add(self._account)

            log.status        = SyncStatus.SUCCESS
            log.items_synced  = len(tasks)
            log.completed_at  = datetime.now(timezone.utc)
            await self._session.flush()

            logger.info(
                "jira.sync_done",
                account_id=self._account.id,
                board_id=board_id,
                synced=len(tasks),
                incremental=incremental,
            )
            return {"synced": len(tasks), "board_id": board_id, "incremental": incremental}

        except Exception as exc:
            log.status       = SyncStatus.FAILED
            log.error_detail = str(exc)[:1000]
            log.completed_at = datetime.now(timezone.utc)
            await self._session.flush()
            logger.error("jira.sync_failed", account_id=self._account.id, error=str(exc))
            raise
        finally:
            await adapter.close()

    async def _sync_sprints(self, adapter: JiraAdapter, project_key: str, project_id: int) -> None:
        """
        Fetch all sprints for the project's Agile board, upsert them.
        If a sprint transitions to 'closed', trigger DeveloperKPI snapshotting.
        """
        from app.models.sprint import Sprint
        from app.services.developer_kpi_service import DeveloperKPIService
        from sqlalchemy import select

        boards = await adapter._client.get_boards()
        target_board = next(
            (b for b in boards if b.get("location", {}).get("projectKey") == project_key), 
            None
        )
        if not target_board:
            return  # No Jira Agile board for this project, just fallback to default sync.

        jira_sprints = await adapter._client.get_board_sprints(target_board["id"])

        for js in jira_sprints:
            sprint_name = js.get("name", "Unknown")
            state = js.get("state", "planning")
            
            # Map Jira state to KPIMaster state
            sp_status = "planning"
            if state == "active":
                sp_status = "active"
            elif state == "closed":
                sp_status = "completed"

            # Check if exists
            result = await self._session.execute(
                select(Sprint)
                .where(Sprint.project_id == project_id)
                .where(Sprint.name == sprint_name)
            )
            sprint = result.scalar_one_or_none()

            start_str = js.get("startDate")
            end_str = js.get("endDate")
            
            # Use UTC now if dates are missing, otherwise parse
            from dateutil.parser import isoparse
            start_date = isoparse(start_str).date() if start_str else datetime.now(timezone.utc).date()
            end_date = isoparse(end_str).date() if end_str else datetime.now(timezone.utc).date()

            if not sprint:
                sprint = Sprint(
                    project_id=project_id,
                    name=sprint_name,
                    status=sp_status,
                    start_date=start_date,
                    end_date=end_date,
                )
                self._session.add(sprint)
                await self._session.flush()
            else:
                # If sprint transitioned to closure during THIS sync, trigger KPI snapshot
                newly_closed = sprint.status != "completed" and sp_status == "completed"
                sprint.status = sp_status
                sprint.start_date = start_date
                sprint.end_date = end_date
                
                if newly_closed:
                    svc = DeveloperKPIService(self._session)
                    await svc.snapshot_sprint_kpis(project_id, sprint.id, datetime.now(timezone.utc))

        await self._session.flush()
