"""CLI entry point for the Stage 1 application shell."""

from __future__ import annotations

import uvicorn

from app.api.server import create_app
from app.config import load_settings


def main() -> None:
    """Run the local API and remote console shell."""

    settings = load_settings()
    uvicorn.run(create_app(), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
