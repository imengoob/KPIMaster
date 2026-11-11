"""
Developer KPI Service — Trello data edition
============================================

All KPIs are computed directly from synced Trello data:

  TrelloCard            — cards with cycle_time_hours, entered_wip_at,
                          entered_done_at, is_stalled, stalled_since,
                          member_ids (JSON list of Trello member ID strings),
                          labels (JSON list of {id, name, color})

  TrelloList            — list_type: backlog | wip | done | unknown

  TrelloAction          — commentCard actions for QRT / UQR computation
                          trello_member_id + member_name identify the author

  TrelloCardMovement    — not needed; cycle_time_hours is already on the card

KPIs computed:
  • Completion Rate     — done-list cards / total cards
  • Avg Cycle Time      — card.cycle_time_hours (wip→done); falls back to
                          entered_done_at − entered_wip_at
  • Blocker Rate        — stalled cards / total cards
  • Avg Blocker Age     — mean hours since stalled_since for stalled cards
  • Stalled Count       — WIP cards with is_stalled=True
  • Task-Type Profile   — per label-derived type: count, done, avg cycle time
  • QRT                 — avg hours from a member's "?" comment to first reply
  • UQR                 — % of such questions with no reply within 8h

Estimation accuracy is not available from Trello (no actual-vs-estimate data).

Developer identity:
  Trello stores members as opaque string IDs on each card (member_ids JSON).
  We derive a deterministic integer ID via SHA-1(trello_member_id)[:8] so the
  frontend can use stable numeric IDs without a separate developer table.
"""
from __future__ import annotations

import hashlib
import re
import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.logging_config import get_logger
from app.models.company import Company
from app.models.developer import Developer
from app.models.developer_external_identity import DeveloperExternalIdentity
from app.models.engagement import DeveloperAssignment, Engagement
from app.models.integration_task import IntegrationComment, IntegrationTask
from app.models.trello_action import TrelloAction
from app.models.trello_board import TrelloBoard
from app.models.trello_card import TrelloCard
from app.models.developer_sprint_kpi import DeveloperSprintKPI
from app.models.trello_credential import TrelloCredential
from app.models.trello_list import ListType, TrelloList
from app.schemas.developer import (
    ClientProgressMember,
    ClientProgressReport,
    ClientProgressSummary,
    DeveloperTicketResponseMetric,
    DeveloperKPIReport,
    TaskTypeProfile,
    TeamKPIReport,
    TeamMemberSummary,
    TeamWarningSignal,
)

logger = get_logger(__name__)

_STALL_IDLE_HOURS = 16
_QRT_THRESHOLD_HOURS = 8
_QUESTION_RE = re.compile(r"\?")
_POINTS_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:sp|pts?|points?)\b", re.IGNORECASE)


# ── Helpers shared with live_project_service ──────────────────────────────────

def _member_numeric_id(member_id: str | None) -> int | None:
    if not member_id:
        return None
    return int(hashlib.sha1(member_id.encode()).hexdigest()[:8], 16)


def _label_text(labels: list | None) -> str:
    return " ".join(
        (lbl.get("name") or "") for lbl in (labels or []) if isinstance(lbl, dict)
    ).lower()


def _ticket_type(labels: list | None) -> str:
    txt = _label_text(labels)
    if "bug" in txt:
        return "bug"
    if "feature" in txt or "story" in txt:
        return "feature"
    if "refactor" in txt:
        return "refactor"
    if "spike" in txt or "investig" in txt or "research" in txt:
        return "investigation"
    return "task"


def _story_points(labels: list | None) -> int:
    for lbl in labels or []:
        if not isinstance(lbl, dict):
            continue
        m = _POINTS_RE.search(lbl.get("name") or "")
        if m:
            return int(m.group(1))
    return 1


