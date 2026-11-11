from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.authz import AuthPrincipal, CurrentPrincipal, ensure_project_access
from app.api.dependencies import DbSession
from app.models.action_item import ActionItem
from app.schemas.action_item import (
    ActionGenerationResponse,
    ActionItemDetailResponse,
    ActionItemResponse,
    ActionItemUpdate,
    ActionNoteRequest,
)
from app.services.action_item_service import ActionItemService

router = APIRouter(prefix="/actions", tags=["Actions"])


@router.get("", response_model=list[ActionItemResponse])
async def list_actions(
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: int = Query(...),
    status: str | None = Query(None),
    source_type: str | None = Query(None),
    owner: str | None = Query(None, pattern="^(mine|all)$"),
    include_resolved: bool = Query(False),
) -> list[ActionItemResponse]:
    await ensure_project_access(session, principal, project_id)
    owner_user_id = principal.user_id if owner == "mine" else None
    actions = await ActionItemService(session).list_actions(
        project_id=project_id,
        status=status,
        source_type=source_type,
        owner_user_id=owner_user_id,
        include_resolved=include_resolved,
    )
    return [ActionItemResponse.model_validate(action) for action in actions]


@router.post("/generate", response_model=ActionGenerationResponse)
async def generate_actions(
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: int = Query(...),
) -> ActionGenerationResponse:
    await ensure_project_access(session, principal, project_id)
    _ensure_can_create_actions(principal)
    result = await ActionItemService(session).generate_for_project(project_id, _actor_user_id(principal))
    await session.commit()
    return ActionGenerationResponse(**result)


@router.get("/{action_id}", response_model=ActionItemDetailResponse)
async def get_action(
    action_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
) -> ActionItemDetailResponse:
    action = await _load_action(session, principal, action_id)
    return ActionItemDetailResponse.model_validate(action)


@router.patch("/{action_id}", response_model=ActionItemDetailResponse)
async def update_action(
    action_id: int,
    body: ActionItemUpdate,
    session: DbSession,
    principal: CurrentPrincipal,
) -> ActionItemDetailResponse:
    action = await _load_action(session, principal, action_id)
    _ensure_can_mutate(principal, action)
    fields = body.model_dump(exclude_unset=True, exclude={"note"})
    updated = await ActionItemService(session).update_action(
        action,
        actor_user_id=_actor_user_id(principal),
        note=body.note,
        **fields,
    )
    await session.commit()
    updated = await ActionItemService(session).get_action(updated.id)
    return ActionItemDetailResponse.model_validate(updated)


@router.post("/{action_id}/acknowledge", response_model=ActionItemDetailResponse)
async def acknowledge_action(
    action_id: int,
    body: ActionNoteRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> ActionItemDetailResponse:
    return await _transition_endpoint(
        action_id,
        body,
        session,
        principal,
        next_status="acknowledged",
        event_type="acknowledged",
    )


@router.post("/{action_id}/approve", response_model=ActionItemDetailResponse)
async def approve_action(
    action_id: int,
    body: ActionNoteRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> ActionItemDetailResponse:
    _ensure_can_approve(principal)
    return await _transition_endpoint(
        action_id,
        body,
        session,
        principal,
        next_status="approved",
        event_type="approved",
    )


@router.post("/{action_id}/reject", response_model=ActionItemDetailResponse)
async def reject_action(
    action_id: int,
    body: ActionNoteRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> ActionItemDetailResponse:
    _ensure_can_approve(principal)
    return await _transition_endpoint(
        action_id,
        body,
        session,
        principal,
        next_status="rejected",
        event_type="rejected",
    )


@router.post("/{action_id}/dispatch", response_model=ActionItemDetailResponse)
async def dispatch_action(
    action_id: int,
    body: ActionNoteRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> ActionItemDetailResponse:
    action = await _load_action(session, principal, action_id)
    _ensure_can_mutate(principal, action)
    updated = await ActionItemService(session).dispatch(
        action,
        actor_user_id=_actor_user_id(principal),
        note=body.note,
    )
    await session.commit()
    updated = await ActionItemService(session).get_action(updated.id)
    return ActionItemDetailResponse.model_validate(updated)


@router.post("/{action_id}/resolve", response_model=ActionItemDetailResponse)
async def resolve_action(
    action_id: int,
    body: ActionNoteRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> ActionItemDetailResponse:
    return await _transition_endpoint(
        action_id,
        body,
        session,
        principal,
        next_status="resolved",
        event_type="resolved",
    )


@router.post("/{action_id}/dismiss", response_model=ActionItemDetailResponse)
async def dismiss_action(
    action_id: int,
    body: ActionNoteRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> ActionItemDetailResponse:
    _ensure_can_approve(principal)
    return await _transition_endpoint(
        action_id,
        body,
        session,
        principal,
        next_status="dismissed",
        event_type="dismissed",
    )


async def _transition_endpoint(
    action_id: int,
    body: ActionNoteRequest,
    session: DbSession,
    principal: AuthPrincipal,
    *,
    next_status: str,
    event_type: str,
) -> ActionItemDetailResponse:
    action = await _load_action(session, principal, action_id)
    _ensure_can_mutate(principal, action)
    updated = await ActionItemService(session).transition(
        action,
        actor_user_id=_actor_user_id(principal),
        next_status=next_status,
        event_type=event_type,
        note=body.note,
    )
    await session.commit()
    updated = await ActionItemService(session).get_action(updated.id)
    return ActionItemDetailResponse.model_validate(updated)


async def _load_action(
    session: DbSession,
    principal: AuthPrincipal,
    action_id: int,
) -> ActionItem:
    action = await ActionItemService(session).get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found.")
    await ensure_project_access(session, principal, action.project_id)
    return action


def _ensure_can_create_actions(principal: AuthPrincipal) -> None:
    if principal.role == "auditor_readonly":
        raise HTTPException(status_code=403, detail="Auditors cannot generate action items.")


def _ensure_can_mutate(principal: AuthPrincipal, action: ActionItem) -> None:
    if principal.role == "auditor_readonly":
        raise HTTPException(status_code=403, detail="Auditors cannot change action items.")
    if principal.role == "developer":
        if action.owner_user_id == principal.user_id or action.owner_role == "developer":
            return
        raise HTTPException(status_code=403, detail="Developers can only act on developer-owned actions.")


def _ensure_can_approve(principal: AuthPrincipal) -> None:
    if principal.role in {"developer", "auditor_readonly"}:
        raise HTTPException(status_code=403, detail="This action requires delivery or admin approval.")


def _actor_user_id(principal: AuthPrincipal) -> int | None:
    return principal.user_id if principal.user_id > 0 else None
