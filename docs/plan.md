# Footage Data Manager Plan

Working root: `~/desktop/datamanager`.

## Architecture

The system has three boundaries:

- macOS local runtime: the only executor for volume detection, scans, copy/offload, checksum, parser execution, frame capture, report generation, SQLite writes, local logs, temp files, and recovery.
- API/sync layer: REST and WebSocket transport, auth, request validation, command dispatch, and state/event delivery.
- Remote web console: browser UI that creates jobs, observes runtime state, reads logs/reports, and submits commands through REST/WebSocket only.

The web console must not directly access local files, invoke OS file pickers for source/destination selection, copy media, calculate checksums, run parsers, run external binaries, or write arbitrary paths.

## Milestones And Gates

| Stage | Output | Gate |
|---|---|---|
| 0 | Durable docs, rules, boundaries, stage map | Stage 0 file/grep validation PASS |
| 1 | Runnable repo shell and validation tooling | Lint, format, typecheck, tests, build, local app, API curl, Playwright smoke PASS |
| 2 | Architecture and milestone contracts | Docs/contracts align with source of truth and Stage 2 validation PASS |
| 3 | Foundation runtime/API/persistence/UI shell | Foundation tests and validation PASS |
| 4.1 | Sprint 0 BRAW capability gate | Contract, implementation, evaluator PASS |
| 4.2 | Sprint 1 state machine and persistence | Contract, implementation, evaluator PASS |
| 4.3 | Sprint 2 offload and checksum pipeline | Contract, implementation, evaluator PASS |
| 4.4 | Sprint 3 parsing, frame capture, reports | Contract, implementation, evaluator PASS |
| 4.5 | Sprint 4 API, WebSocket, command layer | Contract, implementation, evaluator PASS |
| 4.6 | Sprint 5 remote web console UX | Contract, implementation, evaluator PASS |
| 4.7 | Sprint 6 recovery, resilience, local panel | Contract, implementation, evaluator PASS |
| 5 | UI/UX refinement | UI, accessibility, responsive validation PASS |
| 6 | Hardening | Security, failure, performance, and scenario validation PASS |
| 7 | Release wrap-up | Handoff docs, demo path, final validation PASS |

Do not advance before the active stage gate is green.

## Acceptance Criteria

- The local runtime owns every real file operation.
- The web console consumes REST and WebSocket only.
- One BRAW card set can be offloaded to main and backup destinations.
- File-level checksum results are persisted.
- Metadata and frame capture outputs are included in reports when capability is available.
- Browser UI shows progress, speed, ETA, errors, logs, and report links in real time.
- Pause, resume, cancel, and retry follow the state machine.
- Browser disconnect does not stop runtime work.
- Restart recovery handles queued, paused, warning, and failed jobs.

## Validation Matrix

| Area | Evidence |
|---|---|
| Boundary | Static checks and tests proving no web console direct filesystem access |
| Runtime | Unit/integration tests for jobs, queue, state transitions, copy/checksum, recovery |
| API | REST and WebSocket tests for auth, commands, state, logs, reports |
| UI | Playwright smoke and responsive checks |
| Reports | Tests for manifest, PDF/XLSX generation, and failure reporting |
| Quality | Ruff, format check, MyPy, Pytest, build, scenario validation |

## Risks

- BRAW SDK, sample media, and licensing may be unavailable.
- macOS `/Volumes` behavior and permissions require careful runtime-only handling.
- Partial-copy recovery can corrupt state if checkpointing is weak.
- Large media may expose throughput and checksum bottlenecks.
- Packaging may require external signing credentials or bundled binary decisions.
- v1 token auth is not appropriate for public internet exposure.

## Documented Assumptions

- Use canonical job states first; represent device-error details with reason/error codes unless a later contract justifies a new state.
- Use a static web console served by FastAPI unless later validation proves a frontend build tool is necessary.
- Use mocks or capability-unavailable states for BRAW integrations when real SDK/media are absent.

## Request Flow Contract

Browser to API to runtime to persistence to WebSocket to browser:

1. The web console reads runtime status, volumes, jobs, logs, reports, clips, and settings through REST.
2. The web console submits job creation or command requests through REST using runtime-provided IDs, not raw arbitrary local paths.
3. The API authenticates and validates the request shape, then forwards an accepted request to the local runtime service boundary.
4. The local runtime checks state, policy, and file authority before it mutates anything.
5. The local runtime writes jobs, events, file results, clips, reports, settings, and volumes to SQLite.
6. The API/WebSocket layer publishes the persisted state/event update.
7. The browser updates UI from REST snapshots and WebSocket deltas only.

## Module Ownership Boundaries

