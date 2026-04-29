"""Settings skeleton routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_agent, require_token
from app.api.schemas import SettingsPayload
from app.persistence.repositories import SettingsRepository
from app.runtime.agent import RuntimeAgent

router = APIRouter(prefix="/api/settings", tags=["settings"])
AgentDep = Annotated[RuntimeAgent, Depends(get_agent)]
AuthDep = Annotated[None, Depends(require_token)]


@router.get("")
def get_settings(
    agent: AgentDep,
    _auth: AuthDep,
) -> SettingsPayload:
    """Return safe settings metadata without exposing the secret token."""

    return {
        "token_required": True,
        "allowed_destinations": [str(path) for path in agent.settings.allowed_dest_roots],
        "data_dir": str(agent.settings.data_dir),
    }


@router.patch("")
def patch_settings(
    request: Request,
    payload: dict[str, object],
    _auth: AuthDep,
) -> dict[str, object]:
    """Persist safe UI/runtime settings metadata without arbitrary path writes."""

    allowed_keys = {"ui_density", "operator_name"}
    allowed = {key: value for key, value in payload.items() if key in allowed_keys}
    with request.app.state.agent.database.session() as connection:
        SettingsRepository(connection).set_json("remote_console", allowed)
    return {"settings": allowed}
