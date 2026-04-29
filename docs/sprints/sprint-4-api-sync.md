# Sprint 4 - API / WebSocket / Command Layer Contract

Working root: `~/desktop/datamanager`.

## Goal

Expose runtime state, jobs, logs, clips, reports, settings, command dispatch, and WebSocket sync to the remote console without moving execution authority into API/UI layers.

## Scope

- Runtime status route.
- Volumes route.
- Jobs list/create/detail routes.
- Job logs route.
- Job reports list/download route.
- Clips route.
- Settings get/patch route.
- Command dispatch route.
- WebSocket runtime status/event sync.
- Token auth guard for write/command/settings routes.
- API tests, auth negative tests, WebSocket smoke.

## Out Of Scope

- Direct file copy/checksum/parser/report execution in API handlers.
- Remote web console UX implementation.
- Complex RBAC.
- Public internet hardening beyond v1 bearer token.

## Endpoints

- `GET /api/runtime/status`
- `GET /api/volumes`
- `GET /api/jobs`
- `POST /api/jobs` protected
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/logs`
- `GET /api/jobs/{job_id}/reports`
- `GET /api/jobs/{job_id}/reports/{report_id}/download`
- `POST /api/jobs/{job_id}/command` protected
- `GET /api/clips?job_id=...`
- `GET /api/settings` protected
- `PATCH /api/settings` protected
- `WS /ws/runtime`

## WebSocket Event Contract

On connect, send a `runtime_status` event with `event_id`, `timestamp`, current runtime status, and active job ID. Reconnect clients must refresh REST snapshots after connecting; event cursor support can deepen later.

## Auth Expectations

- Protected: job creation, command dispatch, settings get/patch.
- Read-only status/volumes/jobs/logs/reports/clips are allowed in local development.
- Missing/invalid bearer token returns 401 on protected routes.

## Command Behavior

API validates command enum/auth and delegates to runtime lifecycle. Runtime accepts/rejects, persists the decision event, and API returns the runtime decision. API must not decide state transitions independently.

## Reconnect Semantics

Browser reconnect should call REST snapshots and subscribe to WebSocket status. The WebSocket startup event gives enough information to know the runtime is alive; durable state comes from REST/persistence.

## Acceptance Criteria

- Required endpoints exist and are tested.
- Unauthorized protected requests fail.
- Command accepted/rejected paths are persisted.
- WebSocket status event works.
- Route handlers do not perform direct copy/checksum/parser/report execution.

## Validation Commands

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest tests/api tests/runtime tests/persistence -q
.venv/bin/python -m build
```

## Implementation Notes

Implemented API/WS transport layer:

- `app/api/routes_jobs.py`: list, create, detail, command dispatch.
- `app/api/routes_logs.py`: append-only job event log read.
- `app/api/routes_reports.py`: report metadata and safe read-only download route rooted under runtime data dir.
- `app/api/routes_clips.py`: parsed clip metadata read.
- `app/api/routes_settings.py`: token-protected get/patch with path-like arbitrary settings filtered out.
- `app/api/websocket.py`: runtime status event with event ID and timestamp on connect.
- `tests/api/test_api_sync.py`: auth negative tests, job command rejection persistence, clips/reports/download, settings patch filtering, WebSocket snapshot.

Validation run:

- `.venv/bin/ruff check .` PASS
- `.venv/bin/ruff format --check .` PASS
- `.venv/bin/mypy app` PASS
- `.venv/bin/pytest tests/api tests/runtime tests/persistence -q` PASS, 23 tests
- `.venv/bin/pytest -q` PASS, 41 tests
- `.venv/bin/python -m build` PASS

Boundary notes:

- API route handlers do not copy, checksum, parse, capture, or generate reports.
- Commands are delegated to `agent.lifecycle`.
- Report download serves existing persisted artifacts only.