| Module | Owns | Must not own |
|---|---|---|
| `app/runtime/` | state machine, scheduler, scan, copy, checksum, parser/capture orchestration, recovery decisions | HTTP response formatting or browser UI state |
| `app/persistence/` | SQLite connections, schema/migrations, repositories, manifest writes requested by runtime | job policy decisions or direct web console access |
| `app/parsers/` | runtime-only parser protocol, BRAW capability adapter, mock fixtures | REST endpoints or browser execution |
| `app/api/` | auth, REST, WebSocket, schemas, command request validation, static console serving | direct copy/checksum/parser execution |
| `app/web_console/` | rendering REST snapshots, WebSocket events, command forms, responsive UI state | local file access, OS pickers, checksum, parser calls, arbitrary path writes |
| `app/local_panel/` | optional minimal local status/emergency view | full duplicate product surface or separate executor |
| `tests/` | unit, integration, system, Playwright, fixture media/mocks | production behavior not represented in app modules |

## State Transition Matrix

| Current state | Runtime transition | Remote command acceptance |
|---|---|---|
| `QUEUED` | `SCANNING`, `CANCELLED` | `cancel` accepted; `pause`, `resume`, `retry` rejected |
| `SCANNING` | `PREPARING`, `FAILED`, `CANCELLED` | `cancel` accepted; others rejected |
| `PREPARING` | `COPYING`, `FAILED`, `CANCELLED` | `cancel` accepted; others rejected |
| `COPYING` | `PAUSING`, `VERIFYING`, `WARN`, `FAILED`, `CANCELLED` | `pause` and `cancel` accepted; `resume`, `retry` rejected |
| `PAUSING` | `PAUSED`, `FAILED` | commands rejected until stable |
| `PAUSED` | `COPYING`, `CANCELLED` | `resume` and `cancel` accepted; `pause`, `retry` rejected |
| `VERIFYING` | `PARSING`, `WARN`, `FAILED`, `CANCELLED` | `cancel` accepted; others rejected |
| `PARSING` | `CAPTURING`, `REPORTING`, `WARN`, `FAILED`, `CANCELLED` | `cancel` accepted; others rejected |
| `CAPTURING` | `REPORTING`, `WARN`, `FAILED`, `CANCELLED` | `cancel` accepted; others rejected |
| `REPORTING` | `COMPLETED`, `WARN`, `FAILED`, `CANCELLED` | `cancel` accepted; others rejected |
| `WARN` | `QUEUED`, `REPORTING`, `COMPLETED`, `FAILED` | `retry` accepted; `cancel` rejected after terminal artifact finalization |
| `FAILED` | `QUEUED` | `retry` accepted when policy and inputs are still available |
| `CANCELLED` | terminal | all mutating commands rejected |
| `COMPLETED` | terminal | mutating commands rejected; future re-run is a new job |

Device-error detail should be recorded as an event reason/error code while preserving the canonical state list unless a sprint contract explicitly changes it.

## Milestone Implementation Plan

### Milestone 3.1 - Foundation Contracts In Code

Scope: add shared schemas/enums, runtime service interfaces, repository placeholders, and test fixtures that mirror the contracts.

Out-of-scope: real BRAW probing, copy/checksum workers, reports, and browser command flows.

Touched modules/files: `app/api/schemas.py`, `app/runtime/`, `app/persistence/`, `tests/fixtures/`, `docs/implement.md`.

Acceptance criteria: code-level state/command constants match docs; tests prove command rejection defaults are conservative.

Validation commands: `ruff check .`, `ruff format --check .`, `mypy app`, `pytest -q`.

Rollback/risk notes: keep schema additions additive; no migration data risk.

### Milestone 4.1 - Sprint 0 BRAW Capability Gate

Scope: parser protocol, BRAW adapter boundary, mock adapter, capability status, and evaluator proving no fake real-media support.

Out-of-scope: offload pipeline and report generation.

Touched modules/files: `app/parsers/`, `app/runtime/dependencies.py`, `app/api/routes_runtime.py`, `tests/support/`, `docs/qa/sprint-0-braw-gate-*.md`.

Acceptance criteria: real SDK absence is reported as unavailable/unknown; mock fixtures cover metadata/capture contract; web console cannot call parser directly.

Validation commands: baseline quality commands, parser unit tests, capability API tests, boundary static test.

Rollback/risk notes: adapter must remain swappable; never hardcode fake SDK success.

### Milestone 4.2 - Sprint 1 Runtime State Machine And Persistence

Scope: job lifecycle, command acceptance/rejection, SQLite repositories, append-only events, single active queue, recovery candidates.

Out-of-scope: actual media copy, parser execution, UI polish.

Touched modules/files: `app/runtime/state_machine.py`, `app/runtime/scheduler.py`, `app/persistence/`, `tests/unit/runtime/`, `tests/unit/persistence/`.

Acceptance criteria: every documented state transition and command decision is tested; recoverable states are queryable.

Validation commands: baseline quality commands plus state-machine and repository tests.

Rollback/risk notes: migrations must be forward-only during this sprint; schema changes require tests.

### Milestone 4.3 - Sprint 2 Offload And Checksum Pipeline

