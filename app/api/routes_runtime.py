"""Runtime status routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_agent
from app.api.schemas import RuntimeStatusPayload
from app.runtime.agent import RuntimeAgent

router = APIRouter(prefix="/api/runtime", tags=["runtime"])
AgentDep = Annotated[RuntimeAgent, Depends(get_agent)]


@router.get("/status")
def runtime_status(agent: AgentDep) -> RuntimeStatusPayload:
    """Expose local runtime status to the remote web console."""

    return agent.status_payload()


@router.get("/healthz", include_in_schema=False)
def healthz(request: Request) -> dict[str, str]:
    """Tiny local health endpoint for process checks."""

    get_agent(request)
    return {"status": "ok"}


@router.get("/recovery")
def recovery_status(agent: AgentDep) -> dict[str, object]:
    """Expose restart recovery candidates as a read-only snapshot."""

    plan = agent.recovery.load()
    return {
        "jobs": [job.__dict__ for job in plan.jobs],
        "reason": plan.reason,
    }
