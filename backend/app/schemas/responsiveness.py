from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.common import OrmBase


class ResponsivenessTrendPoint(BaseModel):
    date_interval: str
    avg_response_time_hours: float | None
    avg_reaction_time_hours: float | None


class DeveloperResponsivenessRow(BaseModel):
    developer_id: int
    trello_member_id: str | None
    developer_name: str
    
    total_comments: int
    total_reactions: int
    
    # Time from card creation to the very first developer action
    avg_first_reaction_hours: float | None
    
    # Time from card creation to the very first developer comment
    avg_first_response_hours: float | None
    
    # Average time since last action across active tickets
    inactivity_duration_hours: float | None
    
    # Is the user currently breaching internal SLA
    sla_breaching_tickets: int


class ResponsivenessMetrics(BaseModel):
    project_id: int | None
    company_id: int | None
    
    global_avg_reaction_hours: float | None
    global_avg_response_hours: float | None
    
    total_developer_comments: int
    total_developer_reactions: int
    
    active_developers: int
    dormant_developers: int
    
    total_sla_breaches: int
    
    trend: list[ResponsivenessTrendPoint]
    developers: list[DeveloperResponsivenessRow]
