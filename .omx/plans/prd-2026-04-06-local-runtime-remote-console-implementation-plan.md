# Footage Data Manager v1 Implementation Plan

Date: 2026-04-06
Source of truth: `Footage_DataManager_Spec_v2_2_Local_Runtime_Remote_Console.md`

## Requirements Summary

- The execution authority must be the macOS local runtime, not the browser, and real file work must stay local-only. Source: spec lines 16-20, 32-36, 51-57, 78-85, 126-151, 587-593.
- The remote web app must be a control and monitoring console that talks only through REST plus WebSocket state/events. Source: spec lines 33-36, 55-57, 81, 139-142, 159-161, 166-209, 422-462.
- Browser disconnect must not stop active work; reconnect must recover by REST snapshot plus WebSocket resubscribe. Source: spec lines 36, 121-122, 206-209, 393, 581-583.
- v1 scope is limited to BRAW, volume detection, scan, offload, checksum verification, metadata parsing, report generation, and remote monitoring/control. Native iOS, multi-format, complex auth, and concurrent active offloads are out of scope. Source: spec lines 14, 72, 83-85, 241-260, 314-318, 556-564.
- Persistence must use SQLite and retain jobs, events, file-level results, clip metadata, reports, settings, and volume information. Source: spec lines 82, 191, 322-342.
- The runtime must enforce an explicit single-active-job state machine and support recovery for queued, paused, warn, and failed jobs after restart. Source: spec lines 82-83, 275-318, 566-583.
- v1 output artifacts must include checksum PDF, image PDF, metadata XLSX, and `manifest.json`. Source: spec lines 98, 248, 326-330, 558-562.

## Current Repo Status Summary

- Repository is effectively greenfield. `git ls-files` returned no tracked files, and `git log` reports that `main` has no commits yet.
- Root contents are limited to the source-of-truth spec, `.env.example`, `.gitignore`, local virtualenv directories, and `.omx/` state. There is no existing app, API, DB schema, parser, UI, or test suite to adapt.
- The only stack clues are Python-oriented: `.venv/pyvenv.cfg` points to Python 3.13.12, `.gitignore` excludes Python caches, and `.env.example` already defines host/port/token knobs (`FDM_HOST`, `FDM_PORT`, `FDM_TOKEN`). Source: `.venv/pyvenv.cfg`, `.gitignore` lines 1-10, `.env.example` lines 1-4.
- Reusable modules: none.
- Immediate blockers:
  - BRAW metadata/frame-capture dependency is unspecified in the repo and must be validated locally before the image-report path can be declared done.
  - There is no existing persistence, recovery, or event model, so runtime state must be designed before copy logic.
- Spec ambiguity that must be normalized up front:
  - `PAUSED_BY_DEVICE_ERROR` appears in operational policy but is not part of the formal state table. Safest assumption: v1 keeps the formal persisted states in spec section 2.9.2 and encodes device errors as `FAILED` or `PAUSED` with a `reason_code=device_error` event, rather than inventing a new persisted state. Source: spec lines 293-310 and 387-395.

## Acceptance Criteria

- `POST /api/jobs` creates a queued job using only runtime-discovered source/destination IDs; no browser-supplied absolute paths are accepted.
- Exactly one job can be active in `SCANNING` through `REPORTING` at a time; later jobs remain `QUEUED`.
- Runtime restart recovers `QUEUED`, `PAUSED`, `WARN`, and `FAILED` jobs and marks interrupted in-flight jobs recoverable with explicit event history.
- File-level checksum results are stored in SQLite for source, main, and backup copies.
- Parsed BRAW metadata is stored in SQLite and queryable via API.
- WebSocket clients can observe progress, speed, ETA, warnings, errors, state changes, and command acknowledgements in real time.
- Closing the browser does not interrupt runtime processing.
- `app/web_console/` contains no direct filesystem access logic, OS picker calls, Electron/Tauri APIs, or arbitrary path submission behavior.
- A completed v1 job produces `checksum.pdf`, `image.pdf`, `metadata.xlsx`, and `manifest.json`, or lands in `WARN`/`FAILED` with explicit reasons and preserved partial artifacts.