def _tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _parse_range_bound(value: str | None) -> datetime | None:
    if not value:
        return None
    from dateutil.parser import parse as parse_date

    parsed = parse_date(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# ── Trello member record ───────────────────────────────────────────────────────

class _Member:
    __slots__ = ("trello_id", "name", "username", "numeric_id")

    def __init__(self, trello_id: str, name: str, username: str) -> None:
        self.trello_id = trello_id
        self.name = name
        self.username = username
        self.numeric_id: int = _member_numeric_id(trello_id)  # type: ignore[assignment]


# ── Main service ───────────────────────────────────────────────────────────────

class DeveloperKPIService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    # ── Public API ──────────────────────────────────────────────────────────────

    async def compute_team_kpis(
        self,
        project_id: int,
        sprint_id: int | None = None,   # kept for API compat; Trello boards have no sprint scope
        start_date: str | None = None,
        end_date: str | None = None,
        provider: str | None = None,
    ) -> TeamKPIReport:
        now = datetime.now(UTC)
        integration_report = await self._compute_integration_team_report(
            project_id,
            sprint_id,
            now,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
        )
        if integration_report is not None:
            return integration_report

        if provider is not None and provider != "trello":
            return self._empty_team_report(project_id, sprint_id, now)

        board = await self._get_board(project_id)
        if board is None:
            return self._empty_team_report(project_id, sprint_id, now)

        cards_with_lists = await self._load_cards(board.id, start_date=start_date, end_date=end_date)
        comment_actions = await self._load_comment_actions(board.id, start_date=start_date, end_date=end_date)
        name_map = await self._build_name_map(board, project_id)
        members = self._extract_members(cards_with_lists, comment_actions, name_map)

        team_members: list[TeamMemberSummary] = []
        warnings: list[TeamWarningSignal] = []
        cycle_times: list[float] = []
        completion_rates: list[float] = []
        blocker_rates: list[float] = []
        qrts: list[float] = []
        uqrs: list[float] = []

        for member in members:
            my_cards = self._cards_for_member(member.trello_id, cards_with_lists)
            my_comments = [a for a in comment_actions if a.trello_member_id == member.trello_id]
            report = self._build_report(member, project_id, sprint_id, my_cards, comment_actions, now)

            team_members.append(TeamMemberSummary(
                developer_id=member.numeric_id,
                developer_name=member.name,
                role="member",
                story_points_completed=report.story_points_completed,
                story_points_total=report.story_points_total,
                completion_rate=report.completion_rate,
                avg_cycle_time_hours=report.avg_cycle_time_hours,
                blocker_rate=report.blocker_rate,
                active_blockers=report.active_blockers,
                question_response_time_hours=report.question_response_time_hours,
                unanswered_question_rate=report.unanswered_question_rate,
                status=report.status,
                warning_count=len(report.warning_signals),
            ))

            if report.avg_cycle_time_hours is not None:
                cycle_times.append(report.avg_cycle_time_hours)
            completion_rates.append(report.completion_rate)
            blocker_rates.append(report.blocker_rate)
            if report.question_response_time_hours is not None:
                qrts.append(report.question_response_time_hours)
            if report.unanswered_question_rate is not None:
                uqrs.append(report.unanswered_question_rate)

            for sig in report.warning_signals:
                s = sig.lower()
                if "blocker" in s:
                    stype, sev = "blocker_aging", "critical"
                elif "stalled" in s:
                    stype, sev = "silent_stall", "warning"
                elif "unanswered" in s:
                    stype, sev = "high_uqr", "warning"
                else:
                    stype, sev = "process_review", "info"
                warnings.append(TeamWarningSignal(
                    developer_id=member.numeric_id,
                    developer_name=member.name,
                    signal_type=stype,
                    description=sig,
                    severity=sev,
                ))

        return TeamKPIReport(
            project_id=project_id,
            sprint_id=sprint_id,
            members=team_members,
            team_avg_cycle_time_hours=(
                round(statistics.mean(cycle_times), 2) if cycle_times else None
            ),
            team_completion_rate=(
                round(statistics.mean(completion_rates), 4) if completion_rates else 0.0
            ),
            team_blocker_rate=(
                round(statistics.mean(blocker_rates), 4) if blocker_rates else 0.0
            ),
            team_question_response_time_hours=(
                round(statistics.mean(qrts), 2) if qrts else None
            ),
            team_unanswered_question_rate=(
                round(statistics.mean(uqrs), 4) if uqrs else None
            ),
            warning_signals=warnings,
            computed_at=now.isoformat(),
        )

    async def compute_developer_kpis(
        self,
        developer_id: int,
        project_id: int,
        sprint_id: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: str | None = None,
    ) -> DeveloperKPIReport:
        now = datetime.now(UTC)
        integration_report = await self._compute_integration_developer_report(
            developer_id,
            project_id,
            sprint_id,
            now,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
        )
        if integration_report is not None:
            return integration_report

        if provider is not None and provider != "trello":
            raise ValueError(f"No KPI data found for provider '{provider}' on project {project_id}")

        board = await self._get_board(project_id)
        if board is None:
            raise ValueError(f"No Trello board found for project {project_id}")

        cards_with_lists = await self._load_cards(board.id, start_date=start_date, end_date=end_date)
        comment_actions = await self._load_comment_actions(board.id, start_date=start_date, end_date=end_date)
        name_map = await self._build_name_map(board, project_id)
        members = self._extract_members(cards_with_lists, comment_actions, name_map)
        lookup_id = developer_id
        internal_developer = None
        if developer_id <= 2147483647:
            internal_developer = await self._db.get(Developer, developer_id)
        if internal_developer and internal_developer.trello_member_id:
            lookup_id = _member_numeric_id(internal_developer.trello_member_id) or developer_id

        # Reverse-lookup: find member whose SHA-1 hash matches developer_id
        member = next((m for m in members if m.numeric_id == lookup_id), None)
        if member is None:
            raise ValueError(f"Developer {developer_id} not found on project {project_id}")

        my_cards = self._cards_for_member(member.trello_id, cards_with_lists)
        return self._build_report(member, project_id, sprint_id, my_cards, comment_actions, now)

    async def compute_client_progress(
        self,
        project_id: int,
        sprint_id: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: str | None = None,
    ) -> ClientProgressReport:
        now = datetime.now(UTC)
        integration_report = await self._compute_integration_client_progress(
            project_id,
            sprint_id,
            now,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
        )
        if integration_report is not None:
            return integration_report

        if provider is not None and provider != "trello":
            return self._empty_client_report(project_id, sprint_id, now)

        board = await self._get_board(project_id)
        if board is None:
            return self._empty_client_report(project_id, sprint_id, now)

        cards_with_lists = await self._load_cards(board.id, start_date=start_date, end_date=end_date)
        comment_actions = await self._load_comment_actions(board.id, start_date=start_date, end_date=end_date)
        name_map = await self._build_name_map(board, project_id)
        members = self._extract_members(cards_with_lists, comment_actions, name_map)

        client_members: list[ClientProgressMember] = []
        status_rank = {"behind": 0, "at-risk": 1, "on-track": 2}

        for member in members:
            my_cards = self._cards_for_member(member.trello_id, cards_with_lists)
            if not my_cards:
                continue

            report = self._build_report(
                member, project_id, sprint_id, my_cards, comment_actions, now
            )
            latest_activity_at = self._latest_activity_at(my_cards)
            freshness = self._activity_freshness(latest_activity_at, now)

            client_members.append(
                ClientProgressMember(
                    developer_id=member.numeric_id,
                    developer_name=member.name,
                    role=report.developer_role,
                    status=report.status,
                    tickets_completed=report.tickets_done,
                    tickets_total=report.tickets_total,
                    story_points_completed=report.story_points_completed,
                    story_points_total=report.story_points_total,
                    active_work_items=report.tickets_in_progress,
                    active_blockers=report.active_blockers,
                    avg_cycle_time_hours=report.avg_cycle_time_hours,
                    latest_activity_at=(
                        latest_activity_at.isoformat() if latest_activity_at else None
                    ),
                    activity_freshness=freshness,
                    risk_note=self._client_risk_note(report, freshness),
                )
            )

        client_members.sort(
            key=lambda item: (status_rank.get(item.status, 99), item.developer_name.lower())
        )

        return ClientProgressReport(
            project_id=project_id,
            sprint_id=sprint_id,
            summary=self._build_client_summary(cards_with_lists, client_members, now),
            members=client_members,
            computed_at=now.isoformat(),
        )

    # ── Normalized multi-provider KPI path ─────────────────────────────────────

    async def _compute_integration_team_report(
        self,
        project_id: int,
        sprint_id: int | None,
        now: datetime,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: str | None = None,
    ) -> TeamKPIReport | None:
        tasks = await self._load_integration_tasks(project_id, sprint_id, start_date, end_date, provider)
        if not tasks:
            return None

        comments = await self._load_integration_comments([task.id for task in tasks])
        comments_by_task = self._comments_by_task(comments)
        task_map, dev_external_ids, developers = await self._group_integration_tasks_by_developer(tasks)
        engagement_context = await self._load_engagement_context(project_id)

        members: list[TeamMemberSummary] = []
        warnings: list[TeamWarningSignal] = []
        cycle_times: list[float] = []
        completion_rates: list[float] = []
        blocker_rates: list[float] = []
        response_times: list[float] = []
        unanswered_rates: list[float] = []

        for developer_id, dev_tasks in sorted(
            task_map.items(),
            key=lambda item: developers[item[0]].name.lower(),
        ):
            developer = developers[developer_id]
            report = self._build_integration_report(
                developer=developer,
                project_id=project_id,
                sprint_id=sprint_id,
                tasks=dev_tasks,
                comments_by_task=comments_by_task,
                developer_external_ids=dev_external_ids.get(developer_id, set()),
                engagement_context=engagement_context.get(developer_id, {}),
                now=now,
            )
            members.append(TeamMemberSummary(
                developer_id=developer.id,
                developer_name=developer.name,
                role=developer.role,
                provider_sources=report.provider_sources,
                engagement_name=report.engagement_name,
                client_name=report.client_name,
                story_points_completed=report.story_points_completed,
                story_points_total=report.story_points_total,
                completion_rate=report.completion_rate,
                avg_cycle_time_hours=report.avg_cycle_time_hours,
                blocker_rate=report.blocker_rate,
                active_blockers=report.active_blockers,
                question_response_time_hours=report.question_response_time_hours,
                unanswered_question_rate=report.unanswered_question_rate,
                ert_target_hours=report.ert_target_hours,
                ert_status=report.ert_status,
                status=report.status,
                warning_count=len(report.warning_signals),
            ))

            if report.avg_cycle_time_hours is not None:
                cycle_times.append(report.avg_cycle_time_hours)
            completion_rates.append(report.completion_rate)
            blocker_rates.append(report.blocker_rate)
            if report.question_response_time_hours is not None:
                response_times.append(report.question_response_time_hours)
            if report.unanswered_question_rate is not None:
                unanswered_rates.append(report.unanswered_question_rate)

            for signal in report.warning_signals:
                lower = signal.lower()
                if "block" in lower:
                    stype, severity = "blocker_aging", "critical"
                elif "response" in lower or "ert" in lower:
                    stype, severity = "response_sla", "warning"
                elif "unanswered" in lower:
                    stype, severity = "high_uqr", "warning"
                else:
                    stype, severity = "process_review", "info"
                warnings.append(TeamWarningSignal(
                    developer_id=developer.id,
                    developer_name=developer.name,
                    signal_type=stype,
                    description=signal,
                    severity=severity,
                ))

        return TeamKPIReport(
            project_id=project_id,
            sprint_id=sprint_id,
            members=members,
            team_avg_cycle_time_hours=round(statistics.mean(cycle_times), 2) if cycle_times else None,
            team_completion_rate=round(statistics.mean(completion_rates), 4) if completion_rates else 0.0,
            team_blocker_rate=round(statistics.mean(blocker_rates), 4) if blocker_rates else 0.0,
            team_question_response_time_hours=(
                round(statistics.mean(response_times), 2) if response_times else None
            ),
            team_unanswered_question_rate=(
                round(statistics.mean(unanswered_rates), 4) if unanswered_rates else None
            ),
            warning_signals=warnings,
            computed_at=now.isoformat(),
        )

    async def _compute_integration_developer_report(
        self,
        developer_id: int,
        project_id: int,
        sprint_id: int | None,
        now: datetime,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: str | None = None,
    ) -> DeveloperKPIReport | None:
        tasks = await self._load_integration_tasks(project_id, sprint_id, start_date, end_date, provider)
        if not tasks:
            return None

        comments = await self._load_integration_comments([task.id for task in tasks])
        task_map, dev_external_ids, developers = await self._group_integration_tasks_by_developer(tasks)
        if developer_id not in task_map or developer_id not in developers:
            return None
        engagement_context = await self._load_engagement_context(project_id)
        return self._build_integration_report(
            developer=developers[developer_id],
            project_id=project_id,
            sprint_id=sprint_id,
            tasks=task_map[developer_id],
            comments_by_task=self._comments_by_task(comments),
            developer_external_ids=dev_external_ids.get(developer_id, set()),
            engagement_context=engagement_context.get(developer_id, {}),
            now=now,
        )

    async def _compute_integration_client_progress(
        self,
        project_id: int,
        sprint_id: int | None,
        now: datetime,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: str | None = None,
    ) -> ClientProgressReport | None:
        team = await self._compute_integration_team_report(
            project_id,
            sprint_id,
            now,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
        )
        if team is None:
            return None

        members: list[ClientProgressMember] = []
        status_rank = {"behind": 0, "at-risk": 1, "on-track": 2}
        for row in team.members:
            detail = await self._compute_integration_developer_report(
                row.developer_id,
                project_id,
                sprint_id,
                now,
                start_date=start_date,
                end_date=end_date,
                provider=provider,
            )
            if detail is None:
                continue
            latest_activity_at = self._latest_integration_activity(detail.ticket_response_metrics, now)
            members.append(ClientProgressMember(
                developer_id=row.developer_id,
                developer_name=row.developer_name,
                role=row.role,
                provider_sources=row.provider_sources,
                engagement_name=row.engagement_name,
                client_name=row.client_name,
                status=row.status,
                tickets_completed=detail.tickets_done,
                tickets_total=detail.tickets_total,
                story_points_completed=detail.story_points_completed,
                story_points_total=detail.story_points_total,
                active_work_items=detail.tickets_in_progress,
                active_blockers=detail.active_blockers,
                avg_cycle_time_hours=detail.avg_cycle_time_hours,
                question_response_time_hours=detail.question_response_time_hours,
                ert_target_hours=detail.ert_target_hours,
                ert_status=detail.ert_status,
                latest_activity_at=latest_activity_at.isoformat() if latest_activity_at else None,
                activity_freshness=self._activity_freshness(latest_activity_at, now),
                risk_note=self._client_risk_note(detail, self._activity_freshness(latest_activity_at, now)),
            ))

        members.sort(key=lambda item: (status_rank.get(item.status, 99), item.developer_name.lower()))
        total_tickets = sum(member.tickets_total for member in members)
        completed_tickets = sum(member.tickets_completed for member in members)
        cycle_times = [member.avg_cycle_time_hours for member in members if member.avg_cycle_time_hours is not None]

        return ClientProgressReport(
            project_id=project_id,
            sprint_id=sprint_id,
            summary=ClientProgressSummary(
                total_developers=len(members),
                on_track_count=sum(1 for member in members if member.status == "on-track"),
                at_risk_count=sum(1 for member in members if member.status == "at-risk"),
                behind_count=sum(1 for member in members if member.status == "behind"),
                overall_completion_rate=round(completed_tickets / total_tickets, 4) if total_tickets else 0.0,
                story_points_completed=sum(member.story_points_completed for member in members),
                story_points_total=sum(member.story_points_total for member in members),
                active_blockers=sum(member.active_blockers for member in members),
                avg_cycle_time_hours=round(statistics.mean(cycle_times), 2) if cycle_times else None,
                last_updated_at=now.isoformat(),
            ),
            members=members,
            computed_at=now.isoformat(),
        )

    async def _load_integration_tasks(
        self,
        project_id: int,
        sprint_id: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: str | None = None,
    ) -> list[IntegrationTask]:
        from datetime import datetime, timezone
        stmt = select(IntegrationTask).where(
            IntegrationTask.project_id == project_id,
            IntegrationTask.is_active.is_(True),
        )
        if sprint_id:
            stmt = stmt.where(IntegrationTask.sprint_id == sprint_id)
        if provider is not None:
            stmt = stmt.where(IntegrationTask.provider == provider)
        if start_date:
            try:
                sd = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                stmt = stmt.where(IntegrationTask.external_created_at >= sd)
            except Exception:
                pass
        if end_date:
            try:
                ed = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                stmt = stmt.where(IntegrationTask.external_updated_at <= ed)
            except Exception:
                pass
        stmt = stmt.order_by(IntegrationTask.provider, IntegrationTask.title)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def _load_integration_comments(self, task_ids: list[int]) -> list[IntegrationComment]:
        if not task_ids:
            return []
        result = await self._db.execute(
            select(IntegrationComment)
            .where(IntegrationComment.task_id.in_(task_ids))
            .order_by(IntegrationComment.external_created_at)
        )
        return list(result.scalars().all())

    async def _group_integration_tasks_by_developer(
        self,
        tasks: list[IntegrationTask],
    ) -> tuple[dict[int, list[IntegrationTask]], dict[int, set[str]], dict[int, Developer]]:
        providers = {task.provider for task in tasks}
        account_ids = {task.account_id for task in tasks}
        assignees_by_provider: dict[str, set[str]] = defaultdict(set)
        for task in tasks:
            for assignee_id in task.assignee_ids or []:
                if assignee_id:
                    assignees_by_provider[task.provider].add(str(assignee_id))

        identity_rows = await self._db.execute(
            select(DeveloperExternalIdentity, Developer)
            .join(Developer, Developer.id == DeveloperExternalIdentity.developer_id)
            .where(
                DeveloperExternalIdentity.is_active.is_(True),
                DeveloperExternalIdentity.provider.in_(providers),
                or_(
                    DeveloperExternalIdentity.integration_account_id.in_(account_ids),
                    DeveloperExternalIdentity.integration_account_id.is_(None),
                ),
            )
        )

        identity_map: dict[tuple[str, int | None, str], Developer] = {}
        developer_external_ids: dict[int, set[str]] = defaultdict(set)
        developers: dict[int, Developer] = {}
        for identity, developer in identity_rows.all():
            identity_map[(identity.provider, identity.integration_account_id, identity.external_user_id)] = developer
            identity_map[(identity.provider, None, identity.external_user_id)] = developer
            developer_external_ids[developer.id].add(identity.external_user_id)
            developers[developer.id] = developer

        trello_ids = assignees_by_provider.get("trello", set())
        if trello_ids:
            trello_result = await self._db.execute(
                select(Developer).where(Developer.trello_member_id.in_(trello_ids))
            )
            for developer in trello_result.scalars().all():
                if developer.trello_member_id:
                    identity_map[("trello", None, developer.trello_member_id)] = developer
                    developer_external_ids[developer.id].add(developer.trello_member_id)
                    developers[developer.id] = developer

        github_logins = assignees_by_provider.get("github", set())
        if github_logins:
            github_result = await self._db.execute(
                select(Developer).where(Developer.github_username.in_(github_logins))
            )
            for developer in github_result.scalars().all():
                if developer.github_username:
                    identity_map[("github", None, developer.github_username)] = developer
                    developer_external_ids[developer.id].add(developer.github_username)
                    developers[developer.id] = developer

        grouped: dict[int, list[IntegrationTask]] = defaultdict(list)
        seen_pairs: set[tuple[int, int]] = set()
        for task in tasks:
            for assignee_id in task.assignee_ids or []:
                assignee = str(assignee_id)
                developer = (
                    identity_map.get((task.provider, task.account_id, assignee))
                    or identity_map.get((task.provider, None, assignee))
                )
                if developer is None:
                    continue
                pair = (developer.id, task.id)
                if pair in seen_pairs:
                    continue
                grouped[developer.id].append(task)
                developer_external_ids[developer.id].add(assignee)
                developers[developer.id] = developer
                seen_pairs.add(pair)

        return dict(grouped), dict(developer_external_ids), developers

    async def _load_engagement_context(self, project_id: int) -> dict[int, dict]:
        client_company = aliased(Company)
        result = await self._db.execute(
            select(
                DeveloperAssignment.developer_id,
                Engagement.name,
                Engagement.sla_response_hours,
                client_company.name,
            )
            .join(Engagement, Engagement.id == DeveloperAssignment.engagement_id)
            .join(client_company, client_company.id == Engagement.client_company_id)
            .where(
                Engagement.project_id == project_id,
                Engagement.status == "active",
                DeveloperAssignment.status == "active",
            )
            .order_by(DeveloperAssignment.is_primary.desc(), Engagement.id.asc())
        )
        context: dict[int, dict] = {}
        for developer_id, engagement_name, sla_response_hours, client_name in result.all():
            context.setdefault(developer_id, {
                "engagement_name": engagement_name,
                "client_name": client_name,
                "sla_response_hours": float(sla_response_hours) if sla_response_hours else None,
            })
        return context

    def _build_integration_report(
        self,
        *,
        developer: Developer,
        project_id: int,
        sprint_id: int | None,
        tasks: list[IntegrationTask],
        comments_by_task: dict[int, list[IntegrationComment]],
        developer_external_ids: set[str],
        engagement_context: dict,
        now: datetime,
    ) -> DeveloperKPIReport:
        done_tasks = [task for task in tasks if task.status == "done"]
        wip_tasks = [task for task in tasks if task.status in {"in_progress", "in_review"}]
        blocked_tasks = [task for task in tasks if self._is_integration_blocked(task)]
        total = len(tasks)
        story_total = sum(self._integration_story_points(task) for task in tasks)
        story_done = sum(self._integration_story_points(task) for task in done_tasks)
        cycle_times = [value for value in (self._integration_cycle_time(task) for task in done_tasks) if value is not None]
        blocker_ages = [value for value in (self._integration_blocker_age(task, now) for task in blocked_tasks) if value is not None]
        ert_target = engagement_context.get("sla_response_hours")
        response = self._integration_response_metrics(
            tasks=tasks,
            comments_by_task=comments_by_task,
            developer_external_ids=developer_external_ids,
            ert_target_hours=ert_target,
            now=now,
        )

        completion_rate = len(done_tasks) / total if total else 0.0
        blocker_rate = len(blocked_tasks) / total if total else 0.0
        avg_response = response["average_response_time_hours"]
        unanswered_rate = (
            response["unanswered_count"] / response["teammate_comment_count"]
            if response["teammate_comment_count"] else None
        )
        ert_status = self._ert_status(avg_response, ert_target, response["tickets_exceeded_ert"])
        status, warning_signals = self._determine_status(
            completion_rate=completion_rate,
            active_blockers=len(blocked_tasks),
            stalled=len(blocked_tasks),
            uqr=unanswered_rate,
            blocker_rate=blocker_rate,
        )
        if ert_status == "exceeded":
            warning_signals.append("Comment response time exceeded ERT target")

        return DeveloperKPIReport(
            developer_id=developer.id,
            developer_name=developer.name,
            developer_role=developer.role,
            project_id=project_id,
            sprint_id=sprint_id,
            provider_sources=sorted({task.provider for task in tasks}),
            engagement_name=engagement_context.get("engagement_name"),
            client_name=engagement_context.get("client_name"),
            completion_rate=round(completion_rate, 4),
            avg_cycle_time_hours=round(statistics.mean(cycle_times), 2) if cycle_times else None,
            estimation_accuracy=1.0,
            tickets_total=total,
            tickets_done=len(done_tasks),
            tickets_in_progress=len(wip_tasks),
            tickets_blocked=len(blocked_tasks),
            story_points_completed=story_done,
            story_points_total=story_total,
            blocker_rate=round(blocker_rate, 4),
            avg_blocker_age_hours=round(statistics.mean(blocker_ages), 2) if blocker_ages else None,
            blocker_count=len(blocked_tasks),
            active_blockers=len(blocked_tasks),
            resolved_blockers=0,
            stalled_ticket_count=len(blocked_tasks),
            task_type_profile=self._integration_task_type_profile(tasks, done_tasks),
            question_response_time_hours=avg_response,
            unanswered_question_rate=round(unanswered_rate, 4) if unanswered_rate is not None else None,
            comment_response_time_hours=avg_response,
            median_comment_response_time_hours=response["median_response_time_hours"],
            unanswered_questions_count=response["unanswered_count"],
            average_response_time_per_ticket_hours=response["average_response_time_per_ticket_hours"],
            tickets_exceeded_ert=response["tickets_exceeded_ert"],
            ert_target_hours=ert_target,
            ert_status=ert_status,
            ticket_response_metrics=response["ticket_metrics"],
            status=status,
            warning_signals=warning_signals,
            computed_at=now.isoformat(),
        )

    @staticmethod
    def _comments_by_task(comments: list[IntegrationComment]) -> dict[int, list[IntegrationComment]]:
        out: dict[int, list[IntegrationComment]] = defaultdict(list)
        for comment in comments:
            out[comment.task_id].append(comment)
        return {
            task_id: sorted(items, key=lambda item: item.external_created_at)
            for task_id, items in out.items()
        }

    @staticmethod
    def _integration_story_points(task: IntegrationTask) -> int:
        if task.story_points is None:
            return 1
        return max(int(round(task.story_points)), 0)

    @staticmethod
    def _is_integration_blocked(task: IntegrationTask) -> bool:
        labels = " ".join(str(label).lower() for label in (task.labels or []))
        return task.status == "blocked" or any(token in labels for token in ("blocked", "blocker", "on hold"))

    @staticmethod
    def _integration_cycle_time(task: IntegrationTask) -> float | None:
        if not task.external_created_at or not task.external_updated_at:
            return None
        hours = (_tz(task.external_updated_at) - _tz(task.external_created_at)).total_seconds() / 3600
        return round(hours, 2) if hours > 0 else None

    @staticmethod
    def _integration_blocker_age(task: IntegrationTask, now: datetime) -> float | None:
        anchor = task.external_updated_at or task.external_created_at or task.updated_at
        if anchor is None:
            return None
        hours = (_tz(now) - _tz(anchor)).total_seconds() / 3600
        return round(hours, 2) if hours >= 0 else None

    def _integration_response_metrics(
        self,
        *,
        tasks: list[IntegrationTask],
        comments_by_task: dict[int, list[IntegrationComment]],
        developer_external_ids: set[str],
        ert_target_hours: float | None,
        now: datetime,
    ) -> dict:
        all_response_times: list[float] = []
        per_ticket_response_times: list[float] = []
        unanswered_count = 0
        teammate_comment_count = 0
        tickets_exceeded_ert = 0
        ticket_metrics: list[DeveloperTicketResponseMetric] = []

        for task in tasks:
            comments = comments_by_task.get(task.id, [])
            response_times: list[float] = []
            task_unanswered = 0
            for index, comment in enumerate(comments):
                author = comment.author_external_id
                if not author or author in developer_external_ids:
                    continue
                if not (comment.body or "").strip():
                    continue
                teammate_comment_count += 1
                response = next(
                    (
                        later
                        for later in comments[index + 1:]
                        if later.author_external_id in developer_external_ids
                    ),
                    None,
                )
                if response is None:
                    task_unanswered += 1
                    unanswered_count += 1
                    continue
                hours = (
                    _tz(response.external_created_at) - _tz(comment.external_created_at)
                ).total_seconds() / 3600
                if hours >= 0:
                    response_times.append(hours)
                    all_response_times.append(hours)

            avg_ticket_response = round(statistics.mean(response_times), 2) if response_times else None
            if avg_ticket_response is not None:
                per_ticket_response_times.append(avg_ticket_response)
            blocked = self._is_integration_blocked(task)
            blocker_duration = self._integration_blocker_age(task, now) if blocked else None
            exceeded = None
            if ert_target_hours is not None:
                exceeded = bool(
                    task_unanswered > 0
                    or any(value > ert_target_hours for value in response_times)
                )
                if exceeded:
                    tickets_exceeded_ert += 1
            ticket_metrics.append(DeveloperTicketResponseMetric(
                ticket_id=task.external_task_id,
                ticket_title=task.title,
                provider=task.provider,
                response_time_hours=avg_ticket_response,
                unanswered_questions=task_unanswered,
                exceeded_ert=exceeded,
                blocker_status="blocked" if blocked else "clear",
                blocker_duration_hours=blocker_duration,
            ))

        return {
            "average_response_time_hours": (
                round(statistics.mean(all_response_times), 2) if all_response_times else None
            ),
            "median_response_time_hours": (
                round(statistics.median(all_response_times), 2) if all_response_times else None
            ),
            "average_response_time_per_ticket_hours": (
                round(statistics.mean(per_ticket_response_times), 2)
                if per_ticket_response_times else None
            ),
            "unanswered_count": unanswered_count,
            "teammate_comment_count": teammate_comment_count,
            "tickets_exceeded_ert": tickets_exceeded_ert,
            "ticket_metrics": ticket_metrics,
        }

    @staticmethod
    def _ert_status(
        avg_response_hours: float | None,
        ert_target_hours: float | None,
        tickets_exceeded_ert: int,
    ) -> str:
        if ert_target_hours is None:
            return "not-available"
        if tickets_exceeded_ert > 0:
            return "exceeded"
        if avg_response_hours is None:
            return "not-available"
        return "within-target" if avg_response_hours <= ert_target_hours else "exceeded"

    @staticmethod
    def _integration_task_type_profile(
        tasks: list[IntegrationTask],
        done_tasks: list[IntegrationTask],
    ) -> list[TaskTypeProfile]:
        done_ids = {task.id for task in done_tasks}
        buckets: dict[str, dict] = {}
        for task in tasks:
            task_type = task.task_type or "task"
            buckets.setdefault(task_type, {"total": 0, "done": 0, "hours": []})
            buckets[task_type]["total"] += 1
            if task.id in done_ids:
                buckets[task_type]["done"] += 1
                hours = DeveloperKPIService._integration_cycle_time(task)
                if hours is not None:
                    buckets[task_type]["hours"].append(hours)
        return [
            TaskTypeProfile(
                ticket_type=task_type,
                count_total=data["total"],
                count_done=data["done"],
                avg_cycle_time_hours=(
                    round(statistics.mean(data["hours"]), 2) if data["hours"] else None
                ),
            )
            for task_type, data in sorted(buckets.items())
        ]

    @staticmethod
    def _latest_integration_activity(
        metrics: list[DeveloperTicketResponseMetric],
        now: datetime,
    ) -> datetime | None:
        if metrics:
            return now
        return None

    # ── Data fetchers ───────────────────────────────────────────────────────────

    async def _get_board(self, project_id: int) -> TrelloBoard | None:
        result = await self._db.execute(
            select(TrelloBoard)
            .join(TrelloCredential, TrelloBoard.credential_id == TrelloCredential.id)
            .where(
                TrelloCredential.project_id == project_id,
                TrelloCredential.is_active.is_(True),
            )
            .order_by(TrelloBoard.last_synced_at.desc().nullslast(), TrelloBoard.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _load_cards(
        self,
        board_id: int,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[tuple[TrelloCard, TrelloList | None]]:
        stmt = (
            select(TrelloCard, TrelloList)
            .join(TrelloList, TrelloCard.list_id == TrelloList.id, isouter=True)
            .where(TrelloCard.board_id == board_id, TrelloCard.is_closed.is_(False))
        )
        start_dt = _parse_range_bound(start_date)
        end_dt = _parse_range_bound(end_date)
        activity_anchor = func.coalesce(TrelloCard.trello_last_activity, TrelloCard.updated_at)
        if start_dt is not None:
            stmt = stmt.where(activity_anchor >= start_dt)
        if end_dt is not None:
            stmt = stmt.where(activity_anchor <= end_dt)
        result = await self._db.execute(stmt.order_by(TrelloCard.id))
        return list(result.all())

    async def _load_comment_actions(
        self,
        board_id: int,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[TrelloAction]:
        """All commentCard actions for cards on this board, chronological."""
        card_ids_result = await self._db.execute(
            select(TrelloCard.id).where(
                TrelloCard.board_id == board_id,
                TrelloCard.is_closed.is_(False),
            )
        )
        card_ids = [r[0] for r in card_ids_result.fetchall()]
        if not card_ids:
            return []

        stmt = (
            select(TrelloAction)
            .where(
                TrelloAction.card_id.in_(card_ids),
                TrelloAction.action_type == "commentCard",
            )
        )
        start_dt = _parse_range_bound(start_date)
        end_dt = _parse_range_bound(end_date)
        if start_dt is not None:
            stmt = stmt.where(TrelloAction.action_date >= start_dt)
        if end_dt is not None:
            stmt = stmt.where(TrelloAction.action_date <= end_dt)
        result = await self._db.execute(stmt.order_by(TrelloAction.action_date))
        return list(result.scalars().all())

    async def _build_name_map(
        self, board: TrelloBoard, project_id: int
    ) -> dict[str, str]:
        """
        Build a {trello_member_id: display_name} map using two strategies:

        1. Trello API  — most accurate; uses board members endpoint.
        2. All actions — scans every TrelloAction row for the board.
           Actions of any type (addMemberToCard, updateCard, etc.) carry
           trello_member_id + member_name, so even members who never comment
           will appear here if they created or updated a card.
        """
        name_map: dict[str, str] = {}

        # Strategy 1: Trello API (live member list with real full names)
        try:
            cred_result = await self._db.execute(
                select(TrelloCredential).where(
                    TrelloCredential.project_id == project_id,
                    TrelloCredential.is_active.is_(True),
                )
            )
            cred = cred_result.scalar_one_or_none()
            if cred:
                from app.config import settings
                from app.services.trello.client import TrelloClient
                async with TrelloClient(
                    api_key=cred.api_key,
                    api_token=cred.api_token,
                    redis_url=settings.redis_url,
                ) as client:
                    members = await client.get_board_members(board.trello_id)
                    for m in members:
                        if m.id:
                            name_map[m.id] = m.fullName or m.username or m.id
        except Exception:
            logger.warning("trello_member_api_failed_for_kpi", board_id=board.id)

        # Strategy 2: All stored TrelloAction rows for this board
        card_ids_result = await self._db.execute(
            select(TrelloCard.id).where(TrelloCard.board_id == board.id)
        )
        card_ids = [r[0] for r in card_ids_result.fetchall()]
        if card_ids:
            actions_result = await self._db.execute(
                select(TrelloAction.trello_member_id, TrelloAction.member_name)
                .where(
                    TrelloAction.card_id.in_(card_ids),
                    TrelloAction.trello_member_id.is_not(None),
                    TrelloAction.member_name.is_not(None),
                )
                .distinct()
            )
            for mid, mname in actions_result.fetchall():
                if mid and mname and mid not in name_map:
                    name_map[mid] = mname

        return name_map

    # ── Member extraction ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_members(
        cards_with_lists: list[tuple[TrelloCard, TrelloList | None]],
        comment_actions: list[TrelloAction],
        name_map: dict[str, str],
    ) -> list[_Member]:
        """
        Collect all unique Trello members from:
          1. card.member_ids  — who is assigned to cards
          2. TrelloAction     — who has commented (for QRT)

        Names are resolved via name_map (API + all actions),
        falling back to a shortened version of the raw ID if unknown.
        """
        seen: dict[str, _Member] = {}

        def _resolve_name(mid: str) -> str:
            return name_map.get(mid) or mid[:8]  # show first 8 chars, not full 24-char ID

        # Members assigned to cards
        for card, _ in cards_with_lists:
            for mid in (card.member_ids or []):
                if isinstance(mid, str) and mid and mid not in seen:
                    seen[mid] = _Member(
                        trello_id=mid,
                        name=_resolve_name(mid),
                        username=mid,
                    )

        # Comment authors (may include members not assigned to any card)
        for action in comment_actions:
            mid = action.trello_member_id
            if mid and mid not in seen:
                seen[mid] = _Member(
                    trello_id=mid,
                    name=_resolve_name(mid),
                    username=mid,
                )

        return list(seen.values())

    @staticmethod
    def _cards_for_member(
        trello_id: str,
        cards_with_lists: list[tuple[TrelloCard, TrelloList | None]],
    ) -> list[tuple[TrelloCard, TrelloList | None]]:
        return [
            (card, lst)
            for card, lst in cards_with_lists
            if trello_id in (card.member_ids or [])
        ]

    # ── Core KPI builder ────────────────────────────────────────────────────────

    def _build_report(
        self,
        member: _Member,
        project_id: int,
        sprint_id: int | None,
        cards_with_lists: list[tuple[TrelloCard, TrelloList | None]],
        all_comment_actions: list[TrelloAction],
        now: datetime,
    ) -> DeveloperKPIReport:
        done_cards = [
            c for c, lst in cards_with_lists
            if lst and lst.list_type == ListType.DONE
        ]
        wip_cards = [
            c for c, lst in cards_with_lists
            if lst and lst.list_type == ListType.WIP
        ]
        stalled_cards = [c for c, _ in cards_with_lists if c.is_stalled]
        total = len(cards_with_lists)

        completion_rate = len(done_cards) / total if total > 0 else 0.0
        avg_cycle = self._avg_cycle_time(done_cards)

        sp_done = sum(_story_points(c.labels) for c in done_cards)
        sp_total = sum(_story_points(c.labels) for c, _ in cards_with_lists)

        blocker_rate = len(stalled_cards) / total if total > 0 else 0.0
        active_blockers = len([c for c in stalled_cards if c in wip_cards])
        avg_blocker_age = self._avg_stall_age(stalled_cards, now)
        stalled_in_wip = len([c for c in wip_cards if c.is_stalled])

        profile = self._task_type_profile(cards_with_lists, done_cards)

        # QRT / UQR — filter comment actions to cards this member is on
        my_card_ids = {card.id for card, _ in cards_with_lists}
        relevant_actions = [a for a in all_comment_actions if a.card_id in my_card_ids]
        qrt, uqr = self._compute_qrt_uqr(relevant_actions, {member.trello_id})

        status, warning_signals = self._determine_status(
            completion_rate=completion_rate,
            active_blockers=active_blockers,
            stalled=stalled_in_wip,
            uqr=uqr,
            blocker_rate=blocker_rate,
        )

        return DeveloperKPIReport(
            developer_id=member.numeric_id,
            developer_name=member.name,
            developer_role="member",
            project_id=project_id,
            sprint_id=sprint_id,
            completion_rate=round(completion_rate, 4),
            avg_cycle_time_hours=avg_cycle,
            estimation_accuracy=1.0,     # not available from Trello
            tickets_total=total,
            tickets_done=len(done_cards),
            tickets_in_progress=len(wip_cards),
            tickets_blocked=len(stalled_cards),
            story_points_completed=sp_done,
            story_points_total=sp_total,
            blocker_rate=round(blocker_rate, 4),
            avg_blocker_age_hours=avg_blocker_age,
            active_blockers=active_blockers,
            stalled_ticket_count=stalled_in_wip,
            task_type_profile=profile,
            question_response_time_hours=qrt,
            unanswered_question_rate=uqr,
            status=status,
            warning_signals=warning_signals,
            computed_at=now.isoformat(),
        )

    # ── Pure calculations ───────────────────────────────────────────────────────

    @staticmethod
    def _avg_cycle_time(done_cards: list[TrelloCard]) -> float | None:
        hours: list[float] = []
        for c in done_cards:
            if c.cycle_time_hours and c.cycle_time_hours > 0:
                hours.append(c.cycle_time_hours)
            elif c.entered_wip_at and c.entered_done_at:
                h = (_tz(c.entered_done_at) - _tz(c.entered_wip_at)).total_seconds() / 3600
                if h > 0:
                    hours.append(h)
        return round(statistics.mean(hours), 2) if hours else None

    @staticmethod
    def _avg_stall_age(stalled: list[TrelloCard], now: datetime) -> float | None:
        ages: list[float] = []
        for c in stalled:
            anchor = c.stalled_since or c.trello_last_activity or c.updated_at
            if anchor is None:
                continue
            ages.append((_tz(now) - _tz(anchor)).total_seconds() / 3600)
        return round(statistics.mean(ages), 2) if ages else None

    @staticmethod
    def _task_type_profile(
        all_cards: list[tuple[TrelloCard, TrelloList | None]],
        done_cards: list[TrelloCard],
    ) -> list[TaskTypeProfile]:
        done_ids = {c.id for c in done_cards}
        buckets: dict[str, dict] = {}

        for card, _ in all_cards:
            tt = _ticket_type(card.labels)
            buckets.setdefault(tt, {"total": 0, "done": 0, "hours": []})
            buckets[tt]["total"] += 1
            if card.id in done_ids:
                buckets[tt]["done"] += 1
                h: float | None = None
                if card.cycle_time_hours and card.cycle_time_hours > 0:
                    h = card.cycle_time_hours
                elif card.entered_wip_at and card.entered_done_at:
                    h = (_tz(card.entered_done_at) - _tz(card.entered_wip_at)).total_seconds() / 3600
                    if h <= 0:
                        h = None
                if h is not None:
                    buckets[tt]["hours"].append(h)

        return [
            TaskTypeProfile(
                ticket_type=tt,
                count_total=data["total"],
                count_done=data["done"],
                avg_cycle_time_hours=(
                    round(statistics.mean(data["hours"]), 2) if data["hours"] else None
                ),
            )
            for tt, data in sorted(buckets.items())
        ]

    @staticmethod
    def _compute_qrt_uqr(
        actions: list[TrelloAction],
        member_trello_ids: set[str],
    ) -> tuple[float | None, float | None]:
        """
        Scan comment actions grouped by card.
        A question = a commentCard from this member containing "?".
        A response = next commentCard on the same card from a DIFFERENT member.
        Unanswered = no response exists after the question.
        """
        if not actions:
            return None, None

        by_card: dict[int | None, list[TrelloAction]] = {}
        for a in actions:
            by_card.setdefault(a.card_id, []).append(a)

        response_times: list[float] = []
        total_q = 0
        unanswered = 0

        for card_actions in by_card.values():
            sorted_acts = sorted(card_actions, key=lambda x: x.action_date)

            for i, act in enumerate(sorted_acts):
                mid = act.trello_member_id or ""
                if mid not in member_trello_ids:
                    continue  # not this developer's comment

                # Extract comment text from Trello action data
                data = act.data or {}
                text = (
                    data.get("text", "")
                    or (data.get("comment") or {}).get("text", "")
                    or ""
                )
                if not _QUESTION_RE.search(text):
                    continue

                total_q += 1
                q_time = _tz(act.action_date)
                found = False

                for reply in sorted_acts[i + 1:]:
                    reply_mid = reply.trello_member_id or ""
                    if reply_mid and reply_mid not in member_trello_ids:
                        delta = (_tz(reply.action_date) - q_time).total_seconds() / 3600
                        response_times.append(delta)
                        found = True
                        break

                if not found:
                    unanswered += 1

        qrt = round(statistics.mean(response_times), 2) if response_times else None
        uqr = round(unanswered / total_q, 4) if total_q > 0 else None
        return qrt, uqr

    @staticmethod
    def _determine_status(
        completion_rate: float,
        active_blockers: int,
        stalled: int,
        uqr: float | None,
        blocker_rate: float,
    ) -> tuple[str, list[str]]:
        warnings: list[str] = []
        if active_blockers > 0:
            warnings.append(
                f"{active_blockers} stalled card{'s' if active_blockers > 1 else ''} in WIP — needs attention"
            )
        if stalled > 0 and stalled != active_blockers:
            warnings.append(
                f"{stalled} card{'s' if stalled > 1 else ''} stalled with no recent activity"
            )
        if uqr is not None and uqr > 0.30:
            warnings.append(
                f"{uqr * 100:.0f}% of questions unanswered beyond {_QRT_THRESHOLD_HOURS}h"
            )
        if blocker_rate > 0.40:
            warnings.append(
                f"{blocker_rate * 100:.0f}% of cards stalled — process review recommended"
            )

        if active_blockers > 0 or completion_rate < 0.30:
            status = "behind"
        elif completion_rate < 0.60 or (uqr is not None and uqr > 0.30) or stalled > 1:
            status = "at-risk"
        else:
            status = "on-track"

        return status, warnings

    @staticmethod
    def _latest_activity_at(
        cards_with_lists: list[tuple[TrelloCard, TrelloList | None]],
    ) -> datetime | None:
        anchors: list[datetime] = []
        for card, _ in cards_with_lists:
            candidate = (
                card.trello_last_activity
                or card.updated_at
                or card.entered_done_at
                or card.entered_wip_at
                or card.created_at
            )
            if candidate is not None:
                anchors.append(_tz(candidate))
        return max(anchors) if anchors else None

    @staticmethod
    def _activity_freshness(
        latest_activity_at: datetime | None,
        now: datetime,
    ) -> str:
        if latest_activity_at is None:
            return "unknown"

        age_hours = (_tz(now) - _tz(latest_activity_at)).total_seconds() / 3600
        if age_hours <= 24:
            return "active"
        if age_hours <= 72:
            return "recent"
        return "stale"

    @staticmethod
    def _client_risk_note(
        report: DeveloperKPIReport,
        freshness: str,
    ) -> str | None:
        if report.active_blockers > 0:
            return (
                f"{report.active_blockers} blocked work item"
                f"{'s are' if report.active_blockers > 1 else ' is'} slowing delivery."
            )
        if freshness == "stale" and report.tickets_in_progress > 0:
            return "Active work has not moved recently and needs follow-up."
        if report.unanswered_question_rate is not None and report.unanswered_question_rate > 0.30:
            return "Open questions are delaying execution and creating delivery risk."
        if report.status == "behind":
            return "Delivery is behind plan and should be reviewed with the team."
        if report.status == "at-risk":
            return "Progress is moving, but this delivery stream needs closer monitoring."
        return None

    def _build_client_summary(
        self,
        cards_with_lists: list[tuple[TrelloCard, TrelloList | None]],
        client_members: list[ClientProgressMember],
        now: datetime,
    ) -> ClientProgressSummary:
        cards = [card for card, _ in cards_with_lists]
        done_cards = [
            card for card, lst in cards_with_lists if lst and lst.list_type == ListType.DONE
        ]
        wip_blocked = [
            card
            for card, lst in cards_with_lists
            if lst and lst.list_type == ListType.WIP and card.is_stalled
        ]

        total_cards = len(cards)
        total_story_points = sum(_story_points(card.labels) for card in cards)
        done_story_points = sum(_story_points(card.labels) for card in done_cards)

        return ClientProgressSummary(
            total_developers=len(client_members),
            on_track_count=sum(1 for member in client_members if member.status == "on-track"),
            at_risk_count=sum(1 for member in client_members if member.status == "at-risk"),
            behind_count=sum(1 for member in client_members if member.status == "behind"),
            overall_completion_rate=(
                round(len(done_cards) / total_cards, 4) if total_cards > 0 else 0.0
            ),
            story_points_completed=done_story_points,
            story_points_total=total_story_points,
            active_blockers=len(wip_blocked),
            avg_cycle_time_hours=self._avg_cycle_time(done_cards),
            last_updated_at=now.isoformat(),
        )

    # ── Empty fallbacks ─────────────────────────────────────────────────────────

    @staticmethod
    def _empty_team_report(project_id: int, sprint_id: int | None, now: datetime) -> TeamKPIReport:
        return TeamKPIReport(
            project_id=project_id,
            sprint_id=sprint_id,
            members=[],
            team_avg_cycle_time_hours=None,
            team_completion_rate=0.0,
            team_blocker_rate=0.0,
            team_question_response_time_hours=None,
            team_unanswered_question_rate=None,
            warning_signals=[],
            computed_at=now.isoformat(),
        )

    @staticmethod
    def _empty_client_report(
        project_id: int,
        sprint_id: int | None,
        now: datetime,
    ) -> ClientProgressReport:
        return ClientProgressReport(
            project_id=project_id,
            sprint_id=sprint_id,
            summary=ClientProgressSummary(
                total_developers=0,
                on_track_count=0,
                at_risk_count=0,
                behind_count=0,
                overall_completion_rate=0.0,
                story_points_completed=0,
                story_points_total=0,
                active_blockers=0,
                avg_cycle_time_hours=None,
                last_updated_at=now.isoformat(),
            ),
            members=[],
            computed_at=now.isoformat(),
        )

    async def snapshot_sprint_kpis(self, project_id: int, sprint_id: int, now: datetime) -> None:
        """
        Compute KPIs for all developers in the project/sprint and commit them
        as historical snapshots to the DeveloperSprintKPI table.
        This provides a permanent historical record for comparing future sprints.
        """
        report = await self.compute_team_kpis(project_id, sprint_id)
        if not report:
            return

        for member in report.members:
            # Reconstruct the developer's full report accurately to preserve the detailed matrix
            dev_report = await self.compute_developer_kpis(member.developer_id, project_id, sprint_id)
            if not dev_report:
                continue

            snapshot = DeveloperSprintKPI(
                developer_id=member.developer_id,
                project_id=project_id,
                sprint_id=sprint_id,
                completion_rate=dev_report.completion_rate,
                avg_cycle_time_hours=dev_report.avg_cycle_time_hours,
                estimation_accuracy=dev_report.estimation_accuracy,
                tickets_total=dev_report.tickets_total,
                tickets_done=dev_report.tickets_done,
                story_points_completed=dev_report.story_points_completed,
                story_points_total=dev_report.story_points_total,
                blocker_rate=dev_report.blocker_rate,
                avg_blocker_age_hours=dev_report.avg_blocker_age_hours,
                blocker_count=dev_report.blocker_count,
                question_response_time_hours=dev_report.question_response_time_hours,
                unanswered_question_rate=dev_report.unanswered_question_rate,
                raw_snapshot_data=dev_report.model_dump(),
                computed_at=now,
            )
            self._db.add(snapshot)
        await self._db.flush()
