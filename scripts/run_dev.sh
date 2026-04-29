#!/usr/bin/env sh
set -eu

exec .venv/bin/python -m uvicorn app.api.server:create_app --factory --host "${FDM_HOST:-127.0.0.1}" --port "${FDM_PORT:-8000}"
