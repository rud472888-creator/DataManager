from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import websocket_require_token
from app.runtime.events import EventBus, utc_now_iso


router = APIRouter(tags=["websocket"])


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        await websocket_require_token(websocket)
    except RuntimeError:
        return
    event_bus: EventBus = websocket.app.state.event_bus
    queue = event_bus.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                await websocket.send_json(EventBus.serialize(event))
            except TimeoutError:
                await websocket.send_json(
                    {
                        "event_id": None,
                        "type": "runtime.heartbeat",
                        "timestamp": utc_now_iso(),
                        "job_id": None,
                        "payload": {"message": "heartbeat"},
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(queue)
