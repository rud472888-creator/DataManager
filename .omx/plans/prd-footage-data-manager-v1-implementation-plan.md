# Footage Data Manager v1 Implementation Plan

Generated: 2026-04-06T20:37:12+09:00
Mode: `$plan` direct

## Sources of truth

- Product spec: `Footage_DataManager_Spec_v2_2_Local_Runtime_Remote_Console.md:1-593`
- Repo audit:
  - `git ls-files` returned no tracked project files
  - `git log --oneline -n 5` failed with `main does not have any commits yet`
  - top-level files are limited to `.env.example`, `.gitignore`, the spec, local virtualenv folders, and `.omx/`
- Existing stack signals:
  - `.env.example:1-4` defines host, port, and token
  - `.gitignore:1-10` ignores Python cache/build artifacts and `*.spec`
  - `.venv/pyvenv.cfg` shows Python `3.13.12`

## Explicit assumptions

1. Because the repository is effectively empty and the spec already names FastAPI plus a Python-style module tree, v1 should be implemented as a Python 3.13 monorepo with one macOS local runtime process hosting the runtime engine, REST API, WebSocket broadcaster, and static web console assets.
2. The web console should be served by the local runtime/API process in v1 to avoid introducing a second deployment stack before the runtime boundary is proven.
3. `retry` should create a new queued job linked to the terminal source job via `retry_of_job_id`; the original job stays immutable for auditability.
4. Device detach should map to `PAUSED` when recovery is possible and `FAILED` when the source or required destination is gone permanently; no extra v1 state names should be introduced beyond the spec's list.
5. BRAW metadata parsing and frame capture happen only inside local parser/capture adapters. If frame capture cannot be proven in P0.5, image PDF remains a release blocker until an approved local-only fallback exists.

## 1. Current repo status summary

- Current status:
  - No tracked application code exists yet.
  - No commit history exists yet.
  - No runtime, API, persistence, parser, web console, tests, or packaging scaffold exists yet.
- Reusable assets:
  - The spec is the only real implementation artifact.
  - `.env.example` is reusable as the starting runtime config contract for `host`, `port`, and `token`.
  - `.gitignore` and the local Python virtualenv indicate a Python-first setup is already acceptable.
- Blockers:
  - No BRAW SDK integration or ffmpeg availability has been proven.
  - No sample BRAW fixture set exists.
  - No SQLite schema, state machine, or event model exists.
  - No recovery behavior exists to satisfy restart resilience.
- Spec/code conflicts:
  - There is no code-level contradiction yet because there is almost no code.
  - The main implementation risk is accidental drift from the spec by introducing browser-side filesystem access, a web-first execution model, or multiple concurrent offload workers, all of which the spec forbids (`Footage_DataManager_Spec_v2_2_Local_Runtime_Remote_Console.md:16-20`, `:128-151`, `:157-209`, `:237-260`, `:568-593`).

## 2. Architecture proposal aligned to the spec

- Chosen v1 shape:
  - One local macOS Python process owns runtime execution authority.
  - FastAPI runs in the same process as the runtime and exposes REST plus one WebSocket event stream.
  - SQLite is the system of record for jobs, events, file results, clips, reports, settings, and recent volume state.
  - The web console is a remote control and monitoring UI only; it can create jobs only from runtime-discovered source/destination IDs and can never submit raw local paths.
  - The optional local panel is a minimal operator overlay, not a second product.
- Internal boundaries:
  - `runtime`: state machine, scheduler, scan/copy/verify/parse/capture/report orchestration, recovery, volume polling.
  - `api`: request validation, auth, response schemas, websocket fanout, static asset serving.
  - `persistence`: SQLite connection, schema bootstrap/migrations, repositories, manifest/report indexing.
  - `parsers`: BRAW-first plugin contract and registry.
  - `web_console`: browser-only REST/WS client and responsive views.
  - `local_panel`: health/status/emergency controls only.
- Decision rationale:
  - This is the smallest architecture that satisfies runtime authority, browser disconnect resilience, REST + WebSocket control, and the spec's proposed module split (`Footage_DataManager_Spec_v2_2_Local_Runtime_Remote_Console.md:153-209`, `:509-549`, `:552-564`).
  - It avoids unnecessary process or repo splits before the runtime/persistence contract is stable.

## 3. Exact module/file plan