## Architecture Proposal

### Chosen shape

- Build one local macOS process that contains:
  - a `runtime` service layer that owns all filesystem, job, parser, report, and recovery work
  - an `api` layer exposing REST plus WebSocket as the only remote interface
  - a `web_console` static client served by the API layer
  - an optional `local_panel` that talks to the same runtime service and never becomes a second full product
- Keep the architectural boundaries strict even if the v1 implementation runs in one OS process. This is the simplest equivalent to the spec's four-layer model and avoids unnecessary IPC before stability is proven. Source: spec lines 153-209 and 509-549.

### Runtime boundary

- `runtime` is the only module allowed to:
  - enumerate `/Volumes`
  - resolve approved destination roots
  - open file handles
  - copy bytes
  - compute checksums
  - invoke BRAW/ffmpeg tooling
  - write logs, temp files, reports, and manifest output
- `api` can request commands and read persisted state, but it cannot manipulate filesystem paths directly. It passes only IDs and validated user intent strings.
- `web_console` can only call `fetch` and `WebSocket`; it cannot import Python, Node `fs`, Electron/Tauri bridges, or browser file-system APIs.

### Runtime execution model

- `RuntimeAgent` owns:
  - startup dependency probe
  - volume monitor poller
  - scheduler with single active job slot
  - active job runner
  - state machine guard
  - recovery reconciler
  - event broadcaster
- Heavy work stays off the request path. REST handlers enqueue commands to the runtime and return quickly; the runtime processes long-running work in background tasks/worker threads.

### Persistence model

- SQLite is the system of record for jobs, events, file results, clips, reports, settings, and recent volume state.
- Report files, logs, and temporary capture artifacts live under a runtime-controlled app data root; the DB stores indexed relative paths, not browser-provided paths.
- Browser reconnect flow:
  1. `GET /api/runtime/status`
  2. `GET /api/jobs` or `GET /api/jobs/{id}`
  3. reconnect `WebSocket`
  4. render new events on top of the REST snapshot

### Security/auth model

- v1 uses a single bearer token from env/settings, consistent with the spec's simple-auth allowance. Source: spec lines 260 and 435.
- All mutating REST endpoints require the token.
- Report downloads are by `report_id` only; the API resolves the actual file path inside a controlled artifact root.

### Safest explicit assumptions

- Checksum algorithm for v1: SHA-256, because the spec requires checksum verification but does not fix an algorithm.
- Volume detection strategy for v1: poll `/Volumes` plus configured destination roots every few seconds instead of using a more complex native event stack first.
- Pause is supported only during `COPYING`, because that is the only stage where the spec explicitly grants `pause`. Requests during other active stages are rejected with a logged command result. Source: spec lines 297-306.
- Retry creates a new queued attempt linked to the original job, instead of mutating terminal history in place. This preserves auditability and matches the spec's "new retry" language for cancelled work. Source: spec lines 309 and 394.

## Exact Module/File Plan

