"""Volume skeleton routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_agent
from app.api.schemas import VolumeListPayload, VolumePayload
from app.persistence.models import SystemVolume
from app.runtime.agent import RuntimeAgent

router = APIRouter(prefix="/api/volumes", tags=["volumes"])
AgentDep = Annotated[RuntimeAgent, Depends(get_agent)]


def _volume_payload(volume: SystemVolume) -> VolumePayload:
    return {
        "volume_id": volume.volume_id,
        "label": volume.label,
        "kind": "source" if volume.kind == "source" else "destination",
        "status": "available",
        "display_path": volume.display_path,
        "bytes_available": volume.bytes_available,
    }


@router.get("")
def list_volumes(agent: AgentDep) -> VolumeListPayload:
    """Return runtime-owned mock volumes."""

    snapshot = agent.volume_snapshot()
    return {
        "sources": [_volume_payload(volume) for volume in snapshot.sources],
        "destinations": [_volume_payload(volume) for volume in snapshot.destinations],
    }
