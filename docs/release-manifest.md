# Release Manifest

Working root: `~/desktop/datamanager`.

## Status

Stage 7 Release Wrap-Up: PASS.

Last release smoke command:

```sh
scripts/smoke_release.sh
```

Result: PASS.

## Source Of Truth Files

- `docs/Footage_DataManager_Spec_v2_2_Local_Runtime_Remote_Console.md`
- `docs/Footage_DataManager_Codex_Prompt_Pack.md`
- `Footage_DataManager_Spec_v2_2_Local_Runtime_Remote_Console.md`
- `Footage_DataManager_Codex_Prompt_Pack.md`

The root source-of-truth files are compatibility mirrors of the docs copies.

## Release Documents

- `README.md`
- `docs/documentation.md`
- `docs/deployment.md`
- `docs/known-issues.md`
- `docs/handoff.md`
- `docs/hardening.md`
- `docs/qa.md`
- `docs/implement.md`

## Sprint Contracts And Evaluators

- `docs/sprints/sprint-0-braw-gate.md` / `docs/qa/sprint-0-braw-gate-eval.md`
- `docs/sprints/sprint-1-runtime-state.md` / `docs/qa/sprint-1-runtime-state-eval.md`
- `docs/sprints/sprint-2-offload-checksum.md` / `docs/qa/sprint-2-offload-checksum-eval.md`
- `docs/sprints/sprint-3-parse-capture-reports.md` / `docs/qa/sprint-3-parse-capture-reports-eval.md`
- `docs/sprints/sprint-4-api-sync.md` / `docs/qa/sprint-4-api-sync-eval.md`
- `docs/sprints/sprint-5-remote-console.md` / `docs/qa/sprint-5-remote-console-eval.md`
- `docs/sprints/sprint-6-recovery-resilience.md` / `docs/qa/sprint-6-recovery-resilience-eval.md`

## Release Scripts

- `scripts/smoke_release.sh`
- `scripts/demo_run.sh`
- `scripts/apply_migrations.py`
- `scripts/check_braw_capability.py`
- `scripts/generate_fixture_media.py`

## Validation Evidence

The final smoke script validates:

- editable install
- SQLite migration apply
- Ruff lint
- Ruff format check
- MyPy
- Pytest
- BRAW capability truthfulness
- Python package build

Latest full test result: 52 tests passed.

## Known External Blockers

- Real BRAW SDK command is not configured.
- Real `.braw` sample media is not available.
- Real frame capture is unavailable.
- macOS signing/notarization credentials are not available.

## Next Work Entry Point

Start from `docs/known-issues.md`.
