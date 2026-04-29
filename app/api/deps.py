"""FastAPI dependencies for the local runtime API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.status import HTTP_401_UNAUTHORIZED

from app.runtime.agent import RuntimeAgent

bearer_scheme = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def get_agent(request: Request) -> RuntimeAgent:
    """Return the process-local runtime agent."""

    agent = getattr(request.app.state, "agent", None)
    if not isinstance(agent, RuntimeAgent):
        raise RuntimeError("runtime agent is not initialized")
    return agent


def require_token(
    request: Request,
    credentials: BearerCredentials,
) -> None:
    """Validate a simple bearer token for protected Stage 3 skeleton routes."""

    settings = get_agent(request).settings
    if credentials is None or credentials.credentials != settings.token:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "unauthorized",
                    "message": "A valid bearer token is required.",
                    "details": {},
                }
            },
        )
