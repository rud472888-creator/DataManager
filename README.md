# Footage Data Manager

Footage Data Manager is a macOS local runtime with a browser-based remote web console for field footage offload. The local runtime is the only executor of real file work. The web console creates jobs, sends command requests, observes state through REST/WebSocket, and never browses or copies local media directly.

## Architecture Boundary

- Local runtime: volume discovery, scan, clone/copy, checksum verification, clone report generation, SQLite persistence, logs, and recovery.
- API/WebSocket layer: auth, request validation, state/log/report/settings transport, command dispatch to runtime.
- Remote web console: operational UI that consumes REST/WebSocket only.

## Setup

```sh
cd ~/desktop/datamanager
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/apply_migrations.py
```

## Run

```sh
.venv/bin/python -m uvicorn app.api.server:create_app --factory --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`.

## Validate

```sh
scripts/smoke_release.sh
```

The smoke script runs lint, format check, typecheck, tests, clone capability checks, and package build.

## Demo

```sh
scripts/demo_run.sh
```

The demo script applies migrations and prints the local server command plus the main URLs.

## Current Capability Status

- API-created synthetic `.braw`, `.r3d`, `.ari`, `.mxf`, `.mov`, and `.mp4` fixture jobs run through offload/copy/checksum/report generation and are tested.
- `.mov` and `.mp4` metadata parsing uses the runtime `ffprobe` standard-video parser when `ffprobe` is available or `FDM_FFPROBE_COMMAND` is configured.
- The app is clone-only: metadata parsing and frame capture are outside the production job pipeline.
- Frame capture is handled by a separate program, not this app.
- macOS packaging/signing: documented as a release blocker, not claimed complete.

## Key Docs

- `docs/documentation.md`: full document index and reading order.
- `docs/qa.md`: final validation matrix.
- `docs/deployment.md`: deployment and packaging notes.
- `docs/known-issues.md`: blockers and follow-up backlog.
- `docs/handoff.md`: handoff notes for the next developer/operator.
