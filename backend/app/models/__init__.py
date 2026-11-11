"""
Import all models here so Alembic's env.py finds them when it imports Base.
Order matters only insofar as FK references must be defined before use —
SQLAlchemy handles this via string-based forward refs, so alphabetical is fine.
"""
from app.models.base import Base, TimestampMixin
from app.models.action_item import ActionEvent, ActionItem
from app.models.blocker import Blocker
from app.models.burndown_entry import BurndownEntry
from app.models.company import Company, CompanyProjectAccess
from app.models.developer import Developer
from app.models.developer_external_identity import DeveloperExternalIdentity
from app.models.engagement import DeveloperAssignment, Engagement
from app.models.kpi_snapshot import KPISnapshot
from app.models.developer_sprint_kpi import DeveloperSprintKPI
from app.models.project import Project
from app.models.repository_activity import RepositoryActivity
from app.models.sprint import Sprint
from app.models.ticket import Ticket
from app.models.user import User

# ── Trello integration models ─────────────────────────────────────────────────
# Import order follows FK dependency: credential → board → list/webhook → card → action/movement
from app.models.trello_credential import TrelloCredential
from app.models.trello_board import TrelloBoard
from app.models.trello_list import ListType, TrelloList
from app.models.trello_webhook import TrelloWebhook
from app.models.trello_card import TrelloCard, TrelloCardMovement
from app.models.trello_action import TrelloAction, TRACKED_ACTION_TYPES
from app.models.trello_app_settings import TrelloAppSettings

# ── Multi-provider integration models ─────────────────────────────────────────
from app.models.integration_account import IntegrationAccount
from app.models.integration_sync_log import IntegrationSyncLog, SyncType, SyncStatus
from app.models.integration_task import IntegrationComment, IntegrationTask

__all__ = [
    "Base",
    "TimestampMixin",
    "ActionItem",
    "ActionEvent",
    "Project",
    "Sprint",
    "Developer",
    "DeveloperExternalIdentity",
    "Engagement",
    "DeveloperAssignment",
    "Company",
    "CompanyProjectAccess",
    "Ticket",
    "User",
    "Blocker",
    "RepositoryActivity",
    "KPISnapshot",
    "DeveloperSprintKPI",
    "BurndownEntry",
    # Trello
    "TrelloCredential",
    "TrelloBoard",
    "ListType",
    "TrelloList",
    "TrelloWebhook",
    "TrelloCard",
    "TrelloCardMovement",
    "TrelloAction",
    "TRACKED_ACTION_TYPES",
    "TrelloAppSettings",
    # Integration
    "IntegrationAccount",
    "IntegrationSyncLog",
    "IntegrationTask",
    "IntegrationComment",
    "SyncType",
    "SyncStatus",
]
