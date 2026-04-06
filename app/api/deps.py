from __future__ import annotations

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.runtime.agent import RuntimeAgent


bearer_scheme = HTTPBearer(auto_error=False)


def get_runtime_agent(request: Request) -> RuntimeAgent:
    return request.app.state.runtime_agent


def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    runtime_agent: RuntimeAgent = Depends(get_runtime_agent),
) -> str:
    if credentials is None or credentials.credentials != runtime_agent.settings.token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return credentials.credentials


async def websocket_require_token(websocket: WebSocket) -> None:
    runtime_agent: RuntimeAgent = websocket.app.state.runtime_agent
    query_token = websocket.query_params.get("token")
    if query_token == runtime_agent.settings.token:
        return
    header_value = websocket.headers.get("authorization", "")
    prefix = "bearer "
    token = header_value[len(prefix):] if header_value.lower().startswith(prefix) else None
    if token != runtime_agent.settings.token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise RuntimeError("Invalid websocket token")