```text
.
├─ requirements.txt
├─ app/
│  ├─ main.py
│  ├─ config.py
│  ├─ logging_config.py
│  ├─ runtime/
│  │  ├─ controller.py
│  │  ├─ scheduler.py
│  │  ├─ state_machine.py
│  │  ├─ recovery.py
│  │  ├─ command_bus.py
│  │  ├─ event_bus.py
│  │  ├─ volume_service.py
│  │  ├─ scan_service.py
│  │  ├─ offload_service.py
│  │  ├─ checksum_service.py
│  │  ├─ parse_service.py
│  │  ├─ capture_service.py
│  │  └─ report_service.py
│  ├─ api/
│  │  ├─ server.py
│  │  ├─ auth.py
│  │  ├─ schemas.py
│  │  ├─ routes_runtime.py
│  │  ├─ routes_volumes.py
│  │  ├─ routes_jobs.py
│  │  ├─ routes_clips.py
│  │  ├─ routes_reports.py
│  │  ├─ routes_settings.py
│  │  └─ websocket.py
│  ├─ persistence/
│  │  ├─ db.py
│  │  ├─ schema.sql
│  │  ├─ repositories.py
│  │  ├─ manifests.py
│  │  └─ report_index.py
│  ├─ parsers/
│  │  ├─ base.py
│  │  ├─ registry.py
│  │  ├─ braw_parser.py
│  │  └─ braw_capture_adapter.py
│  ├─ web_console/
│  │  ├─ index.html
│  │  ├─ app.js
│  │  ├─ api_client.js
│  │  ├─ ws_client.js
│  │  ├─ state_store.js
│  │  ├─ views_home.js
│  │  ├─ views_job_detail.js
│  │  ├─ views_queue.js
│  │  ├─ views_reports.js
│  │  ├─ views_settings.js
│  │  └─ styles.css
│  └─ local_panel/
│     └─ minimal_panel.py
└─ tests/
   ├─ fixtures/
   │  ├─ braw_stub/
   │  └─ sqlite/
   ├─ unit/
   │  ├─ runtime/
   │  ├─ persistence/
   │  └─ parsers/
   ├─ integration/
   │  ├─ api/
   │  ├─ runtime/
   │  └─ recovery/
   └─ e2e/
      └─ console/
```

### File responsibilities

- `app/main.py`: compose config, DB bootstrap, runtime controller, FastAPI app, and startup/shutdown wiring.
- `app/runtime/controller.py`: single authority that receives validated commands, applies state transitions, and owns the single active job invariant.
- `app/runtime/scheduler.py`: dequeues `QUEUED` jobs and ensures only one job enters active execution at a time.
- `app/runtime/state_machine.py`: allowed transitions and command acceptance rules.
- `app/runtime/recovery.py`: rebuild runtime queue from SQLite on restart and reconcile partial copy state.
- `app/runtime/volume_service.py`: poll `/Volumes`, inspect configured destinations, and persist discovered volume state.
- `app/runtime/scan_service.py`: enumerate supported files, filter junk files, create `job_files` rows.
- `app/runtime/offload_service.py`: create project tree and copy to main/backup destinations.
- `app/runtime/checksum_service.py`: compute and compare checksums per file and persist results.
- `app/runtime/parse_service.py`: execute parser registry on copied BRAW assets and persist `clips`.
- `app/runtime/capture_service.py`: generate stills for report use only after BRAW POC passes.
- `app/runtime/report_service.py`: write checksum PDF, image PDF, metadata XLSX, and manifest JSON.
- `app/api/*`: pure control plane; never direct filesystem execution.
- `app/web_console/*`: no file picker, no local path browsing, no direct filesystem assumptions; all source/destination options come from API payloads.

## 4. Data model / SQLite table plan

- `jobs`
  - columns: `job_id TEXT PRIMARY KEY`, `retry_of_job_id TEXT NULL`, `project_name TEXT NOT NULL`, `source_volume_id TEXT NOT NULL`, `dest_main_id TEXT NOT NULL`, `dest_backup_id TEXT NULL`, `state TEXT NOT NULL`, `current_step TEXT NOT NULL`, `stats_json TEXT NOT NULL DEFAULT '{}'`, `policy_json TEXT NOT NULL DEFAULT '{}'`, `operator_origin TEXT NOT NULL`, `is_active_execution INTEGER NOT NULL DEFAULT 0`, `last_error_code TEXT NULL`, `last_error_message TEXT NULL`, `created_at TEXT NOT NULL`, `started_at TEXT NULL`, `ended_at TEXT NULL`
  - indexes: `(state, created_at DESC)`, partial unique index on `is_active_execution=1`