```text
app/
├─ __init__.py
├─ main.py
├─ config.py
├─ logging.py
├─ runtime/
│  ├─ __init__.py
│  ├─ agent.py
│  ├─ scheduler.py
│  ├─ state_machine.py
│  ├─ recovery.py
│  ├─ commands.py
│  ├─ volume_monitor.py
│  ├─ scan.py
│  ├─ offload.py
│  ├─ checksum.py
│  ├─ parse.py
│  ├─ capture.py
│  ├─ reports.py
│  ├─ dependencies.py
│  └─ events.py
├─ api/
│  ├─ __init__.py
│  ├─ server.py
│  ├─ deps.py
│  ├─ schemas.py
│  ├─ routes_runtime.py
│  ├─ routes_volumes.py
│  ├─ routes_jobs.py
│  ├─ routes_logs.py
│  ├─ routes_reports.py
│  ├─ routes_settings.py
│  └─ websocket.py
├─ persistence/
│  ├─ __init__.py
│  ├─ db.py
│  ├─ migrations.py
│  ├─ schema.sql
│  ├─ models.py
│  ├─ repositories.py
│  └─ manifests.py
├─ parsers/
│  ├─ __init__.py
│  ├─ base.py
│  ├─ registry.py
│  ├─ types.py
│  └─ braw_parser.py
├─ web_console/
│  ├─ index.html
│  ├─ app.js
│  ├─ api.js
│  ├─ ws.js
│  ├─ state.js
│  └─ styles.css
└─ local_panel/
   ├─ __init__.py
   └─ minimal_panel.py

tests/
├─ fixtures/
│  ├─ volume_samples/
│  ├─ manifest_samples/
│  └─ report_samples/
├─ unit/
│  ├─ runtime/test_state_machine.py
│  ├─ runtime/test_scheduler.py
│  ├─ runtime/test_command_rules.py
│  ├─ persistence/test_repositories.py
│  └─ parsers/test_braw_parser_contract.py
├─ integration/
│  ├─ api/test_runtime_status.py
│  ├─ api/test_jobs_routes.py
│  ├─ api/test_websocket_events.py
│  ├─ runtime/test_recovery.py
│  ├─ runtime/test_single_active_job.py
│  └─ runtime/test_report_indexing.py
└─ system/
   ├─ test_no_web_filesystem_access.py
   └─ test_browser_disconnect_runtime_continues.py

requirements.txt
requirements-dev.txt
README.md
```

### File ownership by module

- `app/main.py`: local bootstrap entrypoint; wires config, DB migration, runtime startup, and FastAPI lifespan.
- `app/runtime/*`: all execution authority, including job orchestration and file I/O.
- `app/api/*`: translation layer from REST/WS to runtime commands and persisted read models.
- `app/persistence/*`: SQLite connection policy, schema bootstrapping, repositories, manifest output helper.
- `app/parsers/*`: pluggable parser contract; only `braw_parser.py` is implemented in v1.
- `app/web_console/*`: static remote console assets; no filesystem APIs.
- `app/local_panel/minimal_panel.py`: optional later, limited to status/controls already exposed by runtime.

## Data Model / SQLite Table Plan

### `jobs`

- `job_id TEXT PRIMARY KEY`
- `retry_of_job_id TEXT NULL`
- `project_name TEXT NOT NULL`
- `source_volume_id TEXT NOT NULL`
- `dest_main_id TEXT NOT NULL`
- `dest_backup_id TEXT NULL`
- `state TEXT NOT NULL`
- `current_step TEXT NOT NULL`
- `resume_step TEXT NULL`
- `operator_origin TEXT NOT NULL`
- `policy_json TEXT NOT NULL`
- `stats_json TEXT NOT NULL`
- `warning_count INTEGER NOT NULL DEFAULT 0`
- `error_count INTEGER NOT NULL DEFAULT 0`
- `current_file_relpath TEXT NULL`
- `created_at TEXT NOT NULL`
- `started_at TEXT NULL`
- `ended_at TEXT NULL`
- `last_event_id INTEGER NOT NULL DEFAULT 0`

Purpose: authoritative high-level job row used by scheduler, recovery, API list/detail views.

### `job_events`

- `event_id INTEGER PRIMARY KEY AUTOINCREMENT`
- `job_id TEXT NOT NULL`
- `event_type TEXT NOT NULL`
- `level TEXT NOT NULL`
- `from_state TEXT NULL`
- `to_state TEXT NULL`
- `command_name TEXT NULL`
- `command_status TEXT NULL`
- `origin TEXT NOT NULL`
- `reason_code TEXT NULL`
- `message TEXT NOT NULL`
- `payload_json TEXT NOT NULL`
- `created_at TEXT NOT NULL`

