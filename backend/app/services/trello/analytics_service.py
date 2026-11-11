"""
TrelloAnalyticsService — board-level flow metrics.

Metrics computed
────────────────
Cycle time     Cards that have entered_wip_at AND entered_done_at.
               cycle_time_hours = entered_done_at − entered_wip_at (hours)

Lead time      Cards that have trello_created_at AND entered_done_at.
               lead_time_hours = entered_done_at − trello_created_at (hours)

Throughput     Count of cards that entered a Done list in the last N days
               (configurable, default 7 days).

WIP            Cards currently in a WIP-type list (not closed).

Flow efficiency
               Ratio of active time to total lead time.
               active_time = cycle_time_hours
               flow_efficiency = (cycle_time_hours / lead_time_hours) * 100

Blocker / stall detection
               Cards in WIP lists where trello_last_activity is older than
               stall_threshold_l1_hours (default 24 h).  Cards escalate to
               L2 (48 h) and L3 (72 h).  The `is_stalled` flag is set and
               `stalled_since` records when we first noticed the stall.
               A TrelloCardStalledEvent is emitted for newly stalled cards.

Card movement flow
               For each (from_list, to_list) pair count transitions — input
               data for a Sankey / flow diagram.

Histogram bucketing
               Configurable bucket boundaries (default: [8, 24, 48, 72, 120,
               240] hours → < 8 h, 8–24 h, …, > 240 h).

All writes are idempotent (UPDATE WHERE …).  The service does not commit;
the caller (Celery task or FastAPI endpoint) owns the transaction.
"""
from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta
from typing import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logging_config import get_logger
from app.domain.events.trello_events import TrelloAnalyticsUpdatedEvent, TrelloCardStalledEvent
from app.infrastructure.websocket_manager import WebSocketManager
from app.models.trello_board import TrelloBoard
from app.models.trello_card import TrelloCard, TrelloCardMovement
from app.models.trello_list import ListType, TrelloList
from app.schemas.trello import (
    CardMovementFlow,
    CycleTimeHistogram,
    TrelloAnalytics,
    TrelloBlockerRead,
    TrelloCardRead,
)

logger = get_logger(__name__)

# Default histogram bucket upper-bounds (hours). Overflow → ">{last}" bucket.
_DEFAULT_BUCKETS: list[float] = [8.0, 24.0, 48.0, 72.0, 120.0, 240.0]


