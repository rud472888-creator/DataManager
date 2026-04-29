# Documentation Index

Working root: `~/desktop/datamanager`.

## Overview

Footage Data Manager is a macOS local runtime with a remote web console. The local runtime performs clone work: volume detection, scan, copy/offload, checksum verification, clone report generation, SQLite persistence, logs, and recovery. The web console is a REST and WebSocket client for job creation, monitoring, logs, reports, and command dispatch only.

The architecture boundary is fixed: local runtime executes, web console commands and observes. No documentation or implementation should imply that the browser performs local file access, copy, checksum, parser execution, frame capture, or arbitrary path writes.

## Recommended Reading Order

1. `README.md`
2. `docs/Footage_DataManager_Spec_v2_2_Local_Runtime_Remote_Console.md`
3. `docs/Footage_DataManager_Codex_Prompt_Pack.md`
4. `AGENTS.md`
5. `docs/implement.md`
6. `docs/qa.md`
7. `docs/hardening.md`
8. `docs/known-issues.md`
9. `docs/deployment.md`
10. `docs/handoff.md`

## Source Documents

- `docs/Footage_DataManager_Spec_v2_2_Local_Runtime_Remote_Console.md`: product specification and fixed architecture.
- `docs/Footage_DataManager_Codex_Prompt_Pack.md`: stage prompts, deliverables, validation, repair, and resume rules.
- `Footage_DataManager_Spec_v2_2_Local_Runtime_Remote_Console.md`: root-level compatibility mirror of the specification for tools or prompts that expect the original filename at repository root.
- `Footage_DataManager_Codex_Prompt_Pack.md`: root-level compatibility mirror of the prompt pack for tools or prompts that expect the original filename at repository root.

## Durable Project Docs

- `AGENTS.md`: repo operating rules, stage gates, architecture boundary, validation discipline.
- `README.md`: local bootstrap, run, validation, and architecture boundary summary.
- `pyproject.toml`: Python package metadata, dependencies, package data, Ruff, MyPy, and Pytest configuration.
- `docs/prompt.md`: concise product and prompt baseline.
- `docs/plan.md`: stage map, acceptance criteria, validation matrix, risks, assumptions.
- `docs/implement.md`: durable implementation and resume log.
- `docs/documentation.md`: this documentation index.
- `docs/ui-spec.md`: remote web console screen/state/design rules.
- `docs/api-contract.md`: initial REST, WebSocket, command, state, and auth contract.
- `docs/data-model.md`: entity inventory, keys, relationships, report artifacts, and recovery-critical fields.
- `docs/qa.md`: validation command registry and QA gate expectations.

## Stage 1 Application Shell

- `app/api/server.py`: FastAPI application factory and static console mount.
- `app/api/routes_runtime.py`: `/api/runtime/status` Stage 1 runtime payload.
- `app/api/websocket.py`: `/ws/runtime` Stage 1 WebSocket status event.
- `app/web_console/`: static browser console shell served by the local runtime API.
- `app/persistence/`: SQLite bootstrap schema and migration placeholder.
- `app/runtime/`, `app/parsers/`, `app/local_panel/`: placeholder package boundaries for later gated stages.
- `tests/`: API/WebSocket tests and Playwright browser smoke.
- `scripts/run_dev.sh`: local development server command.

## Stage 3 Architecture Map

- `app/config.py`: environment-backed runtime settings, including host, port, token, data directory, database path, and allowed destination roots.
- `app/persistence/db.py`: SQLite connection/session boundary for local-runtime-owned persistence.
- `app/persistence/migrations.py` and `app/persistence/schema.sql`: idempotent foundation migration and initial tables.
- `app/persistence/models.py` and `app/persistence/repositories.py`: model dataclasses and repository boundaries for jobs, events, volumes, and settings.
- `app/runtime/state_machine.py`: canonical job states, command names, command matrix, and command decisions.
- `app/runtime/events.py`: in-memory event publisher abstraction for Stage 3 and tests.
- `app/runtime/volume_monitor.py`: runtime-only volume provider protocol and safe mock provider.
- `app/runtime/scheduler.py`: single-active-job scheduler skeleton.
- `app/runtime/agent.py`: process-local runtime agent that applies migrations, seeds mock volumes, and reports foundation status.
- `app/api/deps.py`: runtime agent dependency and token auth skeleton.
- `app/api/routes_jobs.py`, `app/api/routes_settings.py`, `app/api/routes_volumes.py`: foundation REST skeletons.
- `scripts/apply_migrations.py`: migration apply command.
- `scripts/generate_fixture_media.py`: tiny fixture tree generator for later local media tests.

## Sprint 0 BRAW Capability Gate

- `docs/sprints/sprint-0-braw-gate.md`: Sprint contract, truthful unavailable rules, implementation notes, and validation record.
- `docs/qa/sprint-0-braw-gate-eval.md`: evaluator scores and PASS verdict.
- `app/parsers/types.py`: parser capability/result data models.
- `app/parsers/base.py`: runtime-only parser protocol.
- `app/parsers/braw_parser.py`: real BRAW adapter boundary plus explicit mock parser.
- `app/parsers/registry.py`: production parser registry with mock parser opt-in.
- `scripts/check_clone_capability.py`: JSON clone capability proof command.
- `tests/parsers/`: parser contract, mock behavior, unavailable real adapter, and registry tests.

## Sprint 1 Runtime State Machine & Persistence

