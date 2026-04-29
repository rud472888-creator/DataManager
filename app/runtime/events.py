"""Runtime event publisher abstraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True)
class RuntimeEvent:
    type: str
    payload: dict[str, object]
    event_id: str = field(default_factory=lambda: f"evt-{uuid4().hex[:12]}")
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class MemoryEventPublisher:
    """In-memory publisher for tests and Stage 3 WebSocket stubs."""

    def __init__(self) -> None:
        self._events: list[RuntimeEvent] = []

    def publish(self, event_type: str, payload: dict[str, object]) -> RuntimeEvent:
        event = RuntimeEvent(type=event_type, payload=payload)
        self._events.append(event)
        return event

    def recent(self) -> list[RuntimeEvent]:
        return list(self._events)
