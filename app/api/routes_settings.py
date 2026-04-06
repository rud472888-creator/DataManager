from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_runtime_agent, require_token
from app.api.schemas import SettingsPatchRequest
from app.runtime.agent import RuntimeAgent


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", dependencies=[Depends(require_token)])
async def get_settings(runtime_agent: RuntimeAgent = Depends(get_runtime_agent)) -> dict[str, object]:
    return runtime_agent.get_settings_summary()


@router.patch("", dependencies=[Depends(require_token)])
async def patch_settings(
    request: SettingsPatchRequest,
    runtime_agent: RuntimeAgent = Depends(get_runtime_agent),
) -> dict[str, object]:
    return runtime_agent.patch_settings(
        allowed_destination_roots=request.allowed_destination_roots,
        poll_interval_sec=request.poll_interval_sec,
        token=request.token,
    )