Purpose: complete audit trail for state transitions, command requests, command acceptance/rejection, warnings, failures, and report generation outcomes.

### `job_files`

- `job_file_id INTEGER PRIMARY KEY AUTOINCREMENT`
- `job_id TEXT NOT NULL`
- `relative_path TEXT NOT NULL`
- `size_bytes INTEGER NOT NULL`
- `parser_name TEXT NULL`
- `source_checksum_sha256 TEXT NULL`
- `main_checksum_sha256 TEXT NULL`
- `backup_checksum_sha256 TEXT NULL`
- `copy_main_state TEXT NOT NULL`
- `copy_backup_state TEXT NOT NULL`
- `verify_main_state TEXT NOT NULL`
- `verify_backup_state TEXT NOT NULL`
- `parse_state TEXT NOT NULL`
- `capture_state TEXT NOT NULL`
- `warning_code TEXT NULL`
- `error_code TEXT NULL`
- `metadata_json TEXT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Purpose: file-level copy/verify/parse/capture evidence and recovery checkpoint data.

### `clips`

- `clip_id TEXT PRIMARY KEY`
- `job_id TEXT NOT NULL`
- `job_file_id INTEGER NOT NULL`
- `format_name TEXT NOT NULL`
- `parser_version TEXT NOT NULL`
- `clip_name TEXT NULL`
- `reel_name TEXT NULL`
- `camera_id TEXT NULL`
- `codec TEXT NULL`
- `resolution_width INTEGER NULL`
- `resolution_height INTEGER NULL`
- `fps REAL NULL`
- `duration_frames INTEGER NULL`
- `timecode_start TEXT NULL`
- `shot_date TEXT NULL`
- `iso_value INTEGER NULL`
- `white_balance_kelvin INTEGER NULL`
- `lens_json TEXT NULL`
- `raw_metadata_json TEXT NOT NULL`
- `parsed_at TEXT NOT NULL`

Purpose: queryable normalized metadata for BRAW clips plus raw metadata payload retention.

### `reports`

- `report_id TEXT PRIMARY KEY`
- `job_id TEXT NOT NULL`
- `report_type TEXT NOT NULL`
- `status TEXT NOT NULL`
- `relative_path TEXT NOT NULL`
- `size_bytes INTEGER NULL`
- `created_at TEXT NOT NULL`

Purpose: track artifact generation and expose report lists/downloads without browser path access.

### `system_volumes`

- `volume_id TEXT PRIMARY KEY`
- `display_name TEXT NOT NULL`
- `mount_path TEXT NOT NULL`
- `volume_role TEXT NOT NULL`
- `is_removable INTEGER NOT NULL`
- `filesystem_type TEXT NULL`
- `capacity_bytes INTEGER NULL`
- `free_bytes INTEGER NULL`
- `serial_hint TEXT NULL`
- `approval_state TEXT NOT NULL`
- `last_seen_at TEXT NOT NULL`
- `metadata_json TEXT NOT NULL`

Purpose: recent runtime-observed source and destination inventory for `/api/volumes`.

### `settings`

- `key TEXT PRIMARY KEY`
- `value_json TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Initial keys:

- `auth.token_hash`
- `runtime.allowed_destination_roots`
- `runtime.poll_interval_sec`
- `reports.output_root`
- `runtime.default_checksum_algorithm`

### SQLite implementation notes