- `job_events`
  - columns: `event_id INTEGER PRIMARY KEY AUTOINCREMENT`, `job_id TEXT NOT NULL`, `seq INTEGER NOT NULL`, `event_type TEXT NOT NULL`, `prev_state TEXT NULL`, `next_state TEXT NULL`, `command_name TEXT NULL`, `command_origin TEXT NULL`, `command_accepted INTEGER NULL`, `message TEXT NOT NULL`, `payload_json TEXT NOT NULL DEFAULT '{}'`, `created_at TEXT NOT NULL`
  - indexes: unique `(job_id, seq)`, `(created_at DESC)`
- `job_files`
  - columns: `file_id INTEGER PRIMARY KEY AUTOINCREMENT`, `job_id TEXT NOT NULL`, `relative_path TEXT NOT NULL`, `source_size_bytes INTEGER NOT NULL`, `source_mtime_ns INTEGER NULL`, `checksum_algorithm TEXT NOT NULL`, `source_checksum TEXT NULL`, `main_dest_path TEXT NULL`, `backup_dest_path TEXT NULL`, `copy_status_main TEXT NOT NULL DEFAULT 'PENDING'`, `copy_status_backup TEXT NOT NULL DEFAULT 'PENDING'`, `verify_status_main TEXT NOT NULL DEFAULT 'PENDING'`, `verify_status_backup TEXT NOT NULL DEFAULT 'PENDING'`, `bytes_copied_main INTEGER NOT NULL DEFAULT 0`, `bytes_copied_backup INTEGER NOT NULL DEFAULT 0`, `error_code TEXT NULL`, `error_message TEXT NULL`, `last_updated_at TEXT NOT NULL`
  - indexes: unique `(job_id, relative_path)`, `(job_id, copy_status_main, verify_status_main)`
- `clips`
  - columns: `clip_id INTEGER PRIMARY KEY AUTOINCREMENT`, `job_id TEXT NOT NULL`, `file_id INTEGER NOT NULL`, `format_name TEXT NOT NULL`, `parser_name TEXT NOT NULL`, `clip_name TEXT NULL`, `reel TEXT NULL`, `camera_serial TEXT NULL`, `timecode_start TEXT NULL`, `fps REAL NULL`, `width INTEGER NULL`, `height INTEGER NULL`, `duration_frames INTEGER NULL`, `scene TEXT NULL`, `take TEXT NULL`, `metadata_json TEXT NOT NULL`, `created_at TEXT NOT NULL`
  - indexes: `(job_id)`, `(file_id)`
- `reports`
  - columns: `report_id INTEGER PRIMARY KEY AUTOINCREMENT`, `job_id TEXT NOT NULL`, `report_type TEXT NOT NULL`, `file_path TEXT NOT NULL`, `status TEXT NOT NULL`, `size_bytes INTEGER NULL`, `checksum TEXT NULL`, `created_at TEXT NOT NULL`, `error_message TEXT NULL`
  - indexes: `(job_id, report_type)`
- `system_volumes`
  - columns: `volume_id TEXT PRIMARY KEY`, `mount_path TEXT NOT NULL`, `display_name TEXT NOT NULL`, `role_hint TEXT NOT NULL`, `filesystem_type TEXT NULL`, `device_id TEXT NULL`, `total_bytes INTEGER NULL`, `free_bytes INTEGER NULL`, `is_mounted INTEGER NOT NULL`, `is_allowed_destination INTEGER NOT NULL DEFAULT 0`, `metadata_json TEXT NOT NULL DEFAULT '{}'`, `last_seen_at TEXT NOT NULL`
  - indexes: `(is_mounted, last_seen_at DESC)`
- `settings`
  - columns: `key TEXT PRIMARY KEY`, `value_json TEXT NOT NULL`, `updated_at TEXT NOT NULL`

### Persistence rules

- Canonical truth is `jobs.state` plus append-only `job_events`.
- Every state change writes a `job_events` row in the same transaction as the `jobs` update.
- Every file-level copy/verify change writes `job_files` immediately so recovery can resume from durable state.
- All timestamps are stored as UTC ISO-8601 strings.

## 5. API endpoint plan

- `GET /api/runtime/status`
  - returns runtime health, version, Python version, token auth enabled, active job ID, dependency status (`braw`, `ffmpeg`, `sqlite`), and last volume scan timestamp