class TrelloAnalyticsService:
    """
    Computes and persists board-level analytics.

    Usage::

        svc = TrelloAnalyticsService(db, ws_manager)
        result = await svc.compute_board_analytics(board)
    """

    def __init__(self, db: AsyncSession, ws_manager: WebSocketManager) -> None:
        self._db = db
        self._ws = ws_manager

    # ── Primary entry point ───────────────────────────────────────────────────

    async def compute_board_analytics(
        self,
        board: TrelloBoard,
        throughput_days: int = 7,
        histogram_buckets: list[float] | None = None,
    ) -> TrelloAnalytics:
        """
        Full analytics pass for one board.

        Steps:
        1. Update cycle_time_hours / lead_time_hours on individual cards.
        2. Detect and flag stalled cards; emit TrelloCardStalledEvent.
        3. Aggregate board-level metrics (avg, p50, p90 cycle time; throughput; WIP).
        4. Build cycle time histogram and movement flow data.
        5. Broadcast TrelloAnalyticsUpdatedEvent to WebSocket clients.
        """
        buckets = histogram_buckets or _DEFAULT_BUCKETS

        # 1 — per-card metrics
        await self._update_card_metrics(board.id)

        # 2 — stall detection
        stalled_events = await self._detect_stalls(board)

        # 3 — aggregate
        completed_cards = await self._load_completed_cards(board.id)
        cycle_times = [c.cycle_time_hours for c in completed_cards if c.cycle_time_hours is not None]
        lead_times  = [c.lead_time_hours  for c in completed_cards if c.lead_time_hours  is not None]

        avg_cycle  = _safe_mean(cycle_times)
        p50_cycle  = _safe_percentile(cycle_times, 50)
        p90_cycle  = _safe_percentile(cycle_times, 90)
        avg_lead   = _safe_mean(lead_times)

        throughput  = await self._compute_throughput(board.id, throughput_days)
        wip_count   = await self._compute_wip(board.id)
        stalled_ids = await self._load_stalled_ids(board.id)

        flow_efficiency: float | None = None
        if avg_cycle is not None and avg_lead is not None and avg_lead > 0:
            flow_efficiency = round((avg_cycle / avg_lead) * 100, 1)

        # 4 — histograms & flow
        cycle_histogram = _build_histogram(cycle_times, buckets, "Cycle Time")
        lead_histogram  = _build_histogram(lead_times,  buckets, "Lead Time")
        movement_flow   = await self._build_movement_flow(board.id)

        # Stalled card details
        blockers = await self._load_blocker_details(board.id)

        analytics = TrelloAnalytics(
            board_id=board.id,
            board_name=board.name,
            computed_at=datetime.now(UTC),
            avg_cycle_time_hours=avg_cycle,
            p50_cycle_time_hours=p50_cycle,
            p90_cycle_time_hours=p90_cycle,
            avg_lead_time_hours=avg_lead,
            throughput_cards=throughput,
            throughput_days=throughput_days,
            current_wip=wip_count,
            flow_efficiency_pct=flow_efficiency,
            stalled_count=len(stalled_ids),
            blockers=blockers,
            cycle_time_histogram=cycle_histogram,
            lead_time_histogram=lead_histogram,
            movement_flow=movement_flow,
        )

        # 5 — emit update event + WebSocket broadcast
        updated_event = TrelloAnalyticsUpdatedEvent(
            board_id=board.id,
            board_name=board.name,
            avg_cycle_time_hours=avg_cycle,
            stalled_count=len(stalled_ids),
            current_wip=wip_count,
        )
        # Broadcast to project WebSocket room
        if board.credential_id:
            board_row = await self._db.scalar(
                select(TrelloBoard).where(TrelloBoard.id == board.id)
            )
            if board_row and board_row.credential:
                await self._ws.broadcast_to_project(
                    board_row.credential.project_id,
                    updated_event.model_dump(),
                )

        # Broadcast stall events
        for stall_evt in stalled_events:
            if board_row and board_row.credential:
                await self._ws.broadcast_to_project(
                    board_row.credential.project_id,
                    stall_evt.model_dump(),
                )

        logger.info(
            "trello_analytics_computed",
            board_id=board.id,
            completed=len(completed_cards),
            avg_cycle_hours=avg_cycle,
            wip=wip_count,
            stalled=len(stalled_ids),
        )
        return analytics

    # ── Cycle time / Lead time ─────────────────────────────────────────────────

    async def _update_card_metrics(self, board_id: int) -> None:
        """
        Compute and write cycle_time_hours + lead_time_hours for every card
        on this board that has the necessary timestamps set.
        """
        # Cycle time: entered_wip_at → entered_done_at
        await self._db.execute(
            update(TrelloCard)
            .where(
                TrelloCard.board_id == board_id,
                TrelloCard.entered_wip_at.is_not(None),
                TrelloCard.entered_done_at.is_not(None),
            )
            .values(
                cycle_time_hours=func.extract(
                    "epoch",
                    TrelloCard.entered_done_at - TrelloCard.entered_wip_at,
                )
                / 3600.0
            )
        )

        # Lead time: trello_created_at → entered_done_at
        await self._db.execute(
            update(TrelloCard)
            .where(
                TrelloCard.board_id == board_id,
                TrelloCard.trello_created_at.is_not(None),
                TrelloCard.entered_done_at.is_not(None),
            )
            .values(
                lead_time_hours=func.extract(
                    "epoch",
                    TrelloCard.entered_done_at - TrelloCard.trello_created_at,
                )
                / 3600.0
            )
        )

        await self._db.flush()

    async def _load_completed_cards(self, board_id: int) -> Sequence[TrelloCard]:
        result = await self._db.execute(
            select(TrelloCard).where(
                TrelloCard.board_id == board_id,
                TrelloCard.entered_done_at.is_not(None),
            )
        )
        return result.scalars().all()

    # ── Throughput ─────────────────────────────────────────────────────────────

    async def _compute_throughput(self, board_id: int, days: int) -> int:
        """Count cards that entered a Done list within the last `days` days."""
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self._db.execute(
            select(func.count(TrelloCard.id)).where(
                TrelloCard.board_id == board_id,
                TrelloCard.entered_done_at >= since,
            )
        )
        return result.scalar_one() or 0

    # ── WIP ────────────────────────────────────────────────────────────────────

    async def _compute_wip(self, board_id: int) -> int:
        """Count open cards currently in a WIP-type list."""
        result = await self._db.execute(
            select(func.count(TrelloCard.id))
            .join(TrelloList, TrelloCard.list_id == TrelloList.id)
            .where(
                TrelloCard.board_id == board_id,
                TrelloCard.is_closed.is_(False),
                TrelloList.list_type == ListType.WIP,
            )
        )
        return result.scalar_one() or 0

    # ── Stall / Blocker detection ─────────────────────────────────────────────

    async def _detect_stalls(self, board: TrelloBoard) -> list[TrelloCardStalledEvent]:
        """
        Find WIP cards that have had no activity for >= L1 threshold.
        Sets is_stalled=True and stalled_since=now (only if not already set).
        Returns TrelloCardStalledEvent for each newly detected stall.
        """
        now = datetime.now(UTC)
        l1 = settings.stall_threshold_l1_hours
        l2 = settings.stall_threshold_l2_hours
        l3 = settings.stall_threshold_l3_hours

        result = await self._db.execute(
            select(TrelloCard, TrelloList)
            .join(TrelloList, TrelloCard.list_id == TrelloList.id)
            .where(
                TrelloCard.board_id == board.id,
                TrelloCard.is_closed.is_(False),
                TrelloList.list_type == ListType.WIP,
                TrelloCard.trello_last_activity.is_not(None),
            )
        )
        rows = result.all()

        events: list[TrelloCardStalledEvent] = []
        for card, lst in rows:
            last_active = card.trello_last_activity.replace(tzinfo=UTC) if card.trello_last_activity.tzinfo is None else card.trello_last_activity
            stalled_hours = (now - last_active).total_seconds() / 3600

            if stalled_hours < l1:
                # Clear stall flag if card has become active again
                if card.is_stalled:
                    await self._db.execute(
                        update(TrelloCard)
                        .where(TrelloCard.id == card.id)
                        .values(is_stalled=False, stalled_since=None)
                    )
                continue

            escalation = 1
            if stalled_hours >= l3:
                escalation = 3
            elif stalled_hours >= l2:
                escalation = 2

            was_stalled = card.is_stalled
            if not was_stalled:
                await self._db.execute(
                    update(TrelloCard)
                    .where(TrelloCard.id == card.id)
                    .values(is_stalled=True, stalled_since=now)
                )
                events.append(
                    TrelloCardStalledEvent(
                        board_id=board.id,
                        board_name=board.name,
                        card_id=card.id,
                        trello_card_id=card.trello_id,
                        card_name=card.name,
                        card_short_id=card.trello_short_id,
                        list_name=lst.name,
                        stalled_hours=round(stalled_hours, 1),
                        escalation_level=escalation,
                        member_ids=card.member_ids or [],
                    )
                )
            else:
                # Already stalled — re-emit escalation if level changed
                existing_hours = (now - card.stalled_since).total_seconds() / 3600 if card.stalled_since else stalled_hours
                prev_level = 1
                if existing_hours >= l3:
                    prev_level = 3
                elif existing_hours >= l2:
                    prev_level = 2

                if escalation > prev_level:
                    events.append(
                        TrelloCardStalledEvent(
                            board_id=board.id,
                            board_name=board.name,
                            card_id=card.id,
                            trello_card_id=card.trello_id,
                            card_name=card.name,
                            card_short_id=card.trello_short_id,
                            list_name=lst.name,
                            stalled_hours=round(stalled_hours, 1),
                            escalation_level=escalation,
                            member_ids=card.member_ids or [],
                        )
                    )

        await self._db.flush()
        return events

    async def _load_stalled_ids(self, board_id: int) -> list[int]:
        result = await self._db.execute(
            select(TrelloCard.id).where(
                TrelloCard.board_id == board_id,
                TrelloCard.is_stalled.is_(True),
            )
        )
        return [r[0] for r in result.all()]

    async def _load_blocker_details(self, board_id: int) -> list[TrelloBlockerRead]:
        result = await self._db.execute(
            select(TrelloCard, TrelloList)
            .join(TrelloList, TrelloCard.list_id == TrelloList.id, isouter=True)
            .where(
                TrelloCard.board_id == board_id,
                TrelloCard.is_stalled.is_(True),
            )
            .order_by(TrelloCard.stalled_since.asc())
        )
        blockers = []
        now = datetime.now(UTC)
        for card, lst in result.all():
            stalled_since = card.stalled_since
            if stalled_since and stalled_since.tzinfo is None:
                stalled_since = stalled_since.replace(tzinfo=UTC)
            stalled_hours = (now - stalled_since).total_seconds() / 3600 if stalled_since else 0.0

            l2 = settings.stall_threshold_l2_hours
            l3 = settings.stall_threshold_l3_hours
            level = 1
            if stalled_hours >= l3:
                level = 3
            elif stalled_hours >= l2:
                level = 2

            blockers.append(
                TrelloBlockerRead(
                    card_id=card.id,
                    trello_card_id=card.trello_id,
                    card_name=card.name,
                    card_short_id=card.trello_short_id,
                    list_name=lst.name if lst else "Unknown",
                    stalled_since=stalled_since,
                    stalled_hours=round(stalled_hours, 1),
                    escalation_level=level,
                    member_ids=card.member_ids or [],
                )
            )
        return blockers

    # ── Movement flow ─────────────────────────────────────────────────────────

    async def _build_movement_flow(self, board_id: int) -> list[CardMovementFlow]:
        """
        Count transitions between (from_list, to_list) pairs for Sankey diagrams.
        Only includes transitions where both endpoints are known.
        """
        result = await self._db.execute(
            select(
                TrelloList.name.label("from_name"),
                # Need a second join alias for the to_list
                func.count(TrelloCardMovement.id).label("count_"),
            )
            .select_from(TrelloCardMovement)
            .join(
                TrelloList,
                TrelloCardMovement.from_list_id == TrelloList.id,
                isouter=True,
            )
            .join(
                TrelloCard,
                TrelloCardMovement.card_id == TrelloCard.id,
            )
            .where(
                TrelloCard.board_id == board_id,
                TrelloCardMovement.from_list_id.is_not(None),
                TrelloCardMovement.to_list_id.is_not(None),
            )
            .group_by(TrelloCardMovement.from_list_id, TrelloCardMovement.to_list_id, TrelloList.name)
        )
        # The query above gives us from_name + count; for a full Sankey we also
        # need to_name.  We load all movements with their list names via a
        # Python-side join to avoid a complex alias setup.
        raw_movements = await self._load_raw_movements(board_id)
        return raw_movements

    async def _load_raw_movements(self, board_id: int) -> list[CardMovementFlow]:
        """
        Load all (from_list_name, to_list_name, count) transitions for a board.
        Uses explicit aliasing of TrelloList for the two FK joins.
        """
        from sqlalchemy.orm import aliased

        FromList = aliased(TrelloList, name="from_list")
        ToList = aliased(TrelloList, name="to_list")

        result = await self._db.execute(
            select(
                FromList.name.label("from_name"),
                ToList.name.label("to_name"),
                func.count(TrelloCardMovement.id).label("transition_count"),
            )
            .select_from(TrelloCardMovement)
            .join(TrelloCard, TrelloCardMovement.card_id == TrelloCard.id)
            .join(FromList, TrelloCardMovement.from_list_id == FromList.id)
            .join(ToList, TrelloCardMovement.to_list_id == ToList.id)
            .where(TrelloCard.board_id == board_id)
            .group_by(FromList.name, ToList.name)
            .order_by(func.count(TrelloCardMovement.id).desc())
        )
        return [
            CardMovementFlow(
                from_list=row.from_name,
                to_list=row.to_name,
                count=row.transition_count,
            )
            for row in result.all()
        ]


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _safe_mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 2) if values else None


def _safe_percentile(values: list[float], pct: int) -> float | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * pct / 100)
    idx = min(idx, len(sorted_vals) - 1)
    return round(sorted_vals[idx], 2)


def _build_histogram(
    values: list[float],
    buckets: list[float],
    label: str,
) -> CycleTimeHistogram:
    """
    Bucket a list of hour-values into a histogram.

    Buckets are defined by upper bounds.  The last bucket is open-ended.
    e.g. buckets=[8, 24, 48] → [<8h, 8-24h, 24-48h, >48h]
    """
    labels: list[str] = []
    counts: list[int] = []

    edges = list(buckets)
    for i, upper in enumerate(edges):
        lower = edges[i - 1] if i > 0 else 0
        labels.append(f"{int(lower)}–{int(upper)}h")
        counts.append(sum(1 for v in values if lower <= v < upper))

    # Overflow bucket
    if edges:
        labels.append(f">{int(edges[-1])}h")
        counts.append(sum(1 for v in values if v >= edges[-1]))

    return CycleTimeHistogram(label=label, bucket_labels=labels, counts=counts)
