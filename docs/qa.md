# QA And Validation Plan

Working root: `~/desktop/datamanager`.

## Gate Principle

No stage is PASS until its required validation commands pass and the durable docs record the result, blocker status, and exact next action. A failed command keeps the project inside the current stage. The local runtime / web console boundary is part of every QA gate.

## Stage 0 Validation

```sh
mkdir -p ~/desktop/datamanager && cd ~/desktop/datamanager
test -f AGENTS.md
test -f docs/prompt.md
test -f docs/plan.md
test -f docs/implement.md
test -f docs/documentation.md
test -f docs/ui-spec.md
test -f docs/api-contract.md
test -f docs/qa.md
grep -R "local runtime" -n AGENTS.md docs
grep -R "web console" -n AGENTS.md docs
grep -R "~/desktop/datamanager" -n AGENTS.md docs
```

## Baseline Commands For Later Stages

Stage 1 must create working project tooling so these commands exist and pass:

```sh
.venv/bin/python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy app
pytest -q
python -m build
curl -fsS http://127.0.0.1:8000/api/runtime/status
```

Stage 1 must also add and run a Python Playwright smoke test for the home page and primary CTA shell.

## Required Validation Families

- Lint: Ruff
- Format check: Ruff format check
- Typecheck: MyPy for `app`
- Unit and integration tests: Pytest
- Package build: `python -m build`
- API smoke: runtime status endpoint and command validation paths
- WebSocket smoke: connection and event shape
- UI smoke: Playwright home, job CTA, responsive basics
- Scenario checks: offload, checksum, command rejection, disconnect/reconnect, restart recovery as the stages add those capabilities
- Static boundary checks: no web console direct filesystem access, parser execution, checksum execution, or arbitrary path write logic

## Milestone-Specific Validation Matrix

| Milestone | Required validation |
|---|---|
| Stage 3 foundation | baseline quality commands, state/command schema tests, static boundary test |
| Sprint 0 BRAW gate | parser protocol tests, mock adapter tests, capability API tests, no fake real-BRAW PASS |
| Sprint 1 state/persistence | state transition matrix tests, command matrix tests, repository tests, recovery candidate tests |
| Sprint 2 offload/checksum | temp-directory scan/copy/verify integration, mismatch failure tests, no arbitrary browser path tests |
| Sprint 3 clone reports | checksum PDF and manifest artifact tests |
| Sprint 4 API/WebSocket | auth negative tests, invalid command tests, WebSocket event shape tests, reconnect snapshot tests |
| Sprint 5 remote console | Playwright desktop/mobile smoke, command UI state tests, no file input/path write affordance scan |
| Sprint 6 recovery/local panel | restart recovery scenarios, browser reconnect test, local panel boundary test |
| Stage 5 UI/UX | responsive screenshots, focus/contrast smoke, no overlap, primary CTA visible |
| Stage 6 hardening | full baseline, security boundary, failure scenario matrix, performance smoke |
| Stage 7 release | full baseline, install/run smoke, final docs review |

## Scenario Tests

- Browser disconnect during `COPYING` does not stop the runtime job.
- Browser reconnect receives REST snapshot and WebSocket updates.
- Invalid `resume` from `COPYING` returns rejection and persists a command event.
- Missing token on command routes returns unauthorized.
- Clone capability status reports checksum and supported offload formats truthfully.
- Source removed during scan/copy creates a failure or paused/error reason without corrupting persisted state.
- Main success with backup failure records `WARN` and report details.
- Checksum mismatch records file-level failure and blocks false completion.
- Report generation failure records an event and surfaces in job detail/reports.
- Web console contains no source/destination file input and no direct filesystem APIs.

## Fixture Strategy

- Use temporary directories and tiny generated binary files for scan/copy/checksum tests.
- Use fake BRAW-like files and mock parser adapters for parser contract tests.
- Keep proprietary media tests optional and gated behind explicit environment variables.
- Never mark real BRAW support PASS without real SDK/sample evidence.

## Stage 2 Validation

```sh
grep -n "Milestone" docs/plan.md
grep -n "state" docs/api-contract.md docs/plan.md
grep -n "WebSocket" docs/api-contract.md
grep -n "mobile" docs/ui-spec.md
grep -n "validation" docs/qa.md
test -f docs/data-model.md || true
```

## Stage 3 Validation

```sh
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python scripts/apply_migrations.py
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest -q
.venv/bin/python -m build
.venv/bin/python -m uvicorn app.api.server:create_app --factory --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/api/runtime/status
.venv/bin/pytest tests/e2e -q
```

## Final Mandatory Validation Matrix

Before release wrap-up, run:

```sh
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python scripts/apply_migrations.py
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest -q
.venv/bin/python scripts/check_clone_capability.py
.venv/bin/python -m build
```

Required scenario coverage now includes:

- Parser capability unavailable truthfulness.
- State transition and command rejection.
- Runtime-only scan/copy/checksum.
- Collision/no-overwrite.
- Backup failure -> `WARN`.
- Parse/report unavailable frame behavior.
- API auth negative tests.
- Web console no file input/direct filesystem APIs.
- Browser reload/reconnect.
- Restart recovery candidates.
- Migration idempotency.
- 50-file synthetic offload smoke.

## Evaluator Expectations

Sprint stages with A. Contract, B. Implementation, and C. Evaluator must produce the contract before implementation and an evaluator document after validation. FAIL means repair inside the same sprint only, rerun the full validation set, and refresh the evaluator verdict.

## Truthful Blockers

If sample media, packaging credentials, signing identity, or external binaries are unavailable, record the blocker honestly in `docs/implement.md` and the relevant evaluator/QA document. Do not create fake media support, fake reports, or fake PASS evidence.