- `docs/sprints/sprint-1-runtime-state.md`: Sprint contract, implementation notes, validation record, and deferred edge cases.
- `docs/qa/sprint-1-runtime-state-eval.md`: evaluator scores and PASS verdict.
- `app/runtime/state_machine.py`: canonical states, allowed transitions, command target states, command decisions.
- `app/runtime/lifecycle.py`: runtime-owned job creation, transition, command, event, and recovery query service.
- `app/runtime/recovery.py`: restart recovery candidate loader.
- `app/persistence/repositories.py`: job/event repository operations for lifecycle persistence.
- `app/api/routes_jobs.py`: transport-only REST skeleton for job list/create/command.
- `tests/runtime/`: state machine, lifecycle, command, and recovery tests.
- `tests/persistence/`: repository and append-only event tests.

## Sprint 2 Offload & Checksum Pipeline

- `docs/sprints/sprint-2-offload-checksum.md`: Sprint contract, offload rules, implementation notes, and validation record.
- `docs/qa/sprint-2-offload-checksum-eval.md`: evaluator scores and PASS verdict.
- `app/runtime/scan.py`: source scan, supported file filtering, excluded file policy.
- `app/runtime/checksum.py`: SHA-256 checksum helper.
- `app/runtime/offload.py`: runtime-only destination scaffold, copy, checksum verify, collision policy, `WARN`/`FAILED` handling.
- `app/persistence/models.py`: `JobFile` model.
- `app/persistence/repositories.py`: `JobFileRepository`.
- `tests/runtime/test_offload.py`: offload success and failure scenario tests.
- `tests/persistence/test_file_results.py`: file-level result persistence tests.

## Sprint 3 Clone Reports

- `docs/sprints/sprint-3-parse-capture-reports.md`: historical sprint contract; current product scope keeps only clone reports.
- `docs/qa/sprint-3-parse-capture-reports-eval.md`: historical evaluator record.
- `app/runtime/reports.py`: checksum PDF and manifest JSON generation from persisted clone results.
- `app/persistence/models.py`: `Report` model; `Clip` remains legacy schema surface for compatibility.
- `app/persistence/repositories.py`: `ReportRepository`; `ClipRepository` remains legacy schema surface for compatibility.
- `tests/runtime/test_parse_capture_reports.py`: parser legacy tests and clone report artifact tests.

## Sprint 4 API / WebSocket / Command Layer

- `docs/sprints/sprint-4-api-sync.md`: Sprint contract, endpoint/auth/WS contract, implementation notes.
- `docs/qa/sprint-4-api-sync-eval.md`: evaluator scores and PASS verdict.
- `app/api/routes_jobs.py`: job list/create/detail and command dispatch.
- `app/api/routes_logs.py`: job event log route.
- `app/api/routes_reports.py`: report metadata and safe download route.
- `app/api/routes_clips.py`: clip metadata route.
- `app/api/routes_settings.py`: token-protected settings get/patch.
- `app/api/websocket.py`: runtime status WebSocket snapshot event.
- `tests/api/test_api_sync.py`: API/auth/WS behavior tests.

## Sprint 5 Remote Web Console Core UX

- `docs/sprints/sprint-5-remote-console.md`: UI contract, screen responsibilities, validation flows, implementation notes.
- `docs/qa/sprint-5-remote-console-eval.md`: evaluator scores and PASS verdict.
- `app/web_console/index.html`: Home, New Job, Job Detail, Queue, Reports, Settings markup.
- `app/web_console/app.js`: REST/WebSocket integration and command interactions.
- `app/web_console/styles.css`: black/white responsive console styling.
- `tests/e2e/test_console_smoke.py`: desktop job flow, mobile CTA, no-file-input boundary.

## Sprint 6 Recovery, Resilience & Local Operator Panel

- `docs/sprints/sprint-6-recovery-resilience.md`: resilience contract and implementation notes.
- `docs/qa/sprint-6-recovery-resilience-eval.md`: evaluator scores and PASS verdict.
- `app/api/routes_runtime.py`: runtime recovery snapshot route.
- `app/local_panel/minimal_panel.py`: minimal status-only local panel renderer.
- `tests/runtime/test_recovery_resilience.py`: restart recovery, log parity, backup warn, local panel scope tests.
- `tests/e2e/test_console_smoke.py`: browser reload/reconnect queue visibility.

## Stage 5 UI/UX Refinement

- `docs/ui-audit.md`: screenshot audit, fixed problems, remaining UI weaknesses, PASS verdict.
- `docs/artifacts/stage-5-ui/desktop-home.png`: desktop screenshot artifact.
- `docs/artifacts/stage-5-ui/mobile-home.png`: mobile screenshot artifact.

## Stage 6 Hardening

- `docs/hardening.md`: hardening summary, evidence, remaining risks, PASS verdict.
- `docs/qa.md`: final mandatory validation matrix.
- `tests/system/test_hardening.py`: boundary, migration, performance smoke, security filtering, accessibility affordance tests.

## Stage 7 Release Wrap-Up

- `README.md`: release-quality overview, setup, run, validation, demo, capability status, and doc map.
- `docs/deployment.md`: local deployment, packaging status, security posture.
- `docs/known-issues.md`: external blockers and follow-up backlog.
- `docs/handoff.md`: reading order and handoff guidance.
- `docs/release-manifest.md`: validated artifact inventory, release script list, PASS evidence, and blocker summary.
- `scripts/smoke_release.sh`: release validation script.
- `scripts/demo_run.sh`: demo startup guidance script.

## Local Run Path

```sh
cd ~/desktop/datamanager
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m uvicorn app.api.server:create_app --factory --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/api/runtime/status
```

## Update Discipline

At each stage boundary, update `docs/implement.md` with current stage, PASS/FAIL evidence, blocker status, and exact next action. Update this index when adding new durable docs, sprint contracts, evaluator reports, or release handoff artifacts.
