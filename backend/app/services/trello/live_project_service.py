from __future__ import annotations

import hashlib
import re
import statistics
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.sprint import Sprint
from app.models.trello_action import TrelloAction
from app.models.trello_board import TrelloBoard
from app.models.trello_card import TrelloCard, TrelloCardMovement
from app.models.trello_credential import TrelloCredential
from app.models.trello_list import ListType, TrelloList
from app.schemas.blocker import EnrichedBlockerResponse
from app.schemas.burndown import BurndownChart, BurndownEntryResponse
from app.schemas.developer import DeveloperResponse
from app.schemas.kpi import KPIDashboard, KPIResponse
from app.schemas.repository_activity import RepositoryMismatchResponse
from app.schemas.ticket import TicketResponse
from app.services.trello.analytics_service import TrelloAnalyticsService
from app.services.trello.client import TrelloClient

_POINTS_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*(?:sp|pts?|points?)\b", re.IGNORECASE)


def _parse_range_bound(value: str | None) -> datetime | None:
    if not value:
        return None
    from dateutil.parser import parse as parse_date

    parsed = parse_date(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class TrelloLiveProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_primary_board(self, project_id: int) -> tuple[TrelloBoard, TrelloCredential] | None:
        result = await self._session.execute(
            select(TrelloBoard, TrelloCredential)
            .join(TrelloCredential, TrelloBoard.credential_id == TrelloCredential.id)
            .where(TrelloCredential.project_id == project_id, TrelloCredential.is_active.is_(True))
            .order_by(TrelloBoard.last_synced_at.desc().nullslast(), TrelloBoard.id.asc())
        )
        row = result.first()
        if not row:
            return None
        return row[0], row[1]

    async def ensure_live_sprint(self, project_id: int, board: TrelloBoard) -> Sprint:
        result = await self._session.execute(
            select(Sprint)
            .where(Sprint.project_id == project_id, Sprint.status == "active")
            .order_by(Sprint.id.desc())
        )
        sprint = result.scalar_one_or_none()

        card_stats = await self._load_board_cards(board.id)
        committed_points = sum(self._story_points(card.labels) for card, _ in card_stats)
        completed_points = sum(
            self._story_points(card.labels)
            for card, lst in card_stats
            if lst and lst.list_type == ListType.DONE
        )

        today = date.today()
        start_date = today - timedelta(days=13)
        end_date = today + timedelta(days=1)

        if sprint is None:
            sprint = Sprint(
                project_id=project_id,
                name=f"{board.name} Live Board",
                goal=f"Live Trello sync for {board.name}",
                start_date=start_date,
                end_date=end_date,
                status="active",
                committed_points=committed_points,
                completed_points=completed_points,
                velocity=float(completed_points),
            )
            self._session.add(sprint)
            await self._session.flush()
            await self._session.refresh(sprint)
            return sprint

        sprint.name = f"{board.name} Live Board"
        sprint.goal = f"Live Trello sync for {board.name}"
        sprint.start_date = start_date
        sprint.end_date = end_date
        sprint.status = "active"
        sprint.committed_points = committed_points
        sprint.completed_points = completed_points
        sprint.velocity = float(completed_points)
        await self._session.flush()
        await self._session.refresh(sprint)
        return sprint

    async def list_ticket_responses(
        self,
        project_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[TicketResponse]:
        board_info = await self.get_primary_board(project_id)
        if not board_info:
            return []

        board, _ = board_info
        rows = await self._load_board_cards(
            board.id,
            offset=offset,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
        return [self._to_ticket_response(project_id, card, lst) for card, lst in rows]

    async def get_ticket_response(self, project_id: int, ticket_id: int) -> TicketResponse | None:
        board_info = await self.get_primary_board(project_id)
        if not board_info:
            return None

        board, _ = board_info
        result = await self._session.execute(
            select(TrelloCard, TrelloList)
            .join(TrelloList, TrelloCard.list_id == TrelloList.id, isouter=True)
            .where(TrelloCard.board_id == board.id, TrelloCard.id == ticket_id)
        )
        row = result.first()
        if not row:
            return None
        return self._to_ticket_response(project_id, row[0], row[1])

    async def build_dashboard(
        self,
        project_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> KPIDashboard | None:
        board_info = await self.get_primary_board(project_id)
        if not board_info:
            return None

        board, credential = board_info
        if start_date or end_date:
            sprint = await self.ensure_live_sprint(project_id, board)
            rows = await self._load_board_cards(board.id, start_date=start_date, end_date=end_date)
            done_rows = [(card, lst) for card, lst in rows if lst and lst.list_type == ListType.DONE]
            cycle_times = [card.cycle_time_hours for card, _ in done_rows if card.cycle_time_hours is not None]
            lead_times = [card.lead_time_hours for card, _ in done_rows if card.lead_time_hours is not None]
            committed_points = sum(self._story_points(card.labels) for card, _ in rows)
            completed_points = sum(self._story_points(card.labels) for card, _ in done_rows)
            completion_rate = round(completed_points / committed_points, 4) if committed_points else 0.0
            throughput = float(len(done_rows))
            stalled_count = sum(1 for card, _ in rows if card.is_stalled)
            velocity = float(completed_points)
            return KPIDashboard(
                project_id=project_id,
                sprint_id=sprint.id,
                current_kpis=KPIResponse(
                    id=0,
                    project_id=project_id,
                    sprint_id=sprint.id,
                    cycle_time_hours=round(statistics.mean(cycle_times), 2) if cycle_times else None,
                    lead_time_hours=round(statistics.mean(lead_times), 2) if lead_times else None,
                    velocity=velocity,
                    completion_rate=completion_rate,
                    throughput=throughput,
                    estimation_accuracy=None,
                    bug_rate=None,
                    computed_at=datetime.now(UTC),
                ),
                velocity_trend=[velocity] if rows else [],
                completion_trend=[completion_rate] if rows else [],
                open_blockers=stalled_count,
                stalled_tickets=stalled_count,
                repo_mismatches=sum(1 for card, _ in rows if card.is_stalled),
            )

        analytics_service = TrelloAnalyticsService(self._session, _NullWebSocketManager())
        analytics = await analytics_service.compute_board_analytics(board)
        sprint = await self.ensure_live_sprint(project_id, board)

        current_kpis = KPIResponse(
            id=0,
            project_id=project_id,
            sprint_id=sprint.id,
            cycle_time_hours=analytics.avg_cycle_time_hours,
            lead_time_hours=analytics.avg_lead_time_hours,
            velocity=float(sprint.completed_points),
            completion_rate=round(
                sprint.completed_points / sprint.committed_points, 4
            ) if sprint.committed_points else 0.0,
            throughput=float(analytics.throughput_cards),
            estimation_accuracy=None,
            bug_rate=None,
            computed_at=analytics.computed_at,
        )

        velocity_trend = [float(sprint.completed_points)]
        completion_trend = [
            round(sprint.completed_points / sprint.committed_points, 4)
            if sprint.committed_points
            else 0.0
        ]

        return KPIDashboard(
            project_id=project_id,
            sprint_id=sprint.id,
            current_kpis=current_kpis,
            velocity_trend=velocity_trend,
            completion_trend=completion_trend,
            open_blockers=analytics.stalled_count,
            stalled_tickets=analytics.stalled_count,
            repo_mismatches=len(await self.list_repo_mismatches(project_id)),
        )

    async def build_burndown_chart(self, sprint_id: int) -> BurndownChart | None:
        sprint = await self._session.get(Sprint, sprint_id)
        if sprint is None:
            return None

        board_info = await self.get_primary_board(sprint.project_id)
        if not board_info:
            return None

        board, _ = board_info
        rows = await self._load_board_cards(board.id)

        committed_points = sum(self._story_points(card.labels) for card, _ in rows)
        today = date.today()
        end = min(sprint.end_date, today)
        sprint_days = max((sprint.end_date - sprint.start_date).days, 1)

        done_by_day: dict[date, int] = {}
        for card, lst in rows:
            if lst and lst.list_type == ListType.DONE and card.entered_done_at:
                done_day = card.entered_done_at.astimezone(UTC).date()
                done_by_day[done_day] = done_by_day.get(done_day, 0) + self._story_points(card.labels)

        entries: list[BurndownEntryResponse] = []
        day = sprint.start_date
        cumulative = 0
        entry_id = 1
        while day <= end:
            completed = done_by_day.get(day, 0)
            cumulative += completed
            remaining = max(committed_points - cumulative, 0)
            elapsed = (day - sprint.start_date).days
            ideal = max(committed_points * (1 - elapsed / sprint_days), 0.0)
            entries.append(
                BurndownEntryResponse(
                    id=entry_id,
                    sprint_id=sprint_id,
                    date=day,
                    remaining_points=remaining,
                    completed_points=completed,
                    ideal_remaining=round(ideal, 2),
                    cumulative_completed=cumulative,
                )
            )
            entry_id += 1
            day += timedelta(days=1)

        return BurndownChart(
            sprint_id=sprint_id,
            sprint_name=sprint.name,
            start_date=sprint.start_date,
            end_date=sprint.end_date,
            committed_points=committed_points,
            entries=entries,
        )

    async def list_blockers(
        self,
        project_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[EnrichedBlockerResponse]:
        board_info = await self.get_primary_board(project_id)
        if not board_info:
            return []

        board, _ = board_info
        await TrelloAnalyticsService(self._session, _NullWebSocketManager()).compute_board_analytics(board)
        stmt = (
            select(TrelloCard, TrelloList)
            .join(TrelloList, TrelloCard.list_id == TrelloList.id, isouter=True)
            .where(TrelloCard.board_id == board.id, TrelloCard.is_stalled.is_(True))
        )
        start_dt = _parse_range_bound(start_date)
        end_dt = _parse_range_bound(end_date)
        activity_anchor = func.coalesce(TrelloCard.trello_last_activity, TrelloCard.updated_at)
        if start_dt is not None:
            stmt = stmt.where(activity_anchor >= start_dt)
        if end_dt is not None:
            stmt = stmt.where(activity_anchor <= end_dt)
        rows = await self._session.execute(stmt.order_by(TrelloCard.stalled_since.asc().nullslast()))
        blockers: list[EnrichedBlockerResponse] = []
        for card, lst in rows.all():
            stalled_hours = self._stalled_hours(card)
            blockers.append(
                EnrichedBlockerResponse(
                    id=card.id,
                    ticket_id=card.id,
                    description=f"Stalled in Trello list '{lst.name if lst else 'unknown'}'",
                    stall_hours=stalled_hours,
                    escalation_level=self._escalation_level(stalled_hours),
                    detected_at=card.stalled_since or card.updated_at,
                    last_escalated_at=None,
                    resolved_at=None,
                    created_at=card.created_at,
                    updated_at=card.updated_at,
                    ticket_title=card.name,
                    ticket_assignee_id=self._member_numeric_id((card.member_ids or [None])[0]),
                )
            )
        return blockers

    async def list_developers(self, project_id: int) -> list[DeveloperResponse]:
        board_info = await self.get_primary_board(project_id)
        if not board_info:
            return []

        board, credential = board_info
        member_details: list[tuple[int, str, str, str | None]] = []
        try:
            async with TrelloClient(
                api_key=credential.api_key,
                api_token=credential.api_token,
                redis_url=settings.redis_url,
            ) as client:
                members = await client.get_board_members(board.trello_id)
            member_details = [
                (
                    self._member_numeric_id(member.id),
                    member.fullName,
                    member.username,
                    member.avatarUrl,
                )
                for member in members
            ]
        except Exception:
            action_rows = await self._session.execute(
                select(TrelloAction.trello_member_id, TrelloAction.member_name)
                .join(TrelloCard, TrelloAction.card_id == TrelloCard.id)
                .where(TrelloCard.board_id == board.id, TrelloAction.trello_member_id.is_not(None))
                .distinct()
            )
            member_details = [
                (
                    self._member_numeric_id(member_id),
                    member_name or member_id,
                    member_id,
                    None,
                )
                for member_id, member_name in action_rows.all()
            ]

        now = datetime.now(UTC)
        return [
            DeveloperResponse(
                id=member_id,
                name=name,
                email=f"{trello_member_id}@trello.local",
                username=name.lower().replace(" ", "-"),
                company_id=None,
                trello_member_id=trello_member_id,
                team="Trello",
                role="member",
                slack_id=None,
                github_username=None,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            for member_id, name, trello_member_id, _ in member_details
        ]

    async def list_repo_mismatches(
        self,
        project_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[RepositoryMismatchResponse]:
        """
        Return all active cards for the primary board.

        Mismatch logic (Trello-only, no real git integration):
        - A card is flagged only when it is genuinely stalled (is_stalled=True).
        - "done_without_due_complete" is intentionally NOT raised: Trello's
          due_complete flag is optional and almost never set by teams, so
          checking it produces a false positive for every Done card.
        """
        board_info = await self.get_primary_board(project_id)
        if not board_info:
            return []

        board, _ = board_info
        stmt = (
            select(TrelloCard, TrelloList)
            .join(TrelloList, TrelloCard.list_id == TrelloList.id, isouter=True)
            .where(TrelloCard.board_id == board.id, TrelloCard.is_closed.is_(False))
        )
        start_dt = _parse_range_bound(start_date)
        end_dt = _parse_range_bound(end_date)
        activity_anchor = func.coalesce(TrelloCard.trello_last_activity, TrelloCard.updated_at)
        if start_dt is not None:
            stmt = stmt.where(activity_anchor >= start_dt)
        if end_dt is not None:
            stmt = stmt.where(activity_anchor <= end_dt)
        rows = await self._session.execute(stmt.order_by(TrelloCard.trello_short_id.asc()))
        items: list[RepositoryMismatchResponse] = []
        for card, lst in rows.all():
            mismatch_type = None
            mismatch_reason = None
            if card.is_stalled:
                mismatch_type = "trello_stalled_card"
                stalled_hours = self._stalled_hours(card)
                mismatch_reason = (
                    f"Card stalled in '{lst.name if lst else 'unknown'}' "
                    f"for {stalled_hours:.0f}h with no activity."
                )

            # Use the Trello card's own short URL when available; fall back to
            # the board URL so every row still has something clickable.
            card_ref = (
                f"https://trello.com/c/{card.trello_id}"
                if card.trello_id
                else (board.short_url or f"T-{card.trello_short_id}")
            )

            items.append(
                RepositoryMismatchResponse(
                    id=card.id,
                    ticket_id=card.id,
                    project_id=project_id,
                    branch_name=card_ref,
                    commit_count=0,
                    pr_count=0,
                    pr_merged=False,
                    last_commit_at=card.trello_last_activity,
                    mismatch_type=mismatch_type,
                    mismatch_reason=mismatch_reason,
                    scanned_at=board.last_synced_at,
                )
            )
        return items

    async def velocity_history(
        self,
        project_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, float | str]]:
        board_info = await self.get_primary_board(project_id)
        if not board_info:
            return []

        board, _ = board_info
        if start_date or end_date:
            stmt = select(TrelloCard).where(
                TrelloCard.board_id == board.id,
                TrelloCard.entered_done_at.is_not(None),
            )
            start_dt = _parse_range_bound(start_date)
            end_dt = _parse_range_bound(end_date)
            if start_dt is not None:
                stmt = stmt.where(TrelloCard.entered_done_at >= start_dt)
            if end_dt is not None:
                stmt = stmt.where(TrelloCard.entered_done_at <= end_dt)
            cards = (await self._session.execute(stmt)).scalars().all()
            label = "Selected range"
            if start_date and end_date:
                label = f"{start_date[:10]} - {end_date[:10]}"
            return [{
                "sprint": label,
                "points": float(sum(self._story_points(card.labels) for card in cards)),
            }]

        today = date.today()
        series: list[dict[str, float | str]] = []
        for offset in range(4, -1, -1):
            start = today - timedelta(days=(offset + 1) * 7)
            end = today - timedelta(days=offset * 7)
            result = await self._session.execute(
                select(TrelloCard)
                .where(
                    TrelloCard.board_id == board.id,
                    TrelloCard.entered_done_at.is_not(None),
                    TrelloCard.entered_done_at >= datetime.combine(start, datetime.min.time(), tzinfo=UTC),
                    TrelloCard.entered_done_at < datetime.combine(end, datetime.min.time(), tzinfo=UTC),
                )
            )
            cards = result.scalars().all()
            series.append(
                {
                    "sprint": f"Week {-offset + 4}",
                    "points": float(sum(self._story_points(card.labels) for card in cards)),
                }
            )
        return series

    async def count_live_tickets(
        self,
        project_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        board_info = await self.get_primary_board(project_id)
        if not board_info:
            return 0

        board, _ = board_info
        stmt = select(func.count(TrelloCard.id)).where(
            TrelloCard.board_id == board.id,
            TrelloCard.is_closed.is_(False),
        )
        start_dt = _parse_range_bound(start_date)
        end_dt = _parse_range_bound(end_date)
        activity_anchor = func.coalesce(TrelloCard.trello_last_activity, TrelloCard.updated_at)
        if start_dt is not None:
            stmt = stmt.where(activity_anchor >= start_dt)
        if end_dt is not None:
            stmt = stmt.where(activity_anchor <= end_dt)
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def _load_board_cards(
        self,
        board_id: int,
        *,
        offset: int = 0,
        limit: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[tuple[TrelloCard, TrelloList | None]]:
        stmt = (
            select(TrelloCard, TrelloList)
            .join(TrelloList, TrelloCard.list_id == TrelloList.id, isouter=True)
            .where(TrelloCard.board_id == board_id, TrelloCard.is_closed.is_(False))
            .offset(offset)
        )
        start_dt = _parse_range_bound(start_date)
        end_dt = _parse_range_bound(end_date)
        activity_anchor = func.coalesce(TrelloCard.trello_last_activity, TrelloCard.updated_at)
        if start_dt is not None:
            stmt = stmt.where(activity_anchor >= start_dt)
        if end_dt is not None:
            stmt = stmt.where(activity_anchor <= end_dt)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt.order_by(TrelloCard.trello_short_id.asc()))
        return result.all()

    def _to_ticket_response(
        self,
        project_id: int,
        card: TrelloCard,
        lst: TrelloList | None,
    ) -> TicketResponse:
        return TicketResponse(
            id=card.id,
            project_id=project_id,
            sprint_id=None,
            assignee_id=self._member_numeric_id((card.member_ids or [None])[0]),
            reporter_id=None,
            title=card.name,
            description=card.description,
            status=self._ticket_status(card, lst),
            priority=self._priority(card.labels),
            ticket_type=self._ticket_type(card.labels),
            estimated_hours=None,
            actual_hours=card.cycle_time_hours,
            story_points=self._story_points(card.labels),
            quality_score=self._quality_score(card),
            last_activity_at=card.trello_last_activity or card.updated_at,
            created_at=card.trello_created_at or card.created_at,
            updated_at=card.updated_at,
        )

    def _ticket_status(self, card: TrelloCard, lst: TrelloList | None) -> str:
        if card.is_stalled:
            return "blocked"
        if lst is None or lst.list_type == ListType.UNKNOWN:
            return "backlog"
        if lst.list_type == ListType.BACKLOG:
            return "backlog"
        if lst.list_type == ListType.WIP:
            return "in_progress"
        return "done"

    def _priority(self, labels: list | None) -> str:
        label_text = " ".join((label.get("name") or "") for label in (labels or []) if isinstance(label, dict)).lower()
        if "critical" in label_text or "urgent" in label_text:
            return "critical"
        if "high" in label_text:
            return "high"
        if "low" in label_text:
            return "low"
        return "medium"

    def _ticket_type(self, labels: list | None) -> str:
        label_text = " ".join((label.get("name") or "") for label in (labels or []) if isinstance(label, dict)).lower()
        if "bug" in label_text:
            return "bug"
        if "feature" in label_text or "story" in label_text:
            return "feature"
        if "spike" in label_text:
            return "spike"
        return "task"

    def _story_points(self, labels: list | None) -> int:
        for label in labels or []:
            if not isinstance(label, dict):
                continue
            name = label.get("name") or ""
            match = _POINTS_PATTERN.search(name)
            if match:
                return int(match.group(1))
        return 1

    def _quality_score(self, card: TrelloCard) -> float:
        score = 0
        if card.description and len(card.description.strip()) >= 20:
            score += 25
        if card.member_ids:
            score += 20
        if card.labels:
            score += 20
        if card.due_date:
            score += 15
        if len(card.name.strip()) >= 10:
            score += 20
        return float(score)

    def _member_numeric_id(self, member_id: str | None) -> int | None:
        if not member_id:
            return None
        return int(hashlib.sha1(member_id.encode("utf-8")).hexdigest()[:8], 16)

    def _stalled_hours(self, card: TrelloCard) -> float:
        anchor = card.stalled_since or card.trello_last_activity or card.updated_at
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=UTC)
        return round((datetime.now(UTC) - anchor).total_seconds() / 3600, 1)

    def _escalation_level(self, stalled_hours: float) -> int:
        if stalled_hours >= settings.stall_threshold_l3_hours:
            return 3
        if stalled_hours >= settings.stall_threshold_l2_hours:
            return 2
        return 1


class _NullWebSocketManager:
    async def broadcast_to_project(self, project_id: int, payload: dict) -> int:
        return 0

    async def broadcast_global(self, payload: dict) -> int:
        return 0