Scope: source scan, destination folder planning, main/backup copy, checksum verification, file result persistence, failure/warn policy.

Out-of-scope: metadata parse, frame capture, PDF/XLSX reports, remote console UX.

Touched modules/files: `app/runtime/scan.py`, `app/runtime/offload.py`, `app/runtime/checksum.py`, `app/persistence/repositories.py`, `tests/integration/runtime/`.

Acceptance criteria: fixture files copy to main/backup; mismatches create file-level failures; web console still only observes API state.

Validation commands: baseline quality commands, offload integration tests, no-web-filesystem-access test.

Rollback/risk notes: tests use temporary directories; never touch arbitrary real volumes in automated tests.

### Milestone 4.4 - Sprint 3 Parsing, Capture, And Reports

Scope: metadata parse orchestration, frame capture gate, checksum PDF, image PDF, metadata XLSX, manifest relationships.

Out-of-scope: new browser features beyond report listing contracts.

Touched modules/files: `app/runtime/parse.py`, `app/runtime/capture.py`, `app/runtime/reports.py`, `app/persistence/manifests.py`, `tests/integration/runtime/`.

Acceptance criteria: report artifacts are generated from persisted runtime data; unavailable capture is honestly represented.

Validation commands: baseline quality commands plus artifact content tests.

Rollback/risk notes: report outputs must be deterministic in tests and linked from `reports`.

### Milestone 4.5 - Sprint 4 API, WebSocket, And Command Layer

Scope: REST endpoints, token auth, command routes, WebSocket snapshots/deltas, logs/reports/clips/settings routes.

Out-of-scope: UI polish and new runtime execution features.

Touched modules/files: `app/api/`, `tests/integration/api/`, `tests/system/`.

Acceptance criteria: unauthorized write/command requests fail; invalid commands are rejected with persisted reasons; WebSocket events match schema.

Validation commands: baseline quality commands, API integration tests, WebSocket tests, security boundary tests.

Rollback/risk notes: route contracts must stay backward-compatible unless docs and tests update together.

### Milestone 4.6 - Sprint 5 Remote Web Console Core UX

Scope: home, new job, job detail, queue, reports, settings, command states, reconnect states, responsive shell.

Out-of-scope: browser direct file access, frontend framework migration, runtime feature changes.

Touched modules/files: `app/web_console/`, `tests/e2e/`, `docs/ui-spec.md`.

Acceptance criteria: Playwright covers first viewport CTA, job status, command flow shells, reports, mobile layout, and no file input/path write affordances.

Validation commands: baseline quality commands plus Playwright desktop/mobile smoke.

Rollback/risk notes: static modules remain preferred; add a build tool only with documented limitation.

### Milestone 4.7 - Sprint 6 Recovery, Resilience, And Local Panel

Scope: restart recovery, browser reconnect behavior, retry repair paths, minimal local operator panel.

Out-of-scope: full native macOS UI and packaging.

Touched modules/files: `app/runtime/recovery.py`, `app/api/websocket.py`, `app/local_panel/`, `tests/integration/runtime/`, `tests/e2e/`.

Acceptance criteria: recoverable jobs resume or surface truthful repair state; browser reconnect restores state; local panel remains status/emergency-only.

Validation commands: baseline quality commands, recovery scenario tests, reconnect Playwright tests.

Rollback/risk notes: recovery must be conservative; avoid automatic destructive cleanup.

### Milestone 5 - UI/UX Refinement

Scope: hierarchy, spacing, contrast, responsive behavior, operational wording, action clarity.

Out-of-scope: changing runtime/API authority boundaries.

Touched modules/files: `app/web_console/`, `docs/ui-spec.md`, `tests/e2e/`.

Acceptance criteria: desktop/mobile screenshots show no overlap, primary actions are visible, selected states use background fill, and labels clarify local runtime execution.

Validation commands: baseline quality commands, Playwright visual/responsive checks, accessibility smoke.

Rollback/risk notes: avoid decorative redesign that hides operational data.

### Milestone 6 - Hardening

Scope: negative auth tests, invalid command fuzzing, failure scenarios, performance smoke, boundary scans, test coverage tightening.

Out-of-scope: broad feature additions.

Touched modules/files: shared tests and focused implementation repairs only.

Acceptance criteria: major failure paths are tested; security boundary is explicit; no known validation failures remain.

Validation commands: full baseline, system scenarios, API negative tests, Playwright, build.

Rollback/risk notes: fixes must stay tied to observed failures.

### Milestone 7 - Release Wrap-Up

Scope: README, setup, handoff, demo script, packaging notes, known blockers, final QA record.

Out-of-scope: new product capability.

Touched modules/files: docs, packaging metadata, release artifacts.

Acceptance criteria: a new operator can install, run, validate, and understand known external blockers.

Validation commands: full baseline, run smoke, final documentation review.

Rollback/risk notes: packaging/signing may remain a truthful blocker if credentials are unavailable.
