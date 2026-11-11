from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ──────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production", "testing"] = "development"
    app_name: str = "KPIMaster"
    app_version: str = "1.0.0"
    app_debug: bool = False
    secret_key: str = "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJEaW5vQ2hpZXNhLmdpdGh1Yi5pbyIsInN1YiI6ImFubmEiLCJhdWQiOiJuYWltaXNoIiwiaWF0IjoxNjczNzA4MTExLCJleHAiOjE2NzM3MDg3MTEsInByb3BYIjpmYWxzZX0.G6sZ8XITlz0kFNhDZ9IsTn_A07ZuqURqRntWsDxgXRIcRdXhT0PzqGkSKLhCck8u-QrUFRXYxV1z3iXVQol1Aluz91szjs4cwd2IMWVgOoIPGqHpl4Npp42GUKgTGaVFA5378rkQAX3pd6OXxPZoU3bm1M2eGWXoRtLxZ2iZ6JTQtPjnCqk4rx_6-loqsbOCuiNuCuDFGr3kHjb4-YFchaRc6UDU2ZBsbDQLhZrw9vU3L4BnWqYQHwZBWjepr6pExCgoFR1nupCsbqZwx_5q5aRVyKGC-Xe2BVoX3Gx-iK5Pu719PvzWtNVZs1xUygTlHtuWbWDVwoEZGr3q_7KGow"
    basic_auth_enabled: bool = False
    basic_auAth_username: str | None = None
    basic_auth_password: str | None = None
    auth_enabled: bool = True
    auth_jwt_secret: str = "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJEaW5vQ2hpZXNhLmdpdGh1Yi5pbyIsInN1YiI6ImFubmEiLCJhdWQiOiJuYWltaXNoIiwiaWF0IjoxNjczNzA4MTExLCJleHAiOjE2NzM3MDg3MTEsInByb3BYIjpmYWxzZX0.G6sZ8XITlz0kFNhDZ9IsTn_A07ZuqURqRntWsDxgXRIcRdXhT0PzqGkSKLhCck8u-QrUFRXYxV1z3iXVQol1Aluz91szjs4cwd2IMWVgOoIPGqHpl4Npp42GUKgTGaVFA5378rkQAX3pd6OXxPZoU3bm1M2eGWXoRtLxZ2iZ6JTQtPjnCqk4rx_6-loqsbOCuiNuCuDFGr3kHjb4-YFchaRc6UDU2ZBsbDQLhZrw9vU3L4BnWqYQHwZBWjepr6pExCgoFR1nupCsbqZwx_5q5aRVyKGC-Xe2BVoX3Gx-iK5Pu719PvzWtNVZs1xUygTlHtuWbWDVwoEZGr3q_7KGow"
    auth_jwt_algorithm: str = "HS256"
    auth_access_token_expire_minutes: int = 120
    auth_bootstrap_username: str | None = None
    auth_bootstrap_email: str | None = None
    auth_bootstrap_password: str | None = None

    # ─── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://sprintpulse:sprintpulse@localhost:5432/sprintpulse"
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_pool_recycle: int = 3600

    # ─── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_celery_backend: str = "redis://localhost:6379/1"
    redis_pubsub_channel_prefix: str = "sprintpulse"

    # ─── Celery ───────────────────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ─── Notification Channels ────────────────────────────────────────────────
    slack_webhook_url: str | None = None
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_user: str = "noreply@example.com"
    smtp_password: str = ""
    smtp_from: str = "KPIMaster <noreply@example.com>"

    # ─── Blocker Thresholds ───────────────────────────────────────────────────
    stall_threshold_l1_hours: int = 24
    stall_threshold_l2_hours: int = 48
    stall_threshold_l3_hours: int = 72

    # ─── Trello Integration ───────────────────────────────────────────────────
    # Base URL used when constructing webhook callback URLs.
    # Must be publicly reachable by Trello (use ngrok in development).
    trello_webhook_base_url: str = "https://example.com"
    trello_api_key: str | None = None
    trello_api_token: str | None = None
    trello_default_board_ids: str | None = None
    # Max requests per 10-second window (Trello hard-limits to 300)
    trello_rate_limit_requests: int = 280
    trello_rate_limit_window_seconds: int = 10
    # Cards in a WIP list with no activity for this many hours are flagged as stalled
    trello_stall_threshold_hours: int = 24   # mirrors stall_threshold_l1_hours by default
    # Incremental sync interval in seconds (also set in Celery beat schedule)
    trello_sync_interval_seconds: int = 300
    # Add these fields to the Settings class in backend/app/config.py
# (next to the existing sections, e.g. right after "Observability")

    # ─── AI Assistant (RAG: ChromaDB + Gemini + voice) ───────────────────────
    gemini_api_key: str | None = None
    chroma_persist_directory: str = "./chroma_data"
    
    gemini_model: str = "gemini-3.8-flash"
    

    # Optional — only if you enable the voice chat (ElevenLabs for the
    # spoken reply; speech-to-text now uses Gemini's native audio input,
    # no separate STT key needed)
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # default ElevenLabs voice

# Then in backend/.env (never committed):
#   GEMINI_API_KEY=AIza...
#   ELEVENLABS_API_KEY=...       (optional, only for voice)

# ── Why gemini_api_key and not GEMINI_API_KEY as the attribute name? ──────
# Same reasoning as before: Pydantic Settings reads the GEMINI_API_KEY
# environment variable case-insensitively, but the Python ATTRIBUTE must
# match the declared field name exactly (snake_case, like every other field
# in this class — database_url, redis_url, trello_api_key...).
# settings.GEMINI_API_KEY would raise an AttributeError.

# ── Where to get a Gemini API key ─────────────────────────────────────────
# https://aistudio.google.com/apikey — free tier available, no credit card
# required to start experimenting.

    # ─── Observability ────────────────────────────────────────────────────────
    log_level: str = "INFO"
    metrics_enabled: bool = True

    # ─── Frontend URL (used for OAuth callback redirects) ────────────────────
    # Override in production: FRONTEND_URL=https://sprintpulse.example.com
    frontend_url: str = "http://localhost:8081"

    # ─── Ticket Scanner Interval ──────────────────────────────────────────────
    ticket_scan_interval_seconds: int = 300  # every 5 minutes

    # ─── Jira Integration ─────────────────────────────────────────────────────
    # Register an OAuth 2.0 app at https://developer.atlassian.com/console/myapps/
    #jira_client_id:     str | None = None
    #jira_client_secret: str | None = None
    # Must match exactly what's registered in the Atlassian developer console
    jira_redirect_uri:  str = "http://localhost:8000/api/v1/integrations/oauth/jira/callback"

    # ─── Microsoft Integration ────────────────────────────────────────────────
    # Register an app at https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps
    microsoft_client_id:     str | None = None
    microsoft_client_secret: str | None = None
    microsoft_redirect_uri:  str = "http://localhost:8000/api/v1/integrations/oauth/microsoft/callback"
    # "common" allows any Microsoft tenant (personal + work accounts)
    microsoft_tenant_id:     str = "common"

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins(self) -> list[str]:
        if self.is_production:
            return ["https://sprintpulse.example.com"]
        return ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
