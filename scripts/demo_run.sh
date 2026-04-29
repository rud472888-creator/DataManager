#!/usr/bin/env sh
set -eu

.venv/bin/python scripts/apply_migrations.py
cat <<'MSG'
Demo ready.

Start the local runtime:
  .venv/bin/python -m uvicorn app.api.server:create_app --factory --host 127.0.0.1 --port 8000

Open:
  http://127.0.0.1:8000/

Smoke:
  curl -fsS http://127.0.0.1:8000/api/runtime/status

Note:
  Real BRAW SDK/frame capture is unavailable until configured and validated.
MSG
