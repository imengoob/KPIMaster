"""Validate database schema and demo-data quality.

This script is intentionally strict enough for CI and demo-readiness checks:
it verifies required tables, deterministic seed minimums, duplicate natural
keys, allowed status/value domains, referential integrity, and basic numeric
and date sanity.

Usage:
    cd backend
    python scripts/validate_data_quality.py --profile demo
    python scripts/validate_data_quality.py --profile schema --json-out report.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

# Allow running the script directly from backend/scripts.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402

Profile = Literal["schema", "demo"]


REQUIRED_TABLES = [
    "alembic_version",
    "companies",
    "projects",
    "users",
    "developers",
    "sprints",
    "tickets",
    "blockers",
    "burndown_entries",
    "repository_activity",
    "kpi_snapshots",
    "developer_sprint_kpis",
    "trello_credentials",
    "trello_boards",
    "trello_lists",
    "trello_cards",
    "trello_card_movements",
    "trello_actions",
    "trello_webhooks",
    "trello_app_settings",
    "company_project_access",
    "company_partnerships",
    "engagements",
    "developer_assignments",
    "developer_client_visibility",
    "developer_external_identities",
    "integration_accounts",
    "integration_sync_logs",
    "integration_tasks",
    "integration_comments",
]


@dataclass(frozen=True)
class Check:
    name: str
    sql: str
    kind: Literal["equals", "minimum"]
    expected: int
    profile: Literal["all", "demo"] = "all"


@dataclass
class CheckResult:
    name: str
    status: Literal["PASS", "FAIL"]
    observed: int | None
    expected: str
    details: str = ""


DEMO_MINIMUM_CHECKS = [
    Check("demo has tenant companies", "SELECT COUNT(*) FROM companies", "minimum", 4, "demo"),
    Check("demo has projects", "SELECT COUNT(*) FROM projects", "minimum", 3, "demo"),
    Check("demo has persona users", "SELECT COUNT(*) FROM users", "minimum", 9, "demo"),
    Check("demo has developers", "SELECT COUNT(*) FROM developers", "minimum", 9, "demo"),
    Check("demo has sprints", "SELECT COUNT(*) FROM sprints", "minimum", 6, "demo"),
    Check("demo has tickets", "SELECT COUNT(*) FROM tickets", "minimum", 60, "demo"),
    Check("demo has engagements", "SELECT COUNT(*) FROM engagements", "minimum", 3, "demo"),
    Check("demo has assignments", "SELECT COUNT(*) FROM developer_assignments", "minimum", 9, "demo"),
    Check("demo has Trello boards", "SELECT COUNT(*) FROM trello_boards", "minimum", 3, "demo"),
    Check("demo has Trello cards", "SELECT COUNT(*) FROM trello_cards", "minimum", 30, "demo"),
    Check("demo has blockers", "SELECT COUNT(*) FROM blockers", "minimum", 1, "demo"),
    Check(
        "demo has repository activity",
        "SELECT COUNT(*) FROM repository_activity",
        "minimum",
        20,
        "demo",
    ),
]


INVARIANT_CHECKS = [
    Check(
        "alembic has exactly one current revision row",
        "SELECT COUNT(*) FROM alembic_version",
        "equals",
        1,
    ),
    Check(
        "company slugs are unique",
        """
        SELECT COUNT(*) FROM (
            SELECT slug FROM companies GROUP BY slug HAVING COUNT(*) > 1
        ) duplicates
        """,
        "equals",
        0,
    ),
    Check(
        "project keys are unique",
        """
        SELECT COUNT(*) FROM (
            SELECT key FROM projects GROUP BY key HAVING COUNT(*) > 1
        ) duplicates
        """,
        "equals",
        0,
    ),
    Check(
        "user usernames are unique",
        """
        SELECT COUNT(*) FROM (
            SELECT username FROM users GROUP BY username HAVING COUNT(*) > 1
        ) duplicates
        """,
        "equals",
        0,
    ),
    Check(
        "user emails are unique",
        """
        SELECT COUNT(*) FROM (
            SELECT email FROM users GROUP BY email HAVING COUNT(*) > 1
        ) duplicates
        """,
        "equals",
        0,
    ),
    Check(
        "developer usernames are unique",
        """
        SELECT COUNT(*) FROM (
            SELECT username FROM developers GROUP BY username HAVING COUNT(*) > 1
        ) duplicates
        """,
        "equals",
        0,
    ),
    Check(
        "developer emails are unique",
        """
        SELECT COUNT(*) FROM (
            SELECT email FROM developers GROUP BY email HAVING COUNT(*) > 1
        ) duplicates
        """,
        "equals",
        0,
    ),
    Check(
        "companies have required fields",
        """
        SELECT COUNT(*) FROM companies
        WHERE NULLIF(TRIM(name), '') IS NULL OR NULLIF(TRIM(slug), '') IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "projects have required fields",
        """
        SELECT COUNT(*) FROM projects
        WHERE NULLIF(TRIM(name), '') IS NULL OR NULLIF(TRIM(key), '') IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "users have credentials",
        """
        SELECT COUNT(*) FROM users
        WHERE NULLIF(TRIM(username), '') IS NULL
           OR NULLIF(TRIM(email), '') IS NULL
           OR NULLIF(TRIM(password_hash), '') IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "developers have required identity fields",
        """
        SELECT COUNT(*) FROM developers
        WHERE NULLIF(TRIM(name), '') IS NULL
           OR NULLIF(TRIM(username), '') IS NULL
           OR NULLIF(TRIM(email), '') IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "tickets have titles",
        "SELECT COUNT(*) FROM tickets WHERE NULLIF(TRIM(title), '') IS NULL",
        "equals",
        0,
    ),
    Check(
        "company tenant types are valid",
        """
        SELECT COUNT(*) FROM companies
        WHERE tenant_type NOT IN ('client', 'vendor', 'esn')
        """,
        "equals",
        0,
    ),
    Check(
        "user roles are valid",
        """
        SELECT COUNT(*) FROM users
        WHERE role NOT IN (
            'super_admin',
            'company_admin',
            'company_manager',
            'client_admin',
            'client_exec',
            'client_pm',
            'esn_admin',
            'esn_delivery_manager',
            'developer',
            'auditor_readonly'
        )
        """,
        "equals",
        0,
    ),
    Check(
        "developer roles are present",
        """
        SELECT COUNT(*) FROM developers
        WHERE NULLIF(TRIM(role), '') IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "sprint statuses are valid",
        """
        SELECT COUNT(*) FROM sprints
        WHERE status NOT IN ('planning', 'active', 'completed', 'cancelled')
        """,
        "equals",
        0,
    ),
    Check(
        "ticket statuses are valid",
        """
        SELECT COUNT(*) FROM tickets
        WHERE status NOT IN (
            'backlog',
            'todo',
            'in_progress',
            'in_review',
            'blocked',
            'done',
            'cancelled'
        )
        """,
        "equals",
        0,
    ),
    Check(
        "ticket priorities are valid",
        "SELECT COUNT(*) FROM tickets WHERE priority NOT IN ('low', 'medium', 'high', 'critical')",
        "equals",
        0,
    ),
    Check(
        "ticket types are valid",
        """
        SELECT COUNT(*) FROM tickets
        WHERE ticket_type NOT IN (
            'feature',
            'story',
            'bug',
            'task',
            'epic',
            'refactor',
            'investigation',
            'other'
        )
        """,
        "equals",
        0,
    ),
    Check(
        "engagement statuses are valid",
        """
        SELECT COUNT(*) FROM engagements
        WHERE status NOT IN ('active', 'paused', 'completed', 'cancelled')
        """,
        "equals",
        0,
    ),
    Check(
        "developer assignment statuses are valid",
        """
        SELECT COUNT(*) FROM developer_assignments
        WHERE status NOT IN ('active', 'paused', 'completed', 'cancelled')
        """,
        "equals",
        0,
    ),
    Check(
        "visibility statuses are valid",
        """
        SELECT COUNT(*) FROM developer_client_visibility
        WHERE status NOT IN ('pending_developer_approval', 'approved', 'rejected')
        """,
        "equals",
        0,
    ),
    Check(
        "partnership statuses are valid",
        """
        SELECT COUNT(*) FROM company_partnerships
        WHERE status NOT IN ('pending', 'active', 'rejected')
        """,
        "equals",
        0,
    ),
    Check(
        "integration providers are valid",
        """
        SELECT COUNT(*) FROM integration_accounts
        WHERE provider NOT IN ('trello', 'jira', 'microsoft', 'github')
        """,
        "equals",
        0,
    ),
    Check(
        "integration task providers are valid",
        """
        SELECT COUNT(*) FROM integration_tasks
        WHERE provider NOT IN ('trello', 'jira', 'microsoft', 'github')
        """,
        "equals",
        0,
    ),
    Check(
        "integration comment providers are valid",
        """
        SELECT COUNT(*) FROM integration_comments
        WHERE provider NOT IN ('trello', 'jira', 'microsoft', 'github')
        """,
        "equals",
        0,
    ),
    Check(
        "users reference existing companies",
        """
        SELECT COUNT(*) FROM users u
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE u.company_id IS NOT NULL AND c.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "users reference existing developers",
        """
        SELECT COUNT(*) FROM users u
        LEFT JOIN developers d ON d.id = u.developer_id
        WHERE u.developer_id IS NOT NULL AND d.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "developers reference existing companies",
        """
        SELECT COUNT(*) FROM developers d
        LEFT JOIN companies c ON c.id = d.company_id
        WHERE d.company_id IS NOT NULL AND c.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "sprints reference existing projects",
        """
        SELECT COUNT(*) FROM sprints s
        LEFT JOIN projects p ON p.id = s.project_id
        WHERE p.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "tickets reference existing projects",
        """
        SELECT COUNT(*) FROM tickets t
        LEFT JOIN projects p ON p.id = t.project_id
        WHERE p.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "tickets reference existing sprints",
        """
        SELECT COUNT(*) FROM tickets t
        LEFT JOIN sprints s ON s.id = t.sprint_id
        WHERE t.sprint_id IS NOT NULL AND s.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "tickets reference existing assignees",
        """
        SELECT COUNT(*) FROM tickets t
        LEFT JOIN developers d ON d.id = t.assignee_id
        WHERE t.assignee_id IS NOT NULL AND d.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "tickets reference existing reporters",
        """
        SELECT COUNT(*) FROM tickets t
        LEFT JOIN developers d ON d.id = t.reporter_id
        WHERE t.reporter_id IS NOT NULL AND d.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "engagements reference existing companies and projects",
        """
        SELECT COUNT(*) FROM engagements e
        LEFT JOIN companies client ON client.id = e.client_company_id
        LEFT JOIN companies vendor ON vendor.id = e.vendor_company_id
        LEFT JOIN projects p ON p.id = e.project_id
        WHERE client.id IS NULL OR vendor.id IS NULL OR p.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "developer assignments reference existing rows",
        """
        SELECT COUNT(*) FROM developer_assignments da
        LEFT JOIN developers d ON d.id = da.developer_id
        LEFT JOIN engagements e ON e.id = da.engagement_id
        WHERE d.id IS NULL OR e.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "company project access references existing rows",
        """
        SELECT COUNT(*) FROM company_project_access cpa
        LEFT JOIN companies c ON c.id = cpa.company_id
        LEFT JOIN projects p ON p.id = cpa.project_id
        WHERE c.id IS NULL OR p.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "company partnerships reference existing companies",
        """
        SELECT COUNT(*) FROM company_partnerships cp
        LEFT JOIN companies client ON client.id = cp.client_company_id
        LEFT JOIN companies vendor ON vendor.id = cp.vendor_company_id
        WHERE client.id IS NULL OR vendor.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "integration accounts reference existing users",
        """
        SELECT COUNT(*) FROM integration_accounts ia
        LEFT JOIN users u ON u.id = ia.user_id
        WHERE u.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "integration sync logs reference existing accounts",
        """
        SELECT COUNT(*) FROM integration_sync_logs isl
        LEFT JOIN integration_accounts ia ON ia.id = isl.account_id
        WHERE ia.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "integration tasks reference existing nullable parents",
        """
        SELECT COUNT(*) FROM integration_tasks it
        LEFT JOIN integration_accounts ia ON ia.id = it.account_id
        LEFT JOIN projects p ON p.id = it.project_id
        LEFT JOIN sprints s ON s.id = it.sprint_id
        WHERE ia.id IS NULL
           OR (it.project_id IS NOT NULL AND p.id IS NULL)
           OR (it.sprint_id IS NOT NULL AND s.id IS NULL)
        """,
        "equals",
        0,
    ),
    Check(
        "integration comments reference existing rows",
        """
        SELECT COUNT(*) FROM integration_comments ic
        LEFT JOIN integration_accounts ia ON ia.id = ic.account_id
        LEFT JOIN integration_tasks it ON it.id = ic.task_id
        WHERE ia.id IS NULL OR it.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "developer external identities reference existing rows",
        """
        SELECT COUNT(*) FROM developer_external_identities dei
        LEFT JOIN developers d ON d.id = dei.developer_id
        LEFT JOIN integration_accounts ia ON ia.id = dei.integration_account_id
        WHERE d.id IS NULL
           OR (dei.integration_account_id IS NOT NULL AND ia.id IS NULL)
        """,
        "equals",
        0,
    ),
    Check(
        "blockers reference existing tickets",
        """
        SELECT COUNT(*) FROM blockers b
        LEFT JOIN tickets t ON t.id = b.ticket_id
        WHERE t.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "repository activity references existing rows",
        """
        SELECT COUNT(*) FROM repository_activity ra
        LEFT JOIN tickets t ON t.id = ra.ticket_id
        LEFT JOIN projects p ON p.id = ra.project_id
        WHERE t.id IS NULL OR p.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "kpi snapshots reference existing rows",
        """
        SELECT COUNT(*) FROM kpi_snapshots ks
        LEFT JOIN projects p ON p.id = ks.project_id
        LEFT JOIN sprints s ON s.id = ks.sprint_id
        WHERE p.id IS NULL OR (ks.sprint_id IS NOT NULL AND s.id IS NULL)
        """,
        "equals",
        0,
    ),
    Check(
        "developer sprint kpis reference existing rows",
        """
        SELECT COUNT(*) FROM developer_sprint_kpis dsk
        LEFT JOIN developers d ON d.id = dsk.developer_id
        LEFT JOIN projects p ON p.id = dsk.project_id
        LEFT JOIN sprints s ON s.id = dsk.sprint_id
        WHERE d.id IS NULL
           OR p.id IS NULL
           OR (dsk.sprint_id IS NOT NULL AND s.id IS NULL)
        """,
        "equals",
        0,
    ),
    Check(
        "burndown entries reference existing sprints",
        """
        SELECT COUNT(*) FROM burndown_entries be
        LEFT JOIN sprints s ON s.id = be.sprint_id
        WHERE s.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "trello credentials reference existing projects",
        """
        SELECT COUNT(*) FROM trello_credentials tc
        LEFT JOIN projects p ON p.id = tc.project_id
        WHERE p.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "trello boards reference existing credentials",
        """
        SELECT COUNT(*) FROM trello_boards tb
        LEFT JOIN trello_credentials tc ON tc.id = tb.credential_id
        WHERE tc.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "trello lists reference existing boards",
        """
        SELECT COUNT(*) FROM trello_lists tl
        LEFT JOIN trello_boards tb ON tb.id = tl.board_id
        WHERE tb.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "trello cards reference existing boards and lists",
        """
        SELECT COUNT(*) FROM trello_cards tc
        LEFT JOIN trello_boards tb ON tb.id = tc.board_id
        LEFT JOIN trello_lists tl ON tl.id = tc.list_id
        WHERE tb.id IS NULL OR (tc.list_id IS NOT NULL AND tl.id IS NULL)
        """,
        "equals",
        0,
    ),
    Check(
        "trello card movements reference existing cards and lists",
        """
        SELECT COUNT(*) FROM trello_card_movements tcm
        LEFT JOIN trello_cards tc ON tc.id = tcm.card_id
        LEFT JOIN trello_lists from_list ON from_list.id = tcm.from_list_id
        LEFT JOIN trello_lists to_list ON to_list.id = tcm.to_list_id
        WHERE tc.id IS NULL
           OR (tcm.from_list_id IS NOT NULL AND from_list.id IS NULL)
           OR (tcm.to_list_id IS NOT NULL AND to_list.id IS NULL)
        """,
        "equals",
        0,
    ),
    Check(
        "trello actions reference existing cards",
        """
        SELECT COUNT(*) FROM trello_actions ta
        LEFT JOIN trello_cards tc ON tc.id = ta.card_id
        WHERE ta.card_id IS NOT NULL AND tc.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "trello webhooks reference existing boards",
        """
        SELECT COUNT(*) FROM trello_webhooks tw
        LEFT JOIN trello_boards tb ON tb.id = tw.board_id
        WHERE tb.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "trello app settings reference existing companies",
        """
        SELECT COUNT(*) FROM trello_app_settings tas
        LEFT JOIN companies c ON c.id = tas.company_id
        WHERE tas.company_id IS NOT NULL AND c.id IS NULL
        """,
        "equals",
        0,
    ),
    Check(
        "sprint date ranges are valid",
        "SELECT COUNT(*) FROM sprints WHERE start_date > end_date",
        "equals",
        0,
    ),
    Check(
        "engagement date ranges are valid",
        """
        SELECT COUNT(*) FROM engagements
        WHERE starts_on IS NOT NULL AND ends_on IS NOT NULL AND starts_on > ends_on
        """,
        "equals",
        0,
    ),
    Check(
        "developer assignment date ranges are valid",
        """
        SELECT COUNT(*) FROM developer_assignments
        WHERE end_date IS NOT NULL AND start_date > end_date
        """,
        "equals",
        0,
    ),
    Check(
        "sprint point totals are non-negative",
        """
        SELECT COUNT(*) FROM sprints
        WHERE committed_points < 0 OR completed_points < 0 OR velocity < 0
        """,
        "equals",
        0,
    ),
    Check(
        "ticket effort values are sane",
        """
        SELECT COUNT(*) FROM tickets
        WHERE estimated_hours < 0
           OR actual_hours < 0
           OR story_points < 0
           OR quality_score < 0
           OR quality_score > 100
        """,
        "equals",
        0,
    ),
    Check(
        "burndown values are non-negative",
        """
        SELECT COUNT(*) FROM burndown_entries
        WHERE remaining_points < 0
           OR completed_points < 0
           OR ideal_remaining < 0
           OR cumulative_completed < 0
        """,
        "equals",
        0,
    ),
    Check(
        "kpi snapshot values are sane",
        """
        SELECT COUNT(*) FROM kpi_snapshots
        WHERE cycle_time_hours < 0
           OR lead_time_hours < 0
           OR velocity < 0
           OR completion_rate < 0
           OR estimation_accuracy < 0
           OR throughput < 0
           OR bug_rate < 0
        """,
        "equals",
        0,
    ),
    Check(
        "developer sprint kpi values are sane",
        """
        SELECT COUNT(*) FROM developer_sprint_kpis
        WHERE completion_rate < 0
           OR avg_cycle_time_hours < 0
           OR estimation_accuracy < 0
           OR tickets_total < 0
           OR tickets_done < 0
           OR story_points_completed < 0
           OR story_points_total < 0
           OR blocker_rate < 0
           OR avg_blocker_age_hours < 0
           OR blocker_count < 0
           OR question_response_time_hours < 0
           OR unanswered_question_rate < 0
        """,
        "equals",
        0,
    ),
    Check(
        "trello analytics values are sane",
        """
        SELECT COUNT(*) FROM trello_cards
        WHERE cycle_time_hours < 0
           OR lead_time_hours < 0
        """,
        "equals",
        0,
    ),
    Check(
        "trello webhook counters are sane",
        "SELECT COUNT(*) FROM trello_webhooks WHERE events_received < 0",
        "equals",
        0,
    ),
    Check(
        "developer assignment allocation is sane",
        """
        SELECT COUNT(*) FROM developer_assignments
        WHERE allocation_percentage < 1 OR allocation_percentage > 100
        """,
        "equals",
        0,
    ),
    Check(
        "blocker escalation values are sane",
        """
        SELECT COUNT(*) FROM blockers
        WHERE stall_hours < 0 OR escalation_level NOT BETWEEN 1 AND 3
        """,
        "equals",
        0,
    ),
    Check(
        "repository activity counts are non-negative",
        """
        SELECT COUNT(*) FROM repository_activity
        WHERE commit_count < 0 OR pr_count < 0
        """,
        "equals",
        0,
    ),
]


async def _existing_tables(conn: AsyncConnection) -> set[str]:
    result = await conn.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
    )
    return {str(row[0]) for row in result.fetchall()}


async def _run_check(conn: AsyncConnection, check: Check) -> CheckResult:
    observed = int(await conn.scalar(text(check.sql)) or 0)
    if check.kind == "equals":
        ok = observed == check.expected
        expected = f"= {check.expected}"
    else:
        ok = observed >= check.expected
        expected = f">= {check.expected}"
    return CheckResult(
        name=check.name,
        status="PASS" if ok else "FAIL",
        observed=observed,
        expected=expected,
    )


def _table_results(existing: set[str]) -> list[CheckResult]:
    results: list[CheckResult] = []
    for table in REQUIRED_TABLES:
        ok = table in existing
        results.append(
            CheckResult(
                name=f"required table exists: {table}",
                status="PASS" if ok else "FAIL",
                observed=1 if ok else 0,
                expected="= 1",
            )
        )
    return results


def _print_results(results: list[CheckResult]) -> None:
    for result in results:
        observed = "ERROR" if result.observed is None else str(result.observed)
        print(f"{result.status:4} {result.name} ({observed} {result.expected})")
        if result.details:
            print(f"     {result.details}")

    failed = sum(1 for result in results if result.status == "FAIL")
    print(f"\nData quality summary: {len(results) - failed} passed, {failed} failed")


async def validate(profile: Profile) -> list[CheckResult]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            existing = await _existing_tables(conn)
            results = _table_results(existing)
            if any(result.status == "FAIL" for result in results):
                return results

            checks = [
                *INVARIANT_CHECKS,
                *(DEMO_MINIMUM_CHECKS if profile == "demo" else []),
            ]
            for check in checks:
                if check.profile == "demo" and profile != "demo":
                    continue
                try:
                    results.append(await _run_check(conn, check))
                except Exception as exc:  # noqa: BLE001 - surface exact failing check in CI.
                    results.append(
                        CheckResult(
                            name=check.name,
                            status="FAIL",
                            observed=None,
                            expected=(
                                f"= {check.expected}"
                                if check.kind == "equals"
                                else f">= {check.expected}"
                            ),
                            details=f"{type(exc).__name__}: {exc}",
                        )
                    )
            return results
    finally:
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("schema", "demo"),
        default="demo",
        help="schema checks migration shape; demo also enforces seeded data minimums",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="optional path for a machine-readable validation report",
    )
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    results = await validate(args.profile)
    _print_results(results)

    if args.json_out:
        args.json_out.write_text(
            json.dumps([asdict(result) for result in results], indent=2),
            encoding="utf-8",
        )

    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
