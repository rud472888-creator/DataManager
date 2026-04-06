from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from app.api.server import create_api_app
from app.config import Settings
from app.logging import configure_logging
from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import PersistenceBundle
from app.runtime.agent import RuntimeAgent
from app.runtime.events import EventBus


def build_runtime(settings: Settings) -> tuple[RuntimeAgent, EventBus]:
    settings.ensure_directories()
    configure_logging(settings.log_level)
    database = Database(settings.db_path)
    schema_path = Path(__file__).resolve().parent / "persistence" / "schema.sql"
    apply_migrations(database, schema_path)
    persistence = PersistenceBundle(database)
    event_bus = EventBus()
    runtime_agent = RuntimeAgent(settings=settings, persistence=persistence, event_bus=event_bus)
    return runtime_agent, event_bus


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.load()
    runtime_agent, event_bus = build_runtime(resolved)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime_agent.startup()
        yield

    app = create_api_app(settings=resolved, runtime_agent=runtime_agent, event_bus=event_bus)
    app.router.lifespan_context = lifespan
    return app


app = create_app()


if __name__ == "__main__":
    runtime_settings = Settings.load()
    uvicorn.run(
        "app.main:app",
        host=runtime_settings.host,
        port=runtime_settings.port,
        reload=False,
    )
