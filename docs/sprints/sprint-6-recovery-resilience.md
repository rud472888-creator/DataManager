# Sprint 6 - Recovery, Resilience & Local Operator Panel Contract

Working root: `~/desktop/datamanager`.

## Goal

Make reconnect/restart/control scenarios credible and add a minimal local operator panel that does not become a second product.

## Scope

- Browser reload/reconnect restores REST state and WebSocket status snapshot.
- Runtime restart loads recoverable jobs from SQLite.
- Pause/resume/cancel/retry command requests flow API -> runtime -> persistence -> UI/logs.
- Log parity between persisted events and remote log route.
- Minimal local operator panel summary.

## Out Of Scope

- Full native macOS UI.
- Packaging/signing.
- Automatic destructive repair of interrupted copy state.
- Multi-user collaboration.

## Scenarios

- Browser reload during queued/active job keeps job persisted and visible.
- Runtime restart with `QUEUED`, `PAUSED`, `WARN`, `FAILED` jobs returns recovery candidates.
- Command rejection is visible in logs and UI/API response.
- Backup destination failure path remains `WARN`.

## Local Operator Panel Responsibilities

- Runtime/network status summary.
- Active job summary.
- Links/labels for logs and results.
- Emergency controls as API-route references only, not direct execution.

## Log Parity

Persisted `job_events` and `GET /api/jobs/{job_id}/logs` must show the same command decisions and state events.

## Validation Commands

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest -q
.venv/bin/python -m build
```

## Implementation Notes

Implemented recovery/resilience closure:

- `GET /api/runtime/recovery` exposes restart recovery candidates.
- `app/local_panel/minimal_panel.py` renders a minimal local status-only panel.
- Playwright reload scenario verifies browser reconnect/reload keeps queued job visible.
- Runtime restart simulation verifies recoverable jobs survive app recreation with same SQLite DB.
- Log parity test verifies command rejection appears in remote log route.
- Backup failure scenario remains `WARN`.

Validation run:

- `.venv/bin/ruff check .` PASS
- `.venv/bin/ruff format --check .` PASS
- `.venv/bin/mypy app` PASS
- `.venv/bin/pytest -q` PASS, 47 tests
- `.venv/bin/python -m build` PASS

Remaining operational gaps:

- Active interrupted copy-state repair remains conservative and is not auto-resumed.
- Local panel is HTML string/status-only, not a packaged native app.
