# Sprint 0 BRAW Capability Gate Evaluation

Working root: `~/desktop/datamanager`.

## Scope Audited

- `docs/sprints/sprint-0-braw-gate.md`
- `app/parsers/base.py`
- `app/parsers/types.py`
- `app/parsers/braw_parser.py`
- `app/parsers/registry.py`
- `app/runtime/agent.py`
- `scripts/check_braw_capability.py`
- `tests/parsers/test_braw_capability.py`
- `docs/implement.md`

## Validation Re-run

- `.venv/bin/ruff check .` PASS
- `.venv/bin/ruff format --check .` PASS
- `.venv/bin/mypy app` PASS
- `.venv/bin/pytest tests/parsers -q` PASS, 6 tests
- `.venv/bin/python scripts/check_braw_capability.py` PASS, reports BRAW metadata/integrity/frame capture as `unavailable` because SDK command is not configured
- `.venv/bin/python -m build` PASS
- `.venv/bin/pytest -q` PASS, 18 tests

Real sample command:

- Not run with real media because no real `BRAW_SAMPLE` file is available.
- A non-real placeholder path was checked during implementation validation and still returned truthful unavailable status; this is not counted as real-media readiness.

## Scores

| Area | Score | Notes |
|---|---:|---|
| Spec fidelity / product depth | 5/5 | Parser execution remains local-runtime only; real vs mock capability is explicit. |
| Functionality | 4/5 | Contract, registry, real adapter boundary, mock parser, script, and runtime status wiring exist. Full real SDK behavior is blocked by missing external SDK/sample. |
| Code quality / maintainability | 4/5 | Parser protocol and data types are small and testable. Adapter command contract is intentionally narrow for this gate. |
| Validation completeness | 4/5 | Required automated validation passed. Real sample validation is honestly unavailable, not skipped silently. |
| Risk honesty / capability truthfulness | 5/5 | Missing SDK returns `unavailable`; mock parser is opt-in and marked `is_mock`; no code path upgrades real capability from mock success. |
| UI-related categories | N/A | Sprint did not change UI behavior except runtime capability values consumed by existing status shell. |

## Fabrication Check

PASS. The production registry includes only `BrawAdapter.from_environment()` by default. `MockBrawParser` is opt-in through `default_registry(include_mock=True)` and test code. `BrawAdapter.parse_metadata()` raises `BrawUnavailableError` when the SDK command is missing. `BrawAdapter.capture_frames()` always raises unavailable in this sprint. Runtime status reports unavailable BRAW metadata/frame capture when the command is absent.

## Verdict

PASS.

No repair actions are required. Stage 4.2 remains blocked until the user explicitly approves or instructs the next stage.
