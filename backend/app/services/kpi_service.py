"""
KPI Computation Engine
======================

Computes the following metrics for a given sprint:

  cycle_time       — avg hours from first IN_PROGRESS → DONE
  lead_time        — avg hours from ticket creation → DONE
  velocity         — sum of story_points for DONE tickets
  completion_rate  — DONE count / committed count
  estimation_acc   — 1 - mean(|actual - estimated| / estimated)
  throughput       — DONE tickets / calendar days elapsed
  bug_rate         — BUG type tickets / total tickets

All computations are pure (no external I/O inside the calculation methods)
so they can be tested without a database.
"""
from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.core.metrics import KPI_COMPUTATION_DURATION_SECONDS
from app.domain.value_objects.ticket_status import TicketStatus
from app.models.kpi_snapshot import KPISnapshot
from app.models.ticket import Ticket
from app.repositories.sprint_repository import SprintRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.kpi import KPIDashboard, KPIResponse

logger = get_logger(__name__)


class KPIService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sprint_repo = SprintRepository(session)
        self._ticket_repo = TicketRepository(session)

    # ── Public API ──────────────────────────────────────────────────────────

    async def compute_and_persist(
        self, project_id: int, sprint_id: int
    ) -> KPISnapshot:
        """Compute KPIs for a sprint, persist a new snapshot, return it."""
        with KPI_COMPUTATION_DURATION_SECONDS.time():
            sprint = await self._sprint_repo.get_by_id(sprint_id)
            if sprint is None:
                raise ValueError(f"Sprint {sprint_id} not found")

            tickets = await self._ticket_repo.get_by_sprint(sprint_id)
            kpis = self._calculate(sprint, tickets)

        snapshot = KPISnapshot(
            project_id=project_id,
            sprint_id=sprint_id,
            **kpis,
            computed_at=datetime.now(UTC),
        )
        self._session.add(snapshot)
        await self._session.flush()
        await self._session.refresh(snapshot)

        logger.info(
            "kpis_computed",
            project_id=project_id,
            sprint_id=sprint_id,
            velocity=kpis.get("velocity"),
            completion_rate=kpis.get("completion_rate"),
        )
        return snapshot

    async def get_dashboard(
        self, project_id: int, sprint_id: int | None = None
    ) -> KPIDashboard:
        """Assemble the full KPI dashboard payload."""
        from sqlalchemy import desc, select
        from app.models.blocker import Blocker
        from app.models.repository_activity import RepositoryActivity

        # Latest KPI snapshot
        from sqlalchemy import select as sa_select
        stmt = sa_select(KPISnapshot).where(
            KPISnapshot.project_id == project_id
        )
        if sprint_id:
            stmt = stmt.where(KPISnapshot.sprint_id == sprint_id)
        stmt = stmt.order_by(KPISnapshot.computed_at.desc()).limit(1)
        result = await self._session.execute(stmt)
        latest_snapshot = result.scalar_one_or_none()

        current_kpis = (
            KPIResponse.model_validate(latest_snapshot) if latest_snapshot else None
        )

        # Velocity trend: last 5 completed sprints
        completed = await self._sprint_repo.get_completed_sprints(project_id, limit=5)
        velocity_trend = [s.velocity for s in reversed(completed)]
        completion_trend: list[float] = []
        for s in reversed(completed):
            rate = s.completed_points / s.committed_points if s.committed_points > 0 else 0.0
            completion_trend.append(round(rate, 4))

        # Open blockers
        from sqlalchemy import func
        blocker_count_result = await self._session.execute(
            sa_select(func.count()).select_from(Blocker).where(Blocker.resolved_at.is_(None))
        )
        open_blockers = blocker_count_result.scalar_one()

        # Stalled tickets
        from app.config import settings
        stalled = await self._ticket_repo.get_stalled_tickets(settings.stall_threshold_l1_hours)
        stalled_tickets = len(stalled)

        # Repo mismatches
        mismatch_result = await self._session.execute(
            sa_select(func.count())
            .select_from(RepositoryActivity)
            .where(
                RepositoryActivity.mismatch_detected.is_(True),
                RepositoryActivity.project_id == project_id,
            )
        )
        repo_mismatches = mismatch_result.scalar_one()

        return KPIDashboard(
            project_id=project_id,
            sprint_id=sprint_id,
            current_kpis=current_kpis,
            velocity_trend=velocity_trend,
            completion_trend=completion_trend,
            open_blockers=open_blockers,
            stalled_tickets=stalled_tickets,
            repo_mismatches=repo_mismatches,
        )

    # ── Pure computation (no I/O) ───────────────────────────────────────────

    def _calculate(self, sprint, tickets: list[Ticket]) -> dict:
        done_tickets = [t for t in tickets if t.status == TicketStatus.DONE.value]
        all_tickets = tickets

        return {
            "cycle_time_hours": self._cycle_time(done_tickets),
            "lead_time_hours": self._lead_time(done_tickets),
            "velocity": self._velocity(done_tickets),
            "completion_rate": self._completion_rate(sprint, done_tickets),
            "estimation_accuracy": self._estimation_accuracy(done_tickets),
            "throughput": self._throughput(sprint, done_tickets),
            "bug_rate": self._bug_rate(all_tickets),
        }

    @staticmethod
    def _cycle_time(done_tickets: list[Ticket]) -> float | None:
        """
        Approximation: updated_at - last time status changed to in_progress.
        We use updated_at - created_at as a proxy when no status log exists.
        """
        durations: list[float] = []
        for t in done_tickets:
            if t.actual_hours is not None:
                durations.append(t.actual_hours)
            elif t.updated_at and t.created_at:
                start = t.created_at
                end = t.updated_at
                if start.tzinfo is None:
                    start = start.replace(tzinfo=UTC)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=UTC)
                hours = (end - start).total_seconds() / 3600
                if hours > 0:
                    durations.append(hours)
        return round(statistics.mean(durations), 2) if durations else None

    @staticmethod
    def _lead_time(done_tickets: list[Ticket]) -> float | None:
        durations: list[float] = []
        for t in done_tickets:
            if t.created_at and t.updated_at:
                start = t.created_at
                end = t.updated_at
                if start.tzinfo is None:
                    start = start.replace(tzinfo=UTC)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=UTC)
                hours = (end - start).total_seconds() / 3600
                if hours > 0:
                    durations.append(hours)
        return round(statistics.mean(durations), 2) if durations else None

    @staticmethod
    def _velocity(done_tickets: list[Ticket]) -> float:
        return float(sum(t.story_points or 0 for t in done_tickets))

    @staticmethod
    def _completion_rate(sprint, done_tickets: list[Ticket]) -> float:
        committed = sprint.committed_points or 0
        if committed == 0:
            return 0.0
        completed = sum(t.story_points or 0 for t in done_tickets)
        return round(min(completed / committed, 1.0), 4)

    @staticmethod
    def _estimation_accuracy(done_tickets: list[Ticket]) -> float | None:
        errors: list[float] = []
        for t in done_tickets:
            if t.estimated_hours and t.actual_hours and t.estimated_hours > 0:
                rel_error = abs(t.actual_hours - t.estimated_hours) / t.estimated_hours
                errors.append(rel_error)
        if not errors:
            return None
        return round(1.0 - statistics.mean(errors), 4)

    @staticmethod
    def _throughput(sprint, done_tickets: list[Ticket]) -> float | None:
        from datetime import date as date_type
        today = datetime.now(UTC).date()
        start = sprint.start_date
        elapsed_days = (today - start).days
        if elapsed_days <= 0:
            return None
        return round(len(done_tickets) / elapsed_days, 4)

    @staticmethod
    def _bug_rate(all_tickets: list[Ticket]) -> float | None:
        if not all_tickets:
            return None
        bugs = sum(1 for t in all_tickets if t.ticket_type == "bug")
        return round(bugs / len(all_tickets), 4)
