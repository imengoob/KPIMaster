from fastapi import APIRouter
from app.api.v1 import assistant as assistant_router


from app.api.v1 import (
    actions,
    auth,
    blockers,
    companies,
    developers,
    engagements,
    integrations,
    kpis,
    projects,
    repository_activity,
    sprints,
    tickets,
    trello,
    websockets,
    analytics,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(assistant_router.router, prefix="/assistant", tags=["assistant"])
api_router.include_router(auth.router)
api_router.include_router(actions.router)
api_router.include_router(companies.router)
api_router.include_router(engagements.router)
api_router.include_router(projects.router)
api_router.include_router(sprints.router)
api_router.include_router(tickets.router)
api_router.include_router(developers.router)
api_router.include_router(blockers.router)
api_router.include_router(kpis.router)
api_router.include_router(repository_activity.router)
api_router.include_router(trello.router)
api_router.include_router(integrations.router)
api_router.include_router(websockets.router)
api_router.include_router(analytics.router)
