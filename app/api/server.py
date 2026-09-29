"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes_clips import router as clips_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_logs import router as logs_router
from app.api.routes_reports import router as reports_router
from app.api.routes_runtime import router as runtime_router
from app.api.routes_settings import router as settings_router
from app.api.routes_volumes import router as volumes_router
from app.api.websocket import router as websocket_router
from app.config import load_settings
from app.persistence.db import Database
from app.runtime.agent import RuntimeAgent


def create_app() -> FastAPI:
    """Create the local runtime API."""

    settings = load_settings()
    agent = RuntimeAgent(settings=settings, database=Database(settings.database_path))
    agent.initialize()

    app = FastAPI(
        title="Footage Data Manager",
        version="0.1.0",
        description="macOS local runtime API.",
    )
    app.state.agent = agent

    app.include_router(runtime_router)
    app.include_router(volumes_router)
    app.include_router(jobs_router)
    app.include_router(logs_router)
    app.include_router(reports_router)
    app.include_router(clips_router)
    app.include_router(settings_router)
    app.include_router(websocket_router)

    return app
