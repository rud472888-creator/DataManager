from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_runtime_agent, require_token
from app.runtime.agent import RuntimeAgent


router = APIRouter(prefix="/api/volumes", tags=["volumes"])


@router.get("", dependencies=[Depends(require_token)])
async def list_volumes(runtime_agent: RuntimeAgent = Depends(get_runtime_agent)) -> dict[str, object]:
    return {"items": runtime_agent.list_volumes()}
