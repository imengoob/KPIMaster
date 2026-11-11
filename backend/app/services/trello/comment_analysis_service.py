from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trello_action import TrelloAction
from app.models.trello_board import TrelloBoard
from app.models.trello_card import TrelloCard
from app.models.trello_credential import TrelloCredential
from app.schemas.trello import (
    ProjectCommentMetricsRead,
    TicketCommentInsightRead,
    TrelloCommentRead,
)

_MENTION_RE = re.compile(r"@([A-Za-z0-9_.-]+)")
_URL_RE = re.compile(r"https?://[^\s>]+", re.IGNORECASE)
_BLOCKER_KEYWORDS = (
    "blocked",
    "waiting for",
    "dependency",
    "can't proceed",
    "cannot continue",
    "issue with",
    "error",
    "need access",
    "stuck",
    "not responding",
)
_QUESTION_KEYWORDS = (
    "?",
    "should",
    "can you clarify",
    "do we",
    "is this expected",
    "which",
    "what should",
)
_DECISION_KEYWORDS = (
    "we agreed",
    "decided",
    "decision",
    "let's move",
    "we will",
    "agreed to",
)
_REVIEW_KEYWORDS = (
    "please refactor",
    "feedback",
    "review",
    "before merging",
    "nit:",
    "suggestion",
)
_PROGRESS_KEYWORDS = (
    "finished",
    "done",
    "working on",
    "implemented",
    "completed",
    "progress",
    "merged",
)
_NEGATIVE_KEYWORDS = (
    "blocked",
    "issue",
    "error",
    "stuck",
    "problem",
    "frustrating",
    "delay",
    "cannot",
    "can't",
)
_POSITIVE_KEYWORDS = (
    "done",
    "completed",
    "fixed",
    "resolved",
    "merged",
    "finished",
    "great",
)
_CLARIFICATION_KEYWORDS = (
    "requirement",
    "scope",
    "clarify",
    "unclear",
    "confused",
    "missing details",
    "missing requirement",
)


