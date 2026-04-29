# Sprint 0 - BRAW Capability Gate Contract

Working root: `~/desktop/datamanager`.

## Goal

De-risk BRAW metadata extraction and frame capture before later runtime/report stages depend on them. The parser layer runs only inside the macOS local runtime. The project must report real BRAW readiness truthfully and must never fabricate successful metadata or frame outputs.

## Scope

- Define a runtime-only parser contract for probing, metadata extraction, integrity checks, and frame capture.
- Define capability states for metadata, integrity, and frame capture.
- Add a BRAW adapter boundary that can report SDK/sample unavailability without pretending support.
- Add deterministic mock parser behavior for tests.
- Add a registry that separates mock parsers from real adapters.
- Add `scripts/check_braw_capability.py` as a proof command.
- Add tests for mock parser behavior, unavailable real adapter behavior, registry behavior, and no fake success.
- Update implementation docs with real vs mocked status and blockers.

## Out Of Scope

- Real offload/copy/checksum pipeline.
- Real report generation.
- Browser-side parser execution or parser UI.
- Shipping a BRAW SDK or bundling proprietary media.
- Declaring BRAW metadata/frame capture available without executable adapter evidence.
- Building RED/ARRI/other formats.

## Touched Files And Modules

- `app/parsers/base.py`
- `app/parsers/registry.py`
- `app/parsers/braw_parser.py`
- `app/parsers/types.py`
- `app/runtime/agent.py` only for capability status wiring if needed
- `app/api/routes_runtime.py` only if capability payload needs to reflect the gate
- `scripts/check_braw_capability.py`
- `tests/parsers/`
- `docs/implement.md`
- `docs/sprints/sprint-0-braw-gate.md`
- `docs/qa/sprint-0-braw-gate-eval.md`

## Acceptance Criteria

- Parser contracts are stable enough for later runtime stages to call without guessing.
- Real BRAW adapter defaults to truthful unavailable/partial when SDK command or sample file is absent.
- Mock parser returns deterministic metadata/frame placeholders only for explicit mock development and tests.
- Capability check script exits successfully while reporting the environment truthfully.
- No code path fabricates successful real BRAW metadata or frame capture when unavailable.
- Tests cover mock success, real adapter unavailable behavior, registry lookup, and capability serialization.

## Validation Commands

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest tests/parsers -q
.venv/bin/python scripts/check_braw_capability.py
BRAW_SAMPLE=/path/to/sample.braw .venv/bin/python scripts/check_braw_capability.py
.venv/bin/python -m build
```

Run the `BRAW_SAMPLE=...` command only when a real sample exists. If no sample exists, record that it was not run because the input is unavailable.

## Blockers

- Real BRAW SDK command is not known to be installed.
- Real `.braw` sample media is not currently provided.
- Licensing/distribution terms for SDK and sample media are unknown.
- Frame capture may require external SDK or ffmpeg-like tooling that is not currently validated.

## Mock Development Vs Real BRAW Integration

Mock development:

- Uses deterministic fake `.braw` fixtures or explicit mock parser IDs.
- May return known fake metadata for tests.
- May create placeholder frame references in a temp/test directory.
- Must label outputs as mock and never present them as real BRAW evidence.

Real BRAW integration:

- Requires configured adapter command or SDK wrapper.
- Requires real sample media for validation.
- Must report command missing, sample missing, command failure, or parse/capture unsupported as unavailable/partial.
- May mark capability `available` only when probe, metadata, and/or capture commands succeed with real adapter evidence.

## Truthful Unavailable Capability Rules

- Missing SDK command: metadata/integrity/frame capability is `unavailable` with reason `BRAW SDK command is not configured`.
- Missing sample file: real sample validation is `unavailable` or `partial`; it is not PASS evidence for real media.
- Command failure: capability is `unavailable` with stderr/exit-code reason sanitized for logs.
- Unsupported frame capture: metadata may be `available` or `partial`, but frame capture remains `unavailable`.
- Mock success never upgrades real adapter capability.
- Runtime/API status may expose `unknown`, `partial`, `available`, or `unavailable`, but must not claim full BRAW readiness unless real adapter validation exists.

## Reporting

The sprint evaluator must write `docs/qa/sprint-0-braw-gate-eval.md` with scored categories and a PASS/FAIL verdict. Any score below 4/5 or missing validation is FAIL and blocks Stage 4.2.

## Implementation Notes

Implemented parser contract and gate:

- `app/parsers/types.py` defines capability, probe, metadata, integrity, frame, and capability-check data models.
- `app/parsers/base.py` defines the runtime-only parser protocol.
- `app/parsers/braw_parser.py` contains the real BRAW adapter boundary and explicit `MockBrawParser`.
- `app/parsers/registry.py` registers the real BRAW adapter by default and keeps the mock parser opt-in.
- `scripts/check_braw_capability.py` prints JSON capability evidence.
- `app/runtime/agent.py` now exposes BRAW metadata/frame capability from the real adapter boundary in runtime status.

Real vs mock status:

- Real BRAW metadata and frame capture are currently `unavailable` because `FDM_BRAW_METADATA_COMMAND` is not configured and no real sample media is present.
- Mock parser behavior is deterministic, opt-in, marked `is_mock`, and covered by parser tests.
- Mock success does not upgrade production/runtime BRAW capability.

Validation run:

- `.venv/bin/ruff check .` PASS
- `.venv/bin/ruff format --check .` PASS
- `.venv/bin/mypy app` PASS
- `.venv/bin/pytest tests/parsers -q` PASS, 6 tests
- `.venv/bin/python scripts/check_braw_capability.py` PASS, truthful unavailable JSON
- `.venv/bin/python -m build` PASS
- `.venv/bin/pytest -q` PASS, 18 tests

Real sample validation:

- Not run with a real sample because no real `.braw` sample path is available. A non-real placeholder path was also checked and the script still reported unavailable rather than fake success.