- `GET /api/volumes`
  - returns runtime-discovered source volumes and allowed destination volumes only; browser never submits raw paths
- `POST /api/jobs`
  - body: `project_name`, `source_volume_id`, `dest_main_id`, `dest_backup_id`, `policy`
  - behavior: create job in `QUEUED`; do not start immediately if another active job exists
- `GET /api/jobs`
  - returns queue plus recent terminal jobs with compact summary fields
- `GET /api/jobs/{id}`
  - returns job summary, state, step, progress stats, warning/error counts, recent event tail, and report summary
- `GET /api/jobs/{id}/logs`
  - returns paginated event/log view derived from runtime logs plus `job_events`
- `GET /api/jobs/{id}/reports`
  - returns known report artifacts and download URLs
- `POST /api/jobs/{id}/command`
  - body: `command=pause|resume|cancel|retry`
  - behavior: API validates auth and shape; runtime decides accept/reject based on current state
- `GET /api/clips`
  - filters: `job_id`, paging; returns parsed metadata rows for queryable review
- `GET /api/settings`
  - returns allowed destinations, auth mode, UI defaults, and dependency flags
- `PATCH /api/settings`
  - allows token rotation, allowed destination list updates, and UI/runtime-safe config changes only
- `GET /ws/events` (WebSocket)
  - single broadcast channel for runtime, volume, job, command, report, and log events

## 6. WebSocket event plan

### Envelope

```json
{
  "seq": 1042,
  "event_type": "job.progress",
  "job_id": "JOB-20260406-0001",
  "timestamp": "2026-04-06T11:37:12Z",
  "payload": {}
}
```

### Required event types

- `runtime.status`
  - runtime online/offline, version, dependency health, active job ID
- `runtime.heartbeat`
  - lightweight liveness pulse so browser can distinguish quiet runtime from broken socket
- `volumes.snapshot`
  - full source/destination volume snapshot after poll/reconnect
- `volumes.changed`
  - mount/unmount or destination availability change
- `job.created`
  - new queued job registered
- `job.state`
  - state transition with `prev_state`, `next_state`, `current_step`, and reason
- `job.progress`
  - `processed_files`, `total_files`, `bytes_done`, `bytes_total`, `speed_mbps`, `eta_sec`, `warnings`, `errors`, `current_file`
- `job.command`
  - command accepted/rejected result with reason
- `job.log`
  - human-readable log line/event summary for live console tail
- `job.file_result`
  - file-level completion/failure summary for copy/verify updates
- `job.report_ready`
  - report artifact created and available
- `job.recovered`
  - runtime restarted and reconstructed queued/paused/warn/failed work

### Client rules

- WebSocket is live-update transport only.
- REST remains the recovery source of truth on every reconnect or sequence gap.
- Browser disconnect must not cancel or pause runtime work.

## 7. Job state machine plan

### Normal path

`QUEUED -> SCANNING -> PREPARING -> COPYING -> VERIFYING -> PARSING -> CAPTURING -> REPORTING -> COMPLETED`

### Command path

- `pause`
  - allowed only in `COPYING`
  - transition: `COPYING -> PAUSING -> PAUSED`
- `resume`
  - allowed only in `PAUSED`
  - transition: `PAUSED -> COPYING`
- `cancel`
  - allowed in `QUEUED`, `SCANNING`, `PREPARING`, `COPYING`, `PAUSED`, `VERIFYING`, `PARSING`, `CAPTURING`, `REPORTING`
  - transition: active state -> `CANCELLED`
- `retry`
  - allowed in `WARN`, `FAILED`, `CANCELLED`, `COMPLETED`
  - behavior: create new `QUEUED` job linked by `retry_of_job_id`

### Failure and warning policy

- `WARN`
  - terminal state for partial success, such as main copy success plus backup failure, or recoverable parse/report gaps where outputs still exist
- `FAILED`
  - terminal state for unrecoverable source loss, unrecoverable destination failure, schema corruption, or impossible continuation
- no direct `COPYING -> WARN`
  - runtime should finish durable event/report writing first, then enter `WARN`

### Restart recovery

- Recover candidates on boot: `QUEUED`, `PAUSED`, `WARN`, `FAILED`
- Interrupted active jobs are reconciled by inspecting persisted `job_files` plus mounted volumes:
  - if resumable, move to `PAUSED`
  - if not resumable, move to `FAILED`

## 8. Phased milestone plan

