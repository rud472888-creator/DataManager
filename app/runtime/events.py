from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class RuntimeEvent:
    event_id: int
    type: str
    timestamp: str
    job_id: str | None
    payload: dict[str, Any]


class EventBus:
    def __init__(self) -> None:
        self._sequence = 0
        self._subscribers: set[asyncio.Queue[RuntimeEvent]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event_type: str, payload: dict[str, Any], job_id: str | None = None) -> RuntimeEvent:
        async with self._lock:
            self._sequence += 1
            event = RuntimeEvent(
                event_id=self._sequence,
                type=event_type,
                timestamp=utc_now_iso(),
                job_id=job_id,
                payload=payload,
            )
            for queue in list(self._subscribers):
                queue.put_nowait(event)
            return event

    def subscribe(self) -> asyncio.Queue[RuntimeEvent]:
        queue: asyncio.Queue[RuntimeEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[RuntimeEvent]) -> None:
        self._subscribers.discard(queue)

    @staticmethod
    def serialize(event: RuntimeEvent) -> dict[str, Any]:
        return asdict(event)
