from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging_config import get_logger
from app.models.action_item import ActionEvent, ActionItem
from app.models.blocker import Blocker
from app.models.integration_sync_log import IntegrationSyncLog, SyncStatus
from app.models.integration_task import IntegrationTask
from app.models.repository_activity import RepositoryActivity
from app.models.ticket import Ticket
from app.models.user import User
from app.services.notification_service import Notification, NotificationService, NotificationSeverity

logger = get_logger(__name__)

TERMINAL_STATUSES = {"resolved", "dismissed"}


@dataclass(slots=True)
class ActionDraft:
    project_id: int
    source_type: str
    source_id: str
    title: str
    description: str
    recommended_action: str
    priority: str
    owner_role: str | None
    owner_user_id: int | None = None
    approval_required: bool = False
    due_at: datetime | None = None
    source_url: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


class ActionItemService:
    """Creates and manages Action Center workflow items."""

    def __init__(
        self,
        session: AsyncSession,
        notifications: NotificationService | None = None,
    ) -> None:
        self._session = session
        self._notifications = notifications or NotificationService()

    async def list_actions(
        self,
        *,
        project_id: int,
        status: str | None = None,
        source_type: str | None = None,
        owner_user_id: int | None = None,
        include_resolved: bool = False,
    ) -> list[ActionItem]:
        stmt = select(ActionItem).where(ActionItem.project_id == project_id)
        if status:
            stmt = stmt.where(ActionItem.status == status)
        elif not include_resolved:
            stmt = stmt.where(ActionItem.status.notin_(TERMINAL_STATUSES))
        if source_type:
            stmt = stmt.where(ActionItem.source_type == source_type)
        if owner_user_id is not None:
            stmt = stmt.where(ActionItem.owner_user_id == owner_user_id)
        stmt = stmt.order_by(
            ActionItem.status == "resolved",
            ActionItem.status == "dismissed",
            ActionItem.due_at.is_(None),
            ActionItem.due_at.asc(),
            ActionItem.created_at.desc(),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_action(self, action_id: int) -> ActionItem | None:
        result = await self._session.execute(
            select(ActionItem)
            .options(selectinload(ActionItem.events))
            .where(ActionItem.id == action_id)
        )
        return result.scalar_one_or_none()

    async def generate_for_project(self, project_id: int, actor_user_id: int | None) -> dict[str, Any]:
        drafts: list[ActionDraft] = []
        drafts.extend(await self._draft_blocker_actions(project_id))
        drafts.extend(await self._draft_ticket_quality_actions(project_id))
        drafts.extend(await self._draft_repository_actions(project_id))
        drafts.extend(await self._draft_integration_actions(project_id))

        generated = 0
        refreshed = 0
        action_ids: list[int] = []

        for draft in drafts:
            item, created = await self._upsert_generated_action(draft, actor_user_id)
            action_ids.append(item.id)
            if created:
                generated += 1
            else:
                refreshed += 1

        total_open = len(
            await self.list_actions(project_id=project_id, include_resolved=False)
        )
        logger.info(
            "action_generation_complete",
            project_id=project_id,
            generated=generated,
            refreshed=refreshed,
            total_open=total_open,
        )
        return {
            "project_id": project_id,
            "generated": generated,
            "refreshed": refreshed,
            "total_open": total_open,
            "action_ids": action_ids,
        }

    async def update_action(
        self,
        action: ActionItem,
        *,
        actor_user_id: int | None,
        note: str | None = None,
        **fields: Any,
    ) -> ActionItem:
        previous_status = action.status
        next_status = fields.get("status", previous_status)
        if next_status in TERMINAL_STATUSES:
            fields.setdefault("resolved_at", datetime.now(UTC))
        elif "status" in fields:
            fields.setdefault("resolved_at", None)

        for key, value in fields.items():
            if value is not None or key in {"owner_user_id", "owner_role", "due_at", "resolved_at"}:
                setattr(action, key, value)
        self._session.add(action)
        await self._session.flush()

        event_type = "status_changed" if previous_status != action.status else "updated"
        await self._record_event(
            action,
            actor_user_id=actor_user_id,
            event_type=event_type,
            previous_status=previous_status,
            next_status=action.status,
            note=note,
            payload={"fields": sorted(fields.keys())},
        )
        await self._session.refresh(action)
        return action

    async def transition(
        self,
        action: ActionItem,
        *,
        actor_user_id: int | None,
        next_status: str,
        event_type: str,
        note: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ActionItem:
        previous_status = action.status
        action.status = next_status
        if next_status in TERMINAL_STATUSES:
            action.resolved_at = datetime.now(UTC)
        elif previous_status in TERMINAL_STATUSES:
            action.resolved_at = None
        self._session.add(action)
        await self._session.flush()
        await self._record_event(
            action,
            actor_user_id=actor_user_id,
            event_type=event_type,
            previous_status=previous_status,
            next_status=next_status,
            note=note,
            payload=payload or {},
        )
        await self._session.refresh(action)
        return action

    async def dispatch(
        self,
        action: ActionItem,
        *,
        actor_user_id: int | None,
        note: str | None = None,
    ) -> ActionItem:
        if action.approval_required and action.status not in {"approved", "in_progress"}:
            return await self.transition(
                action,
                actor_user_id=actor_user_id,
                next_status="awaiting_approval",
                event_type="approval_requested",
                note=note or "Approval is required before dispatch.",
            )

        recipient_emails: list[str] | None = None
        if action.owner_user_id is not None:
            owner = await self._session.get(User, action.owner_user_id)
            if owner and owner.email:
                recipient_emails = [owner.email]

        results = await self._notifications.send(
            Notification(
                title=f"Action required: {action.title}",
                body=f"{action.recommended_action}\n\n{action.description or ''}".strip(),
                severity=NotificationSeverity.CRITICAL if action.priority == "critical" else NotificationSeverity.WARNING,
                recipient_emails=recipient_emails,
                metadata={"action_id": action.id, "project_id": action.project_id},
            )
        )
        return await self.transition(
            action,
            actor_user_id=actor_user_id,
            next_status="in_progress",
            event_type="dispatched",
            note=note,
            payload={"notification_results": results},
        )

    async def _upsert_generated_action(
        self,
        draft: ActionDraft,
        actor_user_id: int | None,
    ) -> tuple[ActionItem, bool]:
        existing = await self._session.scalar(
            select(ActionItem).where(
                and_(
                    ActionItem.project_id == draft.project_id,
                    ActionItem.source_type == draft.source_type,
                    ActionItem.source_id == draft.source_id,
                    ActionItem.recommended_action == draft.recommended_action,
                )
            )
        )
        if existing is None:
            item = ActionItem(
                project_id=draft.project_id,
                source_type=draft.source_type,
                source_id=draft.source_id,
                source_url=draft.source_url,
                title=draft.title,
                description=draft.description,
                recommended_action=draft.recommended_action,
                priority=draft.priority,
                owner_user_id=draft.owner_user_id,
                owner_role=draft.owner_role,
                status="open",
                approval_required=draft.approval_required,
                due_at=draft.due_at,
                metadata_json=draft.metadata_json,
            )
            self._session.add(item)
            await self._session.flush()
            await self._record_event(
                item,
                actor_user_id=actor_user_id,
                event_type="generated",
                previous_status=None,
                next_status=item.status,
                payload={"rule": draft.metadata_json.get("rule")},
            )
            await self._session.refresh(item)
            return item, True

        previous_status = existing.status
        existing.title = draft.title
        existing.description = draft.description
        existing.priority = draft.priority
        existing.owner_user_id = draft.owner_user_id
        existing.owner_role = draft.owner_role
        existing.approval_required = draft.approval_required
        existing.due_at = draft.due_at
        existing.source_url = draft.source_url
        existing.metadata_json = {**(existing.metadata_json or {}), **draft.metadata_json}
        if existing.status in TERMINAL_STATUSES:
            existing.status = "open"
            existing.resolved_at = None
        self._session.add(existing)
        await self._session.flush()
        if previous_status in TERMINAL_STATUSES:
            await self._record_event(
                existing,
                actor_user_id=actor_user_id,
                event_type="regenerated",
                previous_status=previous_status,
                next_status=existing.status,
                payload={"rule": draft.metadata_json.get("rule")},
            )
        await self._session.refresh(existing)
        return existing, False

    async def _record_event(
        self,
        action: ActionItem,
        *,
        actor_user_id: int | None,
        event_type: str,
        previous_status: str | None,
        next_status: str | None,
        note: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ActionEvent:
        event = ActionEvent(
            action_item_id=action.id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            previous_status=previous_status,
            next_status=next_status,
            note=note,
            payload_json=payload or {},
            created_at=datetime.now(UTC),
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def _draft_blocker_actions(self, project_id: int) -> list[ActionDraft]:
        result = await self._session.execute(
            select(Blocker)
            .options(selectinload(Blocker.ticket))
            .join(Ticket, Ticket.id == Blocker.ticket_id)
            .where(Ticket.project_id == project_id, Blocker.resolved_at.is_(None))
        )
        drafts: list[ActionDraft] = []
        now = datetime.now(UTC)
        for blocker in result.scalars().all():
            ticket = blocker.ticket
            if ticket is None:
                continue
            owner_user_id = await self._user_id_for_developer(ticket.assignee_id)
            level = blocker.escalation_level
            if level >= 3:
                priority = "critical"
                action = "Create management escalation and request a recovery plan."
                owner_role = "delivery_lead"
                due_at = now + timedelta(hours=1)
                approval_required = True
            elif level == 2:
                priority = "high"
                action = "Notify the delivery lead and request a concrete unblock plan."
                owner_role = "delivery_lead"
                due_at = now + timedelta(hours=4)
                approval_required = False
            else:
                priority = "medium"
                action = "Ask the assigned developer for a status update."
                owner_role = "developer"
                due_at = now + timedelta(hours=4)
                approval_required = False
            drafts.append(
                ActionDraft(
                    project_id=project_id,
                    source_type="blocker",
                    source_id=str(blocker.id),
                    source_url=f"/blockers?blocker={blocker.id}",
                    title=f"Unblock {ticket.title}",
                    description=blocker.description
                    or f"Ticket #{ticket.id} has been stalled for {blocker.stall_hours:.1f} hours.",
                    recommended_action=action,
                    priority=priority,
                    owner_user_id=owner_user_id,
                    owner_role=owner_role,
                    approval_required=approval_required,
                    due_at=due_at,
                    metadata_json={
                        "rule": f"blocker_l{min(max(level, 1), 3)}",
                        "ticket_id": ticket.id,
                        "stall_hours": blocker.stall_hours,
                        "escalation_level": level,
                    },
                )
            )
        return drafts

    async def _draft_ticket_quality_actions(self, project_id: int) -> list[ActionDraft]:
        result = await self._session.execute(
            select(Ticket)
            .where(
                Ticket.project_id == project_id,
                Ticket.quality_score.is_not(None),
                Ticket.quality_score < 60,
                Ticket.status.notin_(["done", "cancelled"]),
            )
            .order_by(Ticket.quality_score.asc())
            .limit(25)
        )
        drafts: list[ActionDraft] = []
        now = datetime.now(UTC)
        for ticket in result.scalars().all():
            owner_user_id = await self._user_id_for_developer(ticket.assignee_id)
            drafts.append(
                ActionDraft(
                    project_id=project_id,
                    source_type="ticket_quality",
                    source_id=str(ticket.id),
                    source_url=f"/tickets?ticket={ticket.id}",
                    title=f"Improve ticket quality: {ticket.title}",
                    description=(
                        f"Ticket quality is {ticket.quality_score:.0f}%. "
                        "Review description, estimate, priority, assignee, and acceptance criteria."
                    ),
                    recommended_action="Update the ticket before relying on it for sprint planning.",
                    priority="medium",
                    owner_user_id=owner_user_id,
                    owner_role="client_pm" if owner_user_id is None else "developer",
                    due_at=now + timedelta(days=1),
                    metadata_json={
                        "rule": "ticket_quality_below_60",
                        "ticket_id": ticket.id,
                        "quality_score": ticket.quality_score,
                    },
                )
            )
        return drafts

    async def _draft_repository_actions(self, project_id: int) -> list[ActionDraft]:
        result = await self._session.execute(
            select(RepositoryActivity)
            .options(selectinload(RepositoryActivity.ticket))
            .where(
                RepositoryActivity.project_id == project_id,
                RepositoryActivity.mismatch_detected.is_(True),
            )
            .order_by(desc(RepositoryActivity.scanned_at))
            .limit(25)
        )
        drafts: list[ActionDraft] = []
        now = datetime.now(UTC)
        for activity in result.scalars().all():
            ticket = activity.ticket
            owner_user_id = await self._user_id_for_developer(ticket.assignee_id if ticket else None)
            mismatch_type = activity.mismatch_type or "repository_mismatch"
            recommended = _repo_recommendation(mismatch_type)
            priority = "high" if mismatch_type == "pr_not_merged_done" else "medium"
            drafts.append(
                ActionDraft(
                    project_id=project_id,
                    source_type="repository_mismatch",
                    source_id=str(activity.id),
                    source_url=f"/repository?ticket={activity.ticket_id}",
                    title=f"Reconcile repository activity for ticket #{activity.ticket_id}",
                    description=activity.mismatch_reason or "Repository activity does not match ticket state.",
                    recommended_action=recommended,
                    priority=priority,
                    owner_user_id=owner_user_id,
                    owner_role="developer",
                    due_at=now + timedelta(hours=8),
                    metadata_json={
                        "rule": mismatch_type,
                        "ticket_id": activity.ticket_id,
                        "branch_name": activity.branch_name,
                        "commit_count": activity.commit_count,
                        "pr_count": activity.pr_count,
                    },
                )
            )
        return drafts

    async def _draft_integration_actions(self, project_id: int) -> list[ActionDraft]:
        result = await self._session.execute(
            select(IntegrationSyncLog)
            .join(IntegrationTask, IntegrationTask.account_id == IntegrationSyncLog.account_id)
            .where(
                IntegrationTask.project_id == project_id,
                IntegrationSyncLog.status.in_([SyncStatus.FAILED.value, SyncStatus.PARTIAL.value]),
            )
            .order_by(desc(IntegrationSyncLog.started_at))
            .limit(10)
        )
        drafts: list[ActionDraft] = []
        now = datetime.now(UTC)
        seen: set[int] = set()
        for log in result.scalars().all():
            if log.id in seen:
                continue
            seen.add(log.id)
            drafts.append(
                ActionDraft(
                    project_id=project_id,
                    source_type="integration_health",
                    source_id=str(log.id),
                    source_url="/integrations",
                    title=f"Repair {log.provider} sync health",
                    description=log.error_detail or f"Latest {log.provider} sync ended with status {log.status}.",
                    recommended_action="Reconnect the provider account or retry the sync after fixing credentials.",
                    priority="high" if log.status == SyncStatus.FAILED.value else "medium",
                    owner_role="admin",
                    due_at=now + timedelta(hours=2),
                    metadata_json={
                        "rule": "integration_sync_failed",
                        "provider": log.provider,
                        "account_id": log.account_id,
                        "sync_log_id": log.id,
                    },
                )
            )
        return drafts

    async def _user_id_for_developer(self, developer_id: int | None) -> int | None:
        if developer_id is None:
            return None
        return await self._session.scalar(select(User.id).where(User.developer_id == developer_id))


def _repo_recommendation(mismatch_type: str) -> str:
    if mismatch_type == "no_commits_in_progress":
        return "Ask the assignee to link a branch/PR or update the ticket state."
    if mismatch_type == "pr_not_merged_done":
        return "Reconcile the done status before using this ticket in client reporting."
    if mismatch_type == "stale_branch":
        return "Ask for a code progress update or split/escalate the stalled work."
    if mismatch_type == "no_pr_in_review":
        return "Create or link the pull request before keeping the ticket in review."
    return "Review repository evidence and align it with the ticket state."

