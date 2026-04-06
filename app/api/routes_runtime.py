from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_runtime_agent, require_token
from app.api.schemas import RuntimeStatusResponse
from app.runtime.agent import RuntimeAgent


router = APIRouter(prefix="/api/runtime", tags=["runtime"])


@router.get("/status", response_model=RuntimeStatusResponse, dependencies=[Depends(require_token)])
async def get_runtime_status(runtime_agent: RuntimeAgent = Depends(get_runtime_agent)) -> RuntimeStatusResponse:
    return RuntimeStatusResponse(**runtime_agent.runtime_status_payload())
