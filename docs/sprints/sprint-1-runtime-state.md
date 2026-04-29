# Sprint 1 - Runtime State Machine & Persistence Contract

Working root: `~/desktop/datamanager`.

## Goal

Implement the lifecycle backbone for jobs, command decisions, scheduler policy, append-only events, and restart recovery. The runtime owns state transitions and persistence; API and UI only transport requests and display results.

## Canonical States

`QUEUED`, `SCANNING`, `PREPARING`, `COPYING`, `PAUSING`, `PAUSED`, `VERIFYING`, `PARSING`, `CAPTURING`, `REPORTING`, `WARN`, `FAILED`, `CANCELLED`, `COMPLETED`.

Terminal states: `CANCELLED`, `COMPLETED`.

Recoverable states after restart: `QUEUED`, `PAUSED`, `WARN`, `FAILED`.

## Allowed Runtime Transitions

| State | Allowed next states |
|---|---|
| `QUEUED` | `SCANNING`, `CANCELLED` |
| `SCANNING` | `PREPARING`, `FAILED`, `CANCELLED` |
| `PREPARING` | `COPYING`, `FAILED`, `CANCELLED` |
| `COPYING` | `PAUSING`, `VERIFYING`, `WARN`, `FAILED`, `CANCELLED` |
| `PAUSING` | `PAUSED`, `FAILED` |
| `PAUSED` | `COPYING`, `CANCELLED` |
| `VERIFYING` | `PARSING`, `WARN`, `FAILED`, `CANCELLED` |
| `PARSING` | `CAPTURING`, `REPORTING`, `WARN`, `FAILED`, `CANCELLED` |
| `CAPTURING` | `REPORTING`, `WARN`, `FAILED`, `CANCELLED` |
| `REPORTING` | `COMPLETED`, `WARN`, `FAILED`, `CANCELLED` |
| `WARN` | `QUEUED`, `REPORTING`, `COMPLETED`, `FAILED` |
| `FAILED` | `QUEUED` |
| `CANCELLED` | none |
| `COMPLETED` | none |

## Command Acceptance Rules

Commands are requests. API validates shape/auth, then the runtime decides.

| State | pause | resume | cancel | retry | refresh |
|---|---|---|---|---|---|
| `QUEUED` | reject | reject | accept -> `CANCELLED` | reject | accept -> same |
| `SCANNING` | reject | reject | accept -> `CANCELLED` | reject | accept -> same |
| `PREPARING` | reject | reject | accept -> `CANCELLED` | reject | accept -> same |
| `COPYING` | accept -> `PAUSING` | reject | accept -> `CANCELLED` | reject | accept -> same |
| `PAUSING` | reject | reject | reject | reject | accept -> same |
| `PAUSED` | reject | accept -> `COPYING` | accept -> `CANCELLED` | reject | accept -> same |
| `VERIFYING` | reject | reject | accept -> `CANCELLED` | reject | accept -> same |
| `PARSING` | reject | reject | accept -> `CANCELLED` | reject | accept -> same |
| `CAPTURING` | reject | reject | accept -> `CANCELLED` | reject | accept -> same |
| `REPORTING` | reject | reject | accept -> `CANCELLED` | reject | accept -> same |
| `WARN` | reject | reject | reject | accept -> `QUEUED` | accept -> same |
| `FAILED` | reject | reject | reject | accept -> `QUEUED` | accept -> same |
| `CANCELLED` | reject | reject | reject | reject | accept -> same |
| `COMPLETED` | reject | reject | reject | reject | accept -> same |

Every accepted or rejected command must be recorded as an append-only event.

## Scheduler Policy

v1 allows exactly one active job. Active means any non-terminal job except `WARN` and `FAILED`, which are repair/retry states. Creating a new job is rejected when another active job exists.

## Persistence Responsibilities

- `jobs`: current lifecycle state, source/destination IDs, policy/stats JSON, timestamps, recovery cursor.
- `job_events`: append-only lifecycle, command, warning, and error history.
- Repositories are the only code that mutates lifecycle tables directly.
- Runtime services call repositories and decide transitions.
- API routes do not update job state directly.

## Recovery Semantics

On restart, load `QUEUED`, `PAUSED`, `WARN`, and `FAILED` jobs. Active interrupted states should not be silently continued in this sprint; later recovery/resilience work may inspect checkpoints and choose repair behavior.

## Out Of Scope

- Real file copy/verification.
- Parser execution or reports.
- Browser command UX.
- Multi-active-job queue execution.
- Destructive cleanup of partial media.

## Acceptance Criteria

- State transitions are explicit and tested.
- Command accept/reject decisions are deterministic and tested.
- Job creation enforces single-active-job policy.
- Events are append-only and persisted for state changes and commands.
- Recovery loader returns only recoverable jobs.
- API transports job creation/command requests without becoming the state owner.

## Validation Commands

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest tests/runtime tests/persistence -q
.venv/bin/python -m build
```

## Implementation Notes

Implemented lifecycle backbone:

- `app/runtime/state_machine.py` now contains canonical states, terminal/recoverable state sets, allowed runtime transitions, command target states, transition decisions, and command decisions.
- `app/runtime/lifecycle.py` owns job creation, state transition, command decision, event recording, single-active-job enforcement through persisted active job checks, and recoverable job queries.
- `app/runtime/recovery.py` loads restart recovery candidates for `QUEUED`, `PAUSED`, `WARN`, and `FAILED`.
- `app/persistence/repositories.py` now supports create/get/list/update/recoverable jobs and append-only event listing.
- `app/api/routes_jobs.py` transports create/list/command requests to the runtime lifecycle service without directly mutating state.
- `tests/runtime/` covers allowed/rejected transitions, command target states, lifecycle events, single-active-job rejection, command state updates, and recovery candidates.
- `tests/persistence/` covers active/recoverable repository behavior and append-only event ordering.

Validation run:

- `.venv/bin/ruff check .` PASS
- `.venv/bin/ruff format --check .` PASS
- `.venv/bin/mypy app` PASS
- `.venv/bin/pytest tests/runtime tests/persistence -q` PASS, 8 tests
- `.venv/bin/pytest -q` PASS, 26 tests
- `.venv/bin/python -m build` PASS

Open edge cases deferred:

- Active interrupted states are not auto-recovered in this sprint.
- Queue workers do not execute copy/verify work yet.
- Retry policy is state-level only; file-level retry comes with the offload/checksum sprint.