@dataclass
class _CommentRecord:
    action_id: str
    author: str | None
    author_member_id: str | None
    timestamp: datetime
    content: str
    mentioned_users: list[str]
    attachments_or_links: list[str]
    classification: str
    sentiment: str
    blocker_signals: list[str]
    response_time_hours: float | None = None
    unanswered_for_hours: float | None = None


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class TrelloCommentAnalysisService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def analyze_project(self, project_id: int) -> ProjectCommentMetricsRead:
        board = await self._load_primary_board(project_id)
        if board is None:
            raise ValueError("No active Trello board found for this project.")

        rows = await self._session.execute(
            select(TrelloCard)
            .where(TrelloCard.board_id == board.id)
            .order_by(TrelloCard.trello_short_id.asc())
        )
        cards = rows.scalars().all()

        ticket_insights = []
        for card in cards:
            insight = await self.analyze_ticket(project_id=project_id, ticket_id=card.id)
            ticket_insights.append(insight)

        response_times = [
            comment.response_time_hours
            for ticket in ticket_insights
            for comment in ticket.comments
            if comment.response_time_hours is not None
        ]

        blocker_comments = sum(ticket.blocker_comment_count for ticket in ticket_insights)
        unanswered_questions = sum(
            1
            for ticket in ticket_insights
            for comment in ticket.comments
            if comment.classification == "Question / Clarification"
            and comment.unanswered_for_hours is not None
            and comment.unanswered_for_hours >= 24
        )
        ignored_blockers = sum(
            1
            for ticket in ticket_insights
            for comment in ticket.comments
            if comment.classification == "Blocker / Issue"
            and comment.unanswered_for_hours is not None
            and comment.unanswered_for_hours >= 24
        )
        blocker_authors = Counter(
            comment.author or "Unknown"
            for ticket in ticket_insights
            for comment in ticket.comments
            if comment.classification == "Blocker / Issue"
        )
        most_active = sorted(ticket_insights, key=lambda item: item.comment_count, reverse=True)[:5]

        summary_lines = [
            f"{blocker_comments} blocker-related comments detected",
            f"{unanswered_questions} questions unanswered for more than 24h",
            (
                f"Average comment response time: "
                f"{round(sum(response_times) / len(response_times), 2)} hours"
                if response_times
                else "Average comment response time: N/A"
            ),
        ]
        if most_active:
            summary_lines.append(f"Most discussed ticket: {most_active[0].ticket_title}")

        return ProjectCommentMetricsRead(
            project_id=project_id,
            board_id=board.id,
            board_name=board.name,
            tickets_analyzed=len(ticket_insights),
            blocker_comments=blocker_comments,
            unanswered_questions_over_24h=unanswered_questions,
            ignored_blockers_over_24h=ignored_blockers,
            average_response_time_hours=(
                round(sum(response_times) / len(response_times), 2) if response_times else None
            ),
            unresolved_discussion_tickets=sum(1 for ticket in ticket_insights if ticket.unresolved_discussion_count > 0),
            most_active_discussion_tickets=[
                {"ticket_id": item.ticket_id, "ticket_title": item.ticket_title, "comment_count": item.comment_count}
                for item in most_active
            ],
            developers_reporting_blockers=[
                {"author": author, "count": count}
                for author, count in blocker_authors.most_common(5)
            ],
            comment_insights_summary=summary_lines,
            tickets=ticket_insights,
        )

    async def analyze_ticket(self, project_id: int, ticket_id: int) -> TicketCommentInsightRead:
        board = await self._load_primary_board(project_id)
        if board is None:
            raise ValueError("No active Trello board found for this project.")

        card = await self._session.get(TrelloCard, ticket_id)
        if not card or card.board_id != board.id:
            raise ValueError("Ticket not found on the project's active Trello board.")

        rows = await self._session.execute(
            select(TrelloAction)
            .where(TrelloAction.card_id == ticket_id, TrelloAction.action_type == "commentCard")
            .order_by(TrelloAction.action_date.asc())
        )
        actions = rows.scalars().all()

        comments = [self._to_comment(action) for action in actions]
        self._annotate_responses(comments)

        blocker_comments = [comment for comment in comments if comment.classification == "Blocker / Issue"]
        unresolved = [
            comment
            for comment in comments
            if comment.unanswered_for_hours is not None and comment.unanswered_for_hours >= 24
        ]
        clarification_issues = [
            comment
            for comment in comments
            if comment.classification == "Question / Clarification"
            and comment.unanswered_for_hours is not None
            and comment.unanswered_for_hours >= 24
        ]
        response_times = [comment.response_time_hours for comment in comments if comment.response_time_hours is not None]
        negative_count = sum(1 for comment in comments if comment.sentiment == "Negative")
        repeated_negative = negative_count >= 2

        communication_issues: list[str] = []
        if clarification_issues:
            communication_issues.append("Questions are waiting too long for a response.")
        if len(comments) > 10:
            communication_issues.append("Discussion thread is long and may need a clear owner or decision.")
        if any(any(keyword in comment.content.lower() for keyword in _CLARIFICATION_KEYWORDS) for comment in comments):
            communication_issues.append("Comments suggest missing requirements or scope confusion.")
        if repeated_negative:
            communication_issues.append("Repeated negative tone detected in the discussion.")

        potentially_blocked = bool(
            blocker_comments
            or any(comment.unanswered_for_hours and comment.unanswered_for_hours >= 24 for comment in blocker_comments)
        )
        needs_clarification = bool(communication_issues)

        detected_blockers = list({
            signal
            for comment in blocker_comments
            for signal in comment.blocker_signals
        })

        recommended_actions: list[str] = []
        if potentially_blocked:
            recommended_actions.append("Check the blocker owner and confirm the next unblock step today.")
        if clarification_issues:
            recommended_actions.append("Answer open questions and capture the decision directly on the ticket.")
        if len(comments) > 10:
            recommended_actions.append("Summarize the discussion and reduce further back-and-forth.")
        if repeated_negative:
            recommended_actions.append("Have the lead review the thread for escalation risk.")
        if not recommended_actions:
            recommended_actions.append("No immediate action needed; continue monitoring the discussion.")

        ai_summary = self._build_summary(card.name, comments, potentially_blocked, needs_clarification)

        return TicketCommentInsightRead(
            ticket_id=card.id,
            ticket_title=card.name,
            ticket_short_id=card.trello_short_id,
            board_id=board.id,
            comment_count=len(comments),
            blocker_comment_count=len(blocker_comments),
            unresolved_discussion_count=len(unresolved),
            average_response_time_hours=(
                round(sum(response_times) / len(response_times), 2) if response_times else None
            ),
            potentially_blocked=potentially_blocked,
            needs_clarification=needs_clarification,
            repeated_negative_sentiment=repeated_negative,
            communication_issues=communication_issues,
            detected_blockers=detected_blockers,
            recommended_actions=recommended_actions,
            ai_summary=ai_summary,
            comments=[
                TrelloCommentRead(
                    action_id=comment.action_id,
                    author=comment.author,
                    author_member_id=comment.author_member_id,
                    timestamp=comment.timestamp,
                    content=comment.content,
                    mentioned_users=comment.mentioned_users,
                    attachments_or_links=comment.attachments_or_links,
                    classification=comment.classification,
                    sentiment=comment.sentiment,
                    blocker_signals=comment.blocker_signals,
                    response_time_hours=comment.response_time_hours,
                    unanswered_for_hours=comment.unanswered_for_hours,
                )
                for comment in comments
            ],
        )

    async def _load_primary_board(self, project_id: int) -> TrelloBoard | None:
        rows = await self._session.execute(
            select(TrelloBoard)
            .join(TrelloCredential, TrelloBoard.credential_id == TrelloCredential.id)
            .where(TrelloCredential.project_id == project_id, TrelloCredential.is_active.is_(True))
            .order_by(TrelloBoard.last_synced_at.desc().nullslast(), TrelloBoard.id.asc())
        )
        return rows.scalars().first()

    def _to_comment(self, action: TrelloAction) -> _CommentRecord:
        text = str((action.data or {}).get("text") or "").strip()
        lowered = text.lower()
        links = list(dict.fromkeys(_URL_RE.findall(text)))
        mentions = list(dict.fromkeys(_MENTION_RE.findall(text)))
        blocker_signals = [keyword for keyword in _BLOCKER_KEYWORDS if keyword in lowered]

        return _CommentRecord(
            action_id=action.trello_action_id,
            author=action.member_name,
            author_member_id=action.trello_member_id,
            timestamp=action.action_date,
            content=text,
            mentioned_users=mentions,
            attachments_or_links=links,
            classification=self._classify_comment(lowered),
            sentiment=self._classify_sentiment(lowered),
            blocker_signals=blocker_signals,
        )

    def _classify_comment(self, lowered: str) -> str:
        if any(keyword in lowered for keyword in _BLOCKER_KEYWORDS):
            return "Blocker / Issue"
        if any(keyword in lowered for keyword in _QUESTION_KEYWORDS):
            return "Question / Clarification"
        if any(keyword in lowered for keyword in _DECISION_KEYWORDS):
            return "Decision / Agreement"
        if any(keyword in lowered for keyword in _REVIEW_KEYWORDS):
            return "Review / Feedback"
        if any(keyword in lowered for keyword in _PROGRESS_KEYWORDS):
            return "Progress Update"
        return "No Action / Informational"

    def _classify_sentiment(self, lowered: str) -> str:
        positive_hits = sum(1 for keyword in _POSITIVE_KEYWORDS if keyword in lowered)
        negative_hits = sum(1 for keyword in _NEGATIVE_KEYWORDS if keyword in lowered)
        if negative_hits > positive_hits and negative_hits > 0:
            return "Negative"
        if positive_hits > negative_hits and positive_hits > 0:
            return "Positive"
        return "Neutral"

    def _annotate_responses(self, comments: list[_CommentRecord]) -> None:
        now = datetime.now(UTC)
        for index, comment in enumerate(comments):
            if comment.classification not in {"Question / Clarification", "Blocker / Issue"}:
                continue

            responder = next(
                (
                    later
                    for later in comments[index + 1 :]
                    if later.author_member_id and later.author_member_id != comment.author_member_id
                ),
                None,
            )
            if responder:
                comment.response_time_hours = round(
                    (_as_utc(responder.timestamp) - _as_utc(comment.timestamp)).total_seconds() / 3600,
                    2,
                )
            else:
                comment.unanswered_for_hours = round(
                    (now - _as_utc(comment.timestamp)).total_seconds() / 3600,
                    2,
                )

    def _build_summary(
        self,
        ticket_title: str,
        comments: list[_CommentRecord],
        potentially_blocked: bool,
        needs_clarification: bool,
    ) -> str:
        if not comments:
            return f"No Trello comments were found for '{ticket_title}'."

        latest = comments[-1]
        if potentially_blocked:
            return (
                f"This ticket discussion indicates a likely blocker around "
                f"{', '.join(comments[-1].blocker_signals or ['delivery risk'])}, which may delay progress."
            )
        if needs_clarification:
            return (
                f"This ticket discussion shows unresolved questions or scope ambiguity that should be clarified "
                f"before work continues."
            )
        if latest.classification == "Progress Update":
            return f"This ticket discussion shows steady progress, with the latest update focused on active implementation."
        return f"This ticket discussion is active but currently does not show a strong blocker or escalation signal."
