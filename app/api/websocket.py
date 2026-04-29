"""WebSocket endpoint for bootstrap runtime events."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from app.api.schemas import WebSocketStatusPayload
from app.runtime.agent import RuntimeAgent

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/runtime")
async def runtime_events(websocket: WebSocket) -> None:
    """Send a single status event and keep the endpoint shape stable."""

    await websocket.accept()
    agent = websocket.app.state.agent
    if not isinstance(agent, RuntimeAgent):
        await websocket.close(code=1011)
        return
    status = agent.status_payload()
    event = agent.events.publish("runtime_status", dict(status))
    payload: WebSocketStatusPayload = {
        "type": "runtime_status",
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        **status,
    }
    await websocket.send_json(payload)
    await websocket.close()
