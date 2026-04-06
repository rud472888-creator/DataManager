from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_clips import router as clips_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_reports import router as reports_router
from app.api.routes_runtime import router as runtime_router
from app.api.routes_volumes import router as volumes_router
from app.api.websocket import router as websocket_router
from app.config import Settings
from app.runtime.agent import RuntimeAgent
from app.runtime.events import EventBus


def create_api_app(*, settings: Settings, runtime_agent: RuntimeAgent, event_bus: EventBus) -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.state.runtime_agent = runtime_agent
    app.state.event_bus = event_bus

    app.include_router(runtime_router)
    app.include_router(volumes_router)
    app.include_router(jobs_router)
    app.include_router(clips_router)
    app.include_router(reports_router)
    app.include_router(websocket_router)

    static_dir = Path(__file__).resolve().parent.parent / "web_console"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return app
