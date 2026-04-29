# Sprint 2 - Offload & Checksum Pipeline Contract

Working root: `~/desktop/datamanager`.

## Goal

Implement the local-runtime-only scan, copy, checksum verification, destination folder policy, collision handling, partial failure semantics, and file-level result recording for synthetic fixture media.

## Scope

- Runtime source scan for supported files.
- Exclude `.DS_Store` and `._*`.
- Destination scaffold creation.
- Main and backup copy.
- SHA-256 checksum generation and comparison for source/main/backup.
- File-level persistence in `job_files`.
- Collision handling with no blind overwrite.
- Deterministic `WARN` vs `FAILED` behavior.
- Tests using temp directories and synthetic fixtures.

## Out Of Scope

- BRAW metadata parsing.
- Frame capture.
- PDF/XLSX/manifest report generation beyond folder scaffold.
- Browser/UI file selection or filesystem access.
- Pause/cancel mid-file behavior.
- Real removable-device monitoring.

## Touched Files And Modules

- `app/runtime/scan.py`
- `app/runtime/checksum.py`
- `app/runtime/offload.py`
- `app/persistence/models.py`
- `app/persistence/repositories.py`
- `tests/runtime/`
- `tests/persistence/`
- `docs/sprints/sprint-2-offload-checksum.md`
- `docs/qa/sprint-2-offload-checksum-eval.md`
- `docs/implement.md`

## Folder Structure Policy

Each destination root receives:

```text
<destination>/<project_name>/
├─ 00_master/
│  ├─ reports/
│  ├─ manifests/
│  └─ logs/
└─ 01_footage/
   └─ <source relative files>
```

This sprint creates only the scaffold and copied footage files. Reports/manifests/logs are reserved for later sprints.

## Collision Policy

If any target output path already exists before copy, the runtime must not overwrite it. The job becomes `FAILED`, an event is recorded, and file results should preserve the collision reason when a specific file is known.

## Partial Failure Semantics

- Main copy success + backup copy/checksum failure: job becomes `WARN`, file result records backup failure details.
- Main copy/checksum failure: job becomes `FAILED`.
- Source scan failure, source disappearance, unreadable source, or destination scaffold failure before any valid main copy: job becomes `FAILED`.
- Empty supported-file scan: job becomes `FAILED` with reason `no_supported_files`.

## Device Removal Handling

Do not introduce a new state in this sprint. Represent source/destination disappearance as error codes and reasons on events/file results, normally ending in `FAILED` unless a main copy is complete and backup alone failed.

## Validation Plan

Use temporary directories and generated tiny files. Required scenarios:

- success: two `.braw` files copy to main/backup and verify.
- excluded files: `.DS_Store` and `._*` are ignored.
- collision: pre-existing target blocks overwrite and fails deterministically.
- backup failure: main success with backup failure yields `WARN`.
- source/device removal simulation: missing source file during copy yields `FAILED`.
- file results persist source/main/backup checksums and status.

## Acceptance Criteria

- Runtime is the only file-work executor.
- Synthetic source can offload to main/backup destination roots.
- Checksums are computed and compared.
- File-level outcomes are persisted.
- Collision and partial-failure behavior is deterministic and tested.

## Validation Commands

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest tests/runtime tests/persistence -q
.venv/bin/python -m build
```

## Implementation Notes

Implemented runtime-only scan/copy/checksum pipeline:

- `app/runtime/scan.py` scans source directories for `.braw` files and excludes `.DS_Store` plus `._*`.
- `app/runtime/checksum.py` computes SHA-256 checksums.
- `app/runtime/offload.py` creates destination scaffold, blocks collisions, copies to main/backup, verifies checksums, records deterministic `COMPLETED`, `WARN`, and `FAILED` outcomes.
- `app/persistence/models.py` defines `JobFile`.
- `app/persistence/repositories.py` persists and lists file-level outcomes through `JobFileRepository`.
- Tests cover success, excluded files, collision/no overwrite, backup failure -> `WARN`, source disappearance/main copy failure -> `FAILED`, and file-result persistence.

Validation run:

- `.venv/bin/ruff check .` PASS
- `.venv/bin/ruff format --check .` PASS
- `.venv/bin/mypy app` PASS
- `.venv/bin/pytest tests/runtime tests/persistence -q` PASS, 14 tests
- `.venv/bin/pytest -q` PASS, 32 tests
- `.venv/bin/python -m build` PASS

Known limitations:

- Pause/cancel checkpoints are file-boundary only by design for this sprint.
- Real removable-device monitoring remains deferred.
- Report/manifest generation remains deferred.
- Offload is callable from runtime services/tests; full API/UI orchestration is deferred to later sprints.