- Use stdlib `sqlite3` first to minimize moving parts.
- Enable `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, and busy timeouts at startup.
- Track schema upgrades via `PRAGMA user_version` plus versioned SQL in `app/persistence/schema.sql` and `migrations.py`.

## API Endpoint Plan

### `GET /api/runtime/status`

Returns:

- runtime health
- version/build string
- active job id/state
- dependency status for BRAW parser and frame capture
- queue depth
- last startup time

### `GET /api/volumes`

Returns:

- detected source volumes
- approved destination roots/volumes
- availability flags
- free space summary

Rules:

- browser receives volume IDs, labels, and safe summary info
- browser never receives authority to browse arbitrary paths

### `POST /api/jobs`

Request body:

- `project_name`
- `source_volume_id`
- `dest_main_id`
- `dest_backup_id`
- `policy` object with retry mode / exclusions / optional relative naming choices

Rules:

- reject raw absolute paths
- reject if source/destination ids are not currently known and approved
- always persist as `QUEUED`
- return created `job_id`

### `GET /api/jobs`

Supports:

- current active job
- queued jobs
- recent terminal jobs
- optional state filter

### `GET /api/jobs/{id}`

Returns:

- full job summary
- current step/state
- progress stats
- destination summary
- warning/error counts
- recovery hints

### `GET /api/jobs/{id}/logs`

Returns:

- normalized event/log feed from `job_events`
- optional filters by level, event_type, time range

### `GET /api/jobs/{id}/reports`

Returns:

- report metadata rows from `reports`
- `download_url` values keyed by `report_id`

### `POST /api/jobs/{id}/command`

Accepted commands:

- `pause`
- `resume`
- `cancel`
- `retry`
- `refresh` is client-side only and should not be implemented as a runtime command

Rules:

- runtime validates command against current state machine
- response includes `accepted: true|false`
- acceptance/rejection is also persisted in `job_events`

### `GET /api/clips`

Supports:

- filtering by `job_id`
- pagination
- optional clip name / reel / timecode filters

### `GET /api/settings`

Returns:

- non-secret runtime settings
- dependency/readiness flags

### `PATCH /api/settings`

Allows:

- allowed destination roots
- poll interval
- UI preferences
- token rotation

Rules:

- secrets are write-only where applicable
- all changes are audited in logs/events

### Additional report content endpoint required for UX completeness

- `GET /api/reports/{report_id}/content`

Reason:

- the spec requires report access/download, but list-only endpoints are insufficient. This route remains safe because the browser passes only `report_id`, never a filesystem path.

## WebSocket Event Plan

### Endpoint

- `GET /ws/events`

### Connection behavior

- token-authenticated
- stateless subscription
- client reconnects after disconnect and refetches REST snapshots before relying on new events
- server sends heartbeat every few seconds to keep idle connections visible

### Event envelope

```json
{
  "event_id": 1823,
  "type": "job.progress",
  "timestamp": "2026-04-06T20:45:00Z",
  "job_id": "JOB-20260406-001",
  "payload": {}
}
```

### Event types

- `runtime.status`
- `volume.changed`
- `job.created`
- `job.state_changed`
- `job.progress`
- `job.command_result`
- `job.log`
- `job.report_ready`
- `job.recovery_notice`

### `job.progress` payload contract

Payload retains the progress fields shown in the spec example:

- `state`
- `current_file`
- `processed_files`
- `total_files`
- `bytes_done`
- `bytes_total`
- `speed_mbps`
- `eta_sec`
- `warnings`
- `errors`
- `message`

Source: spec lines 437-455.

### Ordering and replay

- `event_id` is monotonic and persisted in `job_events`.
- v1 reconnect strategy does not require full WebSocket replay. Instead:
  - use REST to rebuild current truth
  - use WebSocket only for new deltas after reconnect

## Job State Machine Plan

### Persisted states

- `QUEUED`
- `SCANNING`
- `PREPARING`
- `COPYING`
- `PAUSING`
- `PAUSED`
- `VERIFYING`
- `PARSING`
- `CAPTURING`
- `REPORTING`
- `WARN`
- `FAILED`
- `CANCELLED`
- `COMPLETED`

Source: spec lines 293-310.

### Primary happy-path transitions

- `QUEUED -> SCANNING`
- `SCANNING -> PREPARING`
- `PREPARING -> COPYING`
- `COPYING -> VERIFYING`
- `VERIFYING -> PARSING`
- `PARSING -> CAPTURING`
- `CAPTURING -> REPORTING`
- `REPORTING -> COMPLETED`

### Controlled alternative transitions

- `COPYING -> PAUSING -> PAUSED`
- `PAUSED -> COPYING` if copy stage was interrupted
- `PAUSED -> VERIFYING|PARSING|CAPTURING|REPORTING` only if a later stage is ever made pausable in a future version; not supported in v1
- any active stage -> `FAILED` on unrecoverable error
- `REPORTING -> WARN` when work completed with recoverable/partial failures
- `QUEUED -> CANCELLED`
- `PAUSED -> CANCELLED`

### Command acceptance matrix

- `cancel`: allowed in `QUEUED`, `SCANNING`, `PREPARING`, `COPYING`, `PAUSED`, `VERIFYING`, `PARSING`, `CAPTURING`, `REPORTING`
- `pause`: allowed only in `COPYING`
- `resume`: allowed only in `PAUSED`
- `retry`: allowed only from terminal `WARN`, `FAILED`, `CANCELLED`, `COMPLETED`

### Retry semantics

- Retry creates a new `QUEUED` job with `retry_of_job_id` pointing to the original job.
- Two retry modes:
  - `failed_files_only`
  - `full_job`

### Crash recovery semantics

- On startup:
  - keep `QUEUED` as `QUEUED`
  - keep `PAUSED` as `PAUSED`
  - leave `WARN` and `FAILED` retryable
  - mark interrupted active states (`SCANNING` through `REPORTING`, plus `PAUSING`) as `FAILED` with `reason_code=runtime_interrupted`
- For interrupted copy jobs, recovery inspects partial destination files before allowing retry mode selection. Source: spec lines 317-318.

## Phased Milestone Plan

### P0: Runtime Core, Persistence, State Machine, BRAW Metadata Contract

Deliverables:

- project scaffold and bootable local process
- SQLite schema, migrations, repositories
- runtime agent, scheduler, state machine, recovery reconciler
- volume monitor using `/Volumes` polling
- `runtime/status`, `volumes`, `jobs`, `jobs/{id}`, `jobs/{id}/command` REST surfaces
- WebSocket event hub with `runtime.status`, `job.state_changed`, `job.progress`, `job.command_result`
- BRAW parser contract and metadata-only proof path
- single active job enforcement

Exit criteria:

- queued jobs persist across restarts
- command validation follows the state machine
- browser disconnect has no effect on active runtime task ownership

### P0.5: BRAW Frame Capture Proof Gate

Deliverables:

- confirm local dependency path for BRAW frame extraction on macOS
- implement `capture.py` adapter behind parser contract
- persist capture success/failure per file

Exit criteria:

- one representative BRAW clip can produce first/middle/last frame images locally
- failure modes are explicit and do not crash the full job pipeline

### P1: Real Offload, Verify, Reports, Remote Console

Deliverables:

- source scan manifest creation
- main and backup copy orchestration
- SHA-256 checksum generation/verification stored in `job_files`
- metadata parse persistence in `clips`
- report generation: checksum PDF, image PDF, metadata XLSX, `manifest.json`
- remote web console screens: home, job detail, queue, reports, settings
- log views and report download flow

Exit criteria:

- one BRAW card set completes main+backup offload
- file-level checksum evidence is persisted
- clip metadata is queryable
- reports are indexed and downloadable by report id

### P2: Optional Local Operator Panel and Packaging

Deliverables:

- minimal local operator panel
- runtime status, dependency health, emergency stop/restart, open logs/reports actions
- packaging/distribution decisions for macOS local deployment

Exit criteria:

- local panel adds operational convenience without duplicating remote-console feature parity

## Top Technical Risks and Mitigation

### 1. BRAW metadata and frame-capture tooling may be brittle or unavailable

Mitigation:

- treat parser/capture dependency probing as part of runtime startup status
- complete P0.5 before report-generation work is considered stable
- keep parser behind a strict interface so fallback behavior is contained

### 2. Crash-safe copy plus checksum resume is the hardest correctness path

Mitigation:

- persist per-file copy/verify states in `job_files`
- flush `job_events` before and after every state transition
- normalize interrupted active jobs into explicit recoverable terminal states on startup

### 3. Volume detection can be flaky with removable/network media on macOS

Mitigation:

- start with polling rather than complex native watchers
- track `last_seen_at`, capacity, and approval state in `system_volumes`
- reject job creation if the selected source/destination is no longer present

### 4. API responsiveness can degrade if runtime work shares the request thread

Mitigation:

- keep copy/checksum/parser/report work in background runtime workers
- use the API layer only for lightweight validation plus command submission
- expose runtime health in `/api/runtime/status` so contention is visible

### 5. Web console could accidentally grow filesystem authority

Mitigation:

- accept only IDs in mutating APIs
- serve report content by `report_id`
- add a system test that scans `app/web_console/` for forbidden filesystem APIs and absolute-path submission patterns

## Verification Steps

- Unit-test the state machine transition table and command acceptance matrix.
- Unit-test repository CRUD and crash-recovery normalization.
- Integration-test single-active-job scheduling with two queued jobs.
- Integration-test REST create/list/detail/command endpoints against a temp SQLite DB.
- Integration-test WebSocket progress and command-result events.
- System-test that browser disconnect does not stop the runtime worker.
- System-test that `app/web_console/` does not contain direct filesystem access code.
- End-to-end test with representative BRAW fixture or local staging media for:
  - scan
  - main+backup copy
  - checksum verify
  - metadata parse
  - frame capture
  - report generation

## First Implementation Slice To Build Immediately

### Slice name

Runtime skeleton + persistence + state machine + remote control shell

### Why this is first

- The spec prioritizes runtime authority, persistence, and resumability ahead of UI polish or extra features. Source: spec lines 78-85, 82, 153-209, 275-349, 552-564.
- Without the DB schema, state machine, scheduler, and command/event contracts, later copy/parser/report work will be unstable and hard to recover.

### Files in the first slice

- `requirements.txt`
- `requirements-dev.txt`
- `app/main.py`
- `app/config.py`
- `app/runtime/agent.py`
- `app/runtime/scheduler.py`
- `app/runtime/state_machine.py`
- `app/runtime/recovery.py`
- `app/runtime/commands.py`
- `app/runtime/events.py`
- `app/runtime/volume_monitor.py`
- `app/api/server.py`
- `app/api/schemas.py`
- `app/api/routes_runtime.py`
- `app/api/routes_volumes.py`
- `app/api/routes_jobs.py`
- `app/api/websocket.py`
- `app/persistence/db.py`
- `app/persistence/migrations.py`
- `app/persistence/schema.sql`
- `app/persistence/repositories.py`
- `tests/unit/runtime/test_state_machine.py`
- `tests/unit/runtime/test_scheduler.py`
- `tests/integration/api/test_jobs_routes.py`
- `tests/integration/api/test_websocket_events.py`

### Slice acceptance criteria

- app boots and migrates SQLite automatically
- runtime status endpoint reports healthy boot plus dependency placeholders
- volume endpoint returns runtime-discovered volumes and approved destination roots
- job creation persists `QUEUED` rows and emits `job.created`
- scheduler enforces one active job slot
- command endpoint accepts/rejects by explicit state rules
- WebSocket clients receive state and command-result events
- restart reloads queued/paused/warn/failed jobs from SQLite

### What is intentionally deferred from slice 1

- real BRAW parsing
- real byte copy
- checksum execution
- frame capture
- report builders
- full web-console UX

These arrive only after the runtime contract is locked and tested.
