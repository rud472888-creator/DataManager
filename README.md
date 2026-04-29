# Footage Data Manager

Footage Data Manager is a macOS local runtime with a browser-based remote web console for field footage offload. The local runtime is the only executor of real file work. The web console creates jobs, sends command requests, observes state through REST/WebSocket, and never browses or copies local media directly.

## Architecture Boundary

- Local runtime: volume discovery, scan, copy, checksum, parser execution, frame capture, report generation, SQLite persistence, logs, and recovery.
- API/WebSocket layer: auth, request validation, state/log/report/clip/settings transport, command dispatch to runtime.
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

The smoke script runs lint, format check, typecheck, tests, BRAW capability truthfulness, and package build.

## Demo

```sh
scripts/demo_run.sh
```

The demo script applies migrations and prints the local server command plus the main URLs. It does not fake BRAW readiness.

## Current Capability Status

- API-created synthetic `.braw` fixture jobs run through offload/copy/checksum/report generation and are tested.
- Runtime parser/report plumbing with mock parser: implemented and tested.
- Real BRAW SDK metadata/frame capture: unavailable until `FDM_BRAW_METADATA_COMMAND` and real sample media are provided.
- macOS packaging/signing: documented as a release blocker, not claimed complete.

## Key Docs

- `docs/documentation.md`: full document index and reading order.
- `docs/qa.md`: final validation matrix.
- `docs/deployment.md`: deployment and packaging notes.
- `docs/known-issues.md`: blockers and follow-up backlog.
- `docs/handoff.md`: handoff notes for the next developer/operator.
