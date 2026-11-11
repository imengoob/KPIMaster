from collections import defaultdict
from datetime import UTC, datetime, timedelta
import statistics

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trello_action import TrelloAction
from app.models.trello_card import TrelloCard
from app.models.trello_board import TrelloBoard
from app.models.trello_credential import TrelloCredential
from app.models.developer import Developer
from app.schemas.responsiveness import ResponsivenessMetrics, DeveloperResponsivenessRow, ResponsivenessTrendPoint
from app.api.authz import member_numeric_id


class ResponsivenessAnalyticsService:
    def __init__(self, session: AsyncSession):
        self._db = session

    async def compute_responsiveness_metrics(
        self,
        project_id: int,
        allowed_developer_ids: set[int] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        provider: str | None = None,
        sla_hours: float = 24.0,
    ) -> ResponsivenessMetrics:
        if provider is not None and provider != "trello":
            return self._empty_result(project_id)

        # Load developers
        dev_stmt = select(Developer)
        if allowed_developer_ids is not None:
            if not allowed_developer_ids:
                # No access to any developers
                return self._empty_result(project_id)
            valid_ids = {d for d in allowed_developer_ids if d <= 2147483647}
            if not valid_ids:
                return self._empty_result(project_id)
            dev_stmt = dev_stmt.where(Developer.id.in_(valid_ids))
        
        devs = list((await self._db.execute(dev_stmt)).scalars().all())
        if not devs:
            return self._empty_result(project_id)
            
        dev_by_id = {d.id: d for d in devs}
        dev_ids_by_trello_numeric = {}
        for d in devs:
            tnum = member_numeric_id(d.trello_member_id)
            if tnum:
                dev_ids_by_trello_numeric[tnum] = d.id
                
        # Find project board
        board_result = await self._db.execute(
            select(TrelloBoard.id)
            .join(TrelloCredential, TrelloBoard.credential_id == TrelloCredential.id)
            .where(TrelloCredential.project_id == project_id, TrelloCredential.is_active.is_(True))
            .limit(1)
        )
        board_id = board_result.scalar_one_or_none()
        if not board_id:
            return self._empty_result(project_id)

        # Base conditions for actions and cards
        # We only care about cards belonging to this board.
        now = datetime.now(UTC)
        
        # Load all cards
        cards_result = await self._db.execute(
            select(TrelloCard.id, TrelloCard.trello_created_at, TrelloCard.is_closed)
            .where(TrelloCard.board_id == board_id)
        )
        cards = {row.id: {"created_at": _tz(row.trello_created_at), "is_closed": row.is_closed} for row in cards_result.all()}
        card_ids = list(cards.keys())
        
        if not card_ids:
            return self._empty_result(project_id)

        # Load all developer actions on these cards
        # We consider any action type. Comment is "commentCard"
        actions_stmt = (
            select(
                TrelloAction.card_id, 
                TrelloAction.action_type, 
                TrelloAction.action_date, 
                TrelloAction.trello_member_id,
                TrelloAction.member_name
            )
            .where(TrelloAction.card_id.in_(card_ids), TrelloAction.trello_member_id.is_not(None))
            .order_by(TrelloAction.action_date.asc())
        )
        
        if start_date:
            actions_stmt = actions_stmt.where(TrelloAction.action_date >= start_date)
        if end_date:
            actions_stmt = actions_stmt.where(TrelloAction.action_date <= end_date)
            
        actions_result = await self._db.execute(actions_stmt)
        
        # Aggregation structures
        dev_stats = {}
        dev_names = {}
        dev_trello_ids = {}
        
        for d in devs:
            # We don't prepopulate dev_stats here anymore to only include developers
            # who generated data on the Trello boards.
            dev_names[d.id] = d.name
            dev_trello_ids[d.id] = d.trello_member_id
        
        card_first_reaction_by_dev = defaultdict(dict)
        card_first_response_by_dev = defaultdict(dict)
        last_action_by_dev = {}
        
        for row in actions_result.all():
            card_id = row.card_id
            atype = row.action_type
            adate = _tz(row.action_date)
            tid = row.trello_member_id
            mname = row.member_name or str(tid)[:8]
            
            tnum = member_numeric_id(tid)
            if not tnum:
                continue
                
            # Allow virtual Trello members if they are within RBAC allowed IDs or if no explicit allow-list is set
            dev_id = dev_ids_by_trello_numeric.get(tnum)
            if dev_id is None:
                if allowed_developer_ids is not None and tnum not in allowed_developer_ids:
                    continue
                dev_id = tnum
            
            if dev_id not in dev_stats:
                if dev_id in dev_by_id:
                    dev_names[dev_id] = dev_by_id[dev_id].name
                    dev_trello_ids[dev_id] = dev_by_id[dev_id].trello_member_id
                else:
                    dev_names[dev_id] = mname
                    dev_trello_ids[dev_id] = tid
                
                dev_stats[dev_id] = {
                    "comments": 0,
                    "reactions": 0,
                    "first_reactions": [],
                    "first_responses": [],
                    "last_active": None,
                    "sla_breaches": 0,
                }

            card_meta = cards.get(card_id)
            if not card_meta or not card_meta["created_at"]:
                continue
                
            cdate = card_meta["created_at"]
            stats = dev_stats[dev_id]
            
            # Record last action overall for the dev
            if stats["last_active"] is None or adate > stats["last_active"]:
                stats["last_active"] = adate
                
            stats["reactions"] += 1
            if atype == "commentCard":
                stats["comments"] += 1
                
            # First reaction delta
            if card_id not in card_first_reaction_by_dev[dev_id]:
                if adate >= cdate:
                    delta_hours = (adate - cdate).total_seconds() / 3600.0
                    card_first_reaction_by_dev[dev_id][card_id] = delta_hours
                    stats["first_reactions"].append(delta_hours)
                    
            # First response (comment) delta
            if atype == "commentCard" and card_id not in card_first_response_by_dev[dev_id]:
                if adate >= cdate:
                    delta_hours = (adate - cdate).total_seconds() / 3600.0
                    card_first_response_by_dev[dev_id][card_id] = delta_hours
                    stats["first_responses"].append(delta_hours)
        
        rows = []
        global_reactions = []
        global_responses = []
        total_comments = 0
        total_reactions = 0
        total_breaches = 0
        active_count = 0
        dormant_count = 0
        
        for dev_id, stats in dev_stats.items():
            c_count = stats["comments"]
            r_count = stats["reactions"]
            
            total_comments += c_count
            total_reactions += r_count
            
            # Inactivity duration
            inactivity = None
            if stats["last_active"]:
                inactivity_hrs = (now - stats["last_active"]).total_seconds() / 3600.0
                inactivity = max(0.0, round(inactivity_hrs, 1))
            
            # Determine SLAs (very simplified: if inactivity > sla_hours)
            breaches = 0
            if inactivity is not None and inactivity > sla_hours:
                breaches = 1
                total_breaches += 1
                
            if r_count > 0:
                active_count += 1
            else:
                dormant_count += 1
                
            avg_frs = None
            if stats["first_reactions"]:
                avg_frs = statistics.mean(stats["first_reactions"])
                global_reactions.extend(stats["first_reactions"])
                
            avg_frp = None
            if stats["first_responses"]:
                avg_frp = statistics.mean(stats["first_responses"])
                global_responses.extend(stats["first_responses"])
                
            rows.append(
                DeveloperResponsivenessRow(
                    developer_id=dev_id,
                    trello_member_id=dev_trello_ids[dev_id],
                    developer_name=dev_names[dev_id],
                    total_comments=c_count,
                    total_reactions=r_count,
                    avg_first_reaction_hours=round(avg_frs, 2) if avg_frs else None,
                    avg_first_response_hours=round(avg_frp, 2) if avg_frp else None,
                    inactivity_duration_hours=inactivity,
                    sla_breaching_tickets=breaches,
                )
            )
            
        g_avg_reac = statistics.mean(global_reactions) if global_reactions else None
        g_avg_resp = statistics.mean(global_responses) if global_responses else None
        
        return ResponsivenessMetrics(
            project_id=project_id,
            company_id=None,
            global_avg_reaction_hours=round(g_avg_reac, 2) if g_avg_reac else None,
            global_avg_response_hours=round(g_avg_resp, 2) if g_avg_resp else None,
            total_developer_comments=total_comments,
            total_developer_reactions=total_reactions,
            active_developers=active_count,
            dormant_developers=dormant_count,
            total_sla_breaches=total_breaches,
            trend=[],
            developers=sorted(rows, key=lambda x: x.developer_name)
        )
        
    def _empty_result(self, project_id: int | None) -> ResponsivenessMetrics:
        return ResponsivenessMetrics(
            project_id=project_id,
            company_id=None,
            global_avg_reaction_hours=None,
            global_avg_response_hours=None,
            total_developer_comments=0,
            total_developer_reactions=0,
            active_developers=0,
            dormant_developers=0,
            total_sla_breaches=0,
            trend=[],
            developers=[]
        )

def _tz(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