- `P0: runtime foundation`
  - scaffold Python app structure, config, logging, SQLite bootstrap, state machine, scheduler, command/event bus
  - implement volume polling, source scan, project tree creation, main/backup copy, checksum verification, `manifest.json`, durable logs, recovery hooks
  - prove the single active job invariant and restart-safe queue reconstruction
- `P0.5: BRAW viability gate`
  - prove local-only BRAW metadata parse and frame capture on real fixture material
  - decide capture adapter and artifact path before building image PDF
- `P1: remote control plane and reports`
  - ship REST API, WebSocket stream, token auth, responsive console screens, report center, logs, and reconnect logic
  - generate checksum PDF, metadata XLSX, and image PDF from local runtime outputs
- `P2: operator polish`
  - minimal local operator panel, packaging, launch behavior, dependency diagnostics, artifact/log folder shortcuts

## 9. Top technical risks and mitigation

- BRAW SDK / frame capture may fail on target macOS machines
  - mitigation: make `P0.5` a hard gate with real fixtures before report/UI polish
- Partial-copy recovery can corrupt trust in verification results
  - mitigation: persist per-file copy and verify status, never infer recovery from job-level state alone, and re-verify incomplete files on restart
- API responsiveness can degrade if runtime work shares the same event loop incorrectly
  - mitigation: keep runtime workers off the FastAPI serving loop; API only dispatches commands and reads persisted state
- Browser state can drift from runtime truth during reconnects
  - mitigation: sequence every WS event, force REST rehydration on reconnect or gap, and keep client state derived from runtime payloads only
- Destination disappearance during copy can create silent partial success
  - mitigation: runtime volume polling plus immediate event emission, deterministic transition to `PAUSED` or `FAILED`, and explicit `WARN` only after final accounting
- Empty repo means no existing tests or fixtures protect behavior
  - mitigation: create schema/state-machine/runtime tests before adding BRAW/report complexity

## 10. First implementation slice to build immediately

### Slice goal

Prove the architecture boundary before real media complexity: a local runtime-owned queued job can be created over REST, persisted to SQLite, started by the runtime scheduler, moved through a stubbed execution pipeline, and observed over WebSocket even if the browser disconnects and reconnects.

### Slice contents

1. Scaffold `app/main.py`, `app/config.py`, `app/runtime/controller.py`, `app/runtime/scheduler.py`, `app/runtime/state_machine.py`, `app/api/server.py`, `app/api/routes_runtime.py`, `app/api/routes_jobs.py`, `app/api/websocket.py`, `app/persistence/db.py`, `app/persistence/schema.sql`, and corresponding tests.
2. Implement SQLite tables for `jobs`, `job_events`, `settings`, and minimal `system_volumes`.
3. Implement token auth from `.env.example` values and `GET /api/runtime/status`, `GET /api/volumes`, `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/command`, and `/ws/events`.
4. Implement the explicit state machine and single-active-job scheduler with a stubbed pipeline (`SCANNING -> PREPARING -> COPYING -> VERIFYING -> REPORTING`) using timers and event emission instead of real file I/O.
5. Implement restart recovery for `QUEUED` and `PAUSED` jobs using SQLite only.

### Slice acceptance criteria

- Creating a job through REST writes `jobs` plus `job_events` and returns a durable `job_id`.
- Only one job can enter active execution while later jobs remain `QUEUED`.
- WebSocket clients receive ordered `job.created`, `job.state`, `job.progress`, and `job.command` events.
- Closing the browser does not stop the stubbed job; reconnecting and calling REST returns the correct current state.
- `pause`, `resume`, and `cancel` follow the state machine exactly and persist accepted/rejected command results.

## Verification plan for execution phase

- Unit tests
  - state transition rules
  - repository read/write behavior
  - command acceptance/rejection logic
- Integration tests
  - REST plus WebSocket behavior against a temp SQLite DB
  - restart recovery from persisted rows
  - single active job enforcement
- Runtime fixture tests
  - scan/copy/verify against temporary directories
  - BRAW parse/capture against approved sample media
- Console tests
  - reconnect hydration
  - no browser-side file access patterns in code review and static grep

## Recommended execution order

1. Build the runtime/persistence/control-plane scaffold and prove disconnect-safe state ownership.
2. Add real scan/copy/checksum behavior with file-level persistence.
3. Add BRAW parse and capture adapters behind the parser contract.
4. Add report generation once capture viability is proven.
5. Add the responsive web console and optional minimal local panel last.
