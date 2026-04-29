
# Footage Data Manager — Codex Prompt Pack
Source spec: **Footage Data Manager 개발 기획서 v2.2 (Local Runtime + Remote Web Console)**  
Working root: **`~/desktop/datamanager`**  
Assumed project type: **Greenfield**

## Shared execution rule for every Codex session

Run this first in every stage:

```bash
mkdir -p ~/desktop/datamanager
cd ~/desktop/datamanager
```

Use `~/desktop/datamanager` as the only project root. Do not place durable project files outside this directory except for system temp/cache or virtual environment artifacts.  
The architecture boundary is fixed and must never drift:

- **Local macOS runtime / agent is the only executor of real file operations.**
- **Remote web console only creates jobs, sends commands, and observes state through REST + WebSocket.**
- **The web console must never perform direct local file access, OS file picking, copy, checksum, parser execution, or arbitrary path writes.**

---

## 1. Spec Digest

### Product one-line definition
A macOS-local footage clone manager that detects media volumes, offloads camera footage to main/backup destinations, verifies integrity, generates clone reports, and exposes a browser-based remote console for job control and monitoring. Metadata parsing and frame capture are handled by a separate program.

### Target users / roles
- **Local operator / DIT / data wrangler** running the macOS runtime on the field machine.
- **Remote supervisor / producer / assistant** using a browser on the same or another device for monitoring and command dispatch.
- **Optional local operator panel user** who needs a minimal emergency/status view on the runtime machine.

### Core user flows
1. **Field start**
   - Card inserted -> local runtime detects volume -> remote console loads detected sources and allowed destinations -> operator creates job -> runtime executes.
2. **Offload execution**
   - Runtime scans source -> prepares folder structure -> copies to main/backup -> verifies checksums -> generates checksum/manifest outputs.
3. **Remote monitoring**
   - Browser shows runtime status, job progress, speed, ETA, current file, warnings/errors, logs, and report links in real time.
4. **Remote command/control**
   - Browser sends pause / resume / cancel / retry -> API validates -> runtime accepts/rejects based on current state -> event is persisted and reflected back to the browser.
5. **Recovery**
   - Browser can disconnect and reconnect without stopping the job.
   - App restart can recover `QUEUED`, `PAUSED`, `WARN`, and `FAILED` jobs.
6. **Failure handling**
   - Drive failure or copy/verify/report problems are recorded as events, surfaced in the web console, and repaired through retry or destination adjustments within allowed policies.

### Required features
- macOS local runtime / agent as the execution engine
- BRAW-focused ingest for v1
- volume detection and allowed destination discovery
- single active offload queue
- state machine for job lifecycle
- main + backup destination copy
- checksum verification
- clone manifest and checksum report generation
- report generation:
  - checksum PDF
  - manifest.json
- SQLite persistence
- append-only event/log history
- REST API + WebSocket status/event stream
- remote web console:
  - home
  - new job flow
  - job detail
  - queue
  - reports center
  - settings
- responsive browser support for mobile/iPad
- runtime/browser disconnect tolerance
- restart recovery for recoverable jobs

### Optional features
- minimal local operator panel
- macOS packaging / app bundle hardening
- future parser expansion beyond BRAW
- richer auth later than simple token-based v1 auth

### Non-goals for v1
- native iOS app
- web console direct file-system access
- browser-based file picker for source/destination
- multiple active offload jobs
- multi-format ingest beyond BRAW
- advanced integrations like Resolve project generation, Telegram, Notion, proxy generation
- complex RBAC / enterprise auth
- turning the local operator panel into a second full product

### Non-functional requirements
- clear architecture boundary between executor and remote console
- resilient job execution even when browser disconnects
- persistent audit trail for states, commands, logs, file-level outcomes, and reports
- maintainable module boundaries:
  - business logic
  - transport/API
  - persistence
  - runtime workers
  - UI
- reproducible validations and scenario tests
- responsive UI with explicit task hierarchy
- accessibility fundamentals:
  - semantic structure
  - keyboard focus
  - contrast
  - labels
- visual consistency:
  - black/white palette
  - no shadows
  - strong spacing and hierarchy
  - selected state uses background change, not border only
- no generic AI-template aesthetics or random card soup

### Technical constraints
- runtime target is **macOS**
- local runtime is the only layer with file authority
- remote console consumes **REST + WebSocket only**
- persistence is **SQLite**
- simple token auth is acceptable for v1
- only runtime can use `/Volumes`, local storage, SDKs, ffmpeg, file handles, temp files
- web console may only use runtime-provided source/destination/setting data
- v1 should be conservative and shippable before introducing extra stack complexity

### UI / brand / tone requirements
- simple, modern, wireframe-like visual system
- black & white first
- CTA visible in the first viewport
- Gutenberg-style priority: context upper-left, main CTA lower-right or equivalent prominent placement
- mobile should use a fixed bottom action bar or an equally obvious primary action pattern
- job status must clearly say that the local runtime is performing real file operations
- reports/logs/errors should be easy to inspect quickly under field pressure

### Performance / accessibility / security / testing expectations
- show speed, ETA, current step, warnings, errors, success counts
- large-file operations should not freeze UI/control surfaces
- long-running jobs should survive browser disconnect
- token auth and read/write boundaries should be explicit
- negative tests for invalid commands and unauthorized access
- lint, typecheck, tests, Playwright, build/package smoke, and scenario validation are required
- no “done” state without passing validation

### Existing codebase status
No existing repository or production codebase was provided. These prompts assume a **greenfield** implementation rooted at `~/desktop/datamanager`.

### Key ambiguities to resolve by documented assumption
- real camera sample media availability for clone validation
- separate capture-app integration boundary, if operators need to hand off cloned media
- final packaging method for macOS runtime
- exact local operator panel technology
- auth UX for the remote console (simple token entry, config file, or env-based gate)
- destination configuration UX and local-network exposure model

---

## 2. Assumptions & Risks

### Assumptions
1. This is a **greenfield repo** and should be created under `~/desktop/datamanager`.
2. Use a **conservative Python-first stack** for v1:
   - Python package for runtime/API/persistence
   - FastAPI for REST/WebSocket
   - SQLite for persistence
   - Alembic or equivalent migration discipline
   - Pytest, Ruff, MyPy, Python Playwright
   - static web console served by FastAPI using HTML/CSS/JS modules unless a stronger reason for a front-end build tool is documented first
3. v1 auth is **simple token-based auth**, suitable for trusted local/LAN environments.
4. The runtime is the authority for discovered source volumes and allowed destinations; the web console never accepts arbitrary raw paths.
5. A single active offload job is the correct stability-first policy for v1.
6. Frame capture and deeper image processing are outside this clone app and belong to a separate program.

### Risks
1. **Camera-media clone validation risk**
   - Real sample files and target volumes may be unavailable during development, so clone behavior must be validated with truthful fixtures and documented field checks.
2. **macOS file/volume behavior**
   - Permissions, mounted volumes, removable devices, and `/Volumes` semantics must be handled carefully.
3. **Partial-copy and recovery correctness**
   - Resuming after interruption without corrupting state or double-counting results is a high-risk area.
4. **Checksum and copy throughput**
   - Large media workloads may expose bottlenecks, checkpoint granularity problems, or slow verification paths.
5. **Packaging**
   - Bundling SDKs/ffmpeg or external dependencies into a distributable macOS runtime may require a separate packaging pass.
6. **Security if exposed beyond a trusted network**
   - The v1 token model is not suitable for broad internet exposure without additional safeguards.
7. **Spec edge-case ambiguity**
   - The spec mentions device-error handling policy without a canonical extra state. Use the canonical state list first, and represent device-error detail with reason/error codes unless planning docs justify a new state.

---

## 3. Recommended Stage Map

| Stage | Name | Main output |
|---|---|---|
| 0 | Freeze the Target & Working Memory | durable docs, rules, boundaries, stage map |
| 1 | Greenfield Bootstrap | runnable repo shell with validation tooling |
| 2 | Architecture & Milestone Planning | implementation-ready contracts and module map |
| 3 | Foundation Build | core runtime/API/persistence/UI shell foundations |
| 4.1 | Sprint 0 — BRAW Capability Gate | parser contract + truthful BRAW gate |
| 4.2 | Sprint 1 — Runtime State Machine & Persistence | job lifecycle, scheduler, repositories, recovery scaffolding |
| 4.3 | Sprint 2 — Offload & Checksum Pipeline | scan/copy/verify core path |
| 4.4 | Sprint 3 — Clone Reports | checksum/manifest report artifacts |
| 4.5 | Sprint 4 — API / WebSocket / Command Layer | remote control and state sync contract |
| 4.6 | Sprint 5 — Remote Web Console Core UX | core browser experience and command flows |
| 4.7 | Sprint 6 — Recovery, Resilience & Local Operator Panel | restart recovery, reconnect UX, minimal local panel |
| 5 | UI/UX Refinement | visual polish, responsive tuning, clearer task flow |
| 6 | Hardening | tests, accessibility, security, performance, failure handling |
| 7 | Release Wrap-Up | README, setup, demo, deployment/packaging prep, handoff |
| R | Resume / Recovery | restart long-run Codex work safely from durable docs |

---

## 4. Copy-paste-ready Codex prompts

---

## [Stage 0] Freeze the Target & Working Memory

- **Why this stage exists**  
  Prevent architectural drift and create durable project memory before implementation begins.

- **Recommended Codex mode**: Plan  
- **Suggested reasoning level**: High  
- **Suggested tools/skills**: docs, filesystem, planning, worktree  
- **Worktree recommendation**: use the main worktree only

### Copy-paste prompt

```text
Goal
Freeze the product boundary, working rules, and durable project memory for a greenfield implementation of Footage Data Manager before writing feature code.

Context
- Product: Footage Data Manager.
- Architecture boundary is fixed:
  - macOS Local Runtime / Agent is the only executor of real file operations.
  - Remote Web Console is only for remote job creation, monitoring, logs, reports, and command dispatch through REST + WebSocket.
  - The web console must never perform direct local file access, OS file picking, copy, checksum, parser execution, or arbitrary path writes.
- v1 scope: BRAW-oriented clone/offload, volume detection, single active offload queue, main/backup destinations, checksum verification, clone report generation, SQLite persistence, remote monitoring/control, responsive browser UI.
- Non-goals: native iOS app, web direct file access, multi-active offload, multi-format ingest beyond BRAW, advanced post-production integrations.

Constraints
- Work in `~/desktop/datamanager`; if the directory does not exist, create it first and use it as the project root.
- This is a greenfield repo. Do not invent a second architecture or parallel executor.
- Keep this stage documentation-first. Minimal repo scaffolding is allowed, but no deep implementation yet.
- Create or update:
  - `AGENTS.md`
  - `docs/prompt.md`
  - `docs/plan.md`
  - `docs/implement.md`
  - `docs/documentation.md`
  - `docs/ui-spec.md`
  - `docs/api-contract.md`
  - `docs/qa.md`
- Capture assumptions explicitly instead of blocking on ambiguity.
- In every document, keep the wording consistent with the executor/console split.

Deliverables
1. A durable `AGENTS.md` with execution rules, architecture boundaries, validation rules, forbidden shortcuts, and update discipline.
2. Planning docs that contain:
   - product summary
   - user roles and core flows
   - required features / optional features / non-goals
   - non-functional requirements
   - stage map with milestones and gates
   - acceptance criteria and validation matrix
   - major risks and assumptions
3. `docs/ui-spec.md` with screen inventory, state inventory, layout intent, responsive rules, and the black/white visual language.
4. `docs/api-contract.md` with initial REST routes, WebSocket event shape, command/state transition rules, and auth assumptions.
5. `docs/qa.md` with mandatory commands for lint, typecheck, tests, build, Playwright, and scenario checks.

Done when
- All required docs exist and are internally consistent.
- The docs explicitly repeat the product boundary: local runtime executes; web console commands/observes only.
- The docs mention the working root `~/desktop/datamanager`.
- The docs define milestone order and clear stop/go gates.

Validation
- Run:
  - `mkdir -p ~/desktop/datamanager && cd ~/desktop/datamanager`
  - `test -f AGENTS.md`
  - `test -f docs/prompt.md`
  - `test -f docs/plan.md`
  - `test -f docs/implement.md`
  - `test -f docs/documentation.md`
  - `test -f docs/ui-spec.md`
  - `test -f docs/api-contract.md`
  - `test -f docs/qa.md`
  - `grep -R "local runtime" -n AGENTS.md docs`
  - `grep -R "web console" -n AGENTS.md docs`
  - `grep -R "~/desktop/datamanager" -n AGENTS.md docs`
- If any document is missing or the architecture boundary is ambiguous, fix it before stopping.

Reporting / update files
- Update `docs/implement.md` with:
  - what was created
  - key decisions
  - open risks
  - exact next stage
- Update `docs/documentation.md` with a concise project overview and document index.
- Do not claim implementation progress beyond planning.
```

### Expected artifacts/files
- `AGENTS.md`
- `docs/prompt.md`
- `docs/plan.md`
- `docs/implement.md`
- `docs/documentation.md`
- `docs/ui-spec.md`
- `docs/api-contract.md`
- `docs/qa.md`

### Validation / Done when
- All required planning docs exist and align with the local-runtime / remote-console split.
- No planning document implies direct browser file execution.

### Failure repair prompt

```text
Re-open the repo at `~/desktop/datamanager` and repair Stage 0 only.

Find every missing or contradictory planning artifact, especially any wording that implies the web console executes local file operations.
Do not start new feature code.
Patch the docs until all Stage 0 validation commands pass, then update `docs/implement.md` with the repairs made and remaining risks.
```

---

## [Stage 1] Greenfield Bootstrap

- **Why this stage exists**  
  Create a minimal but reproducible repo shell that can run, test, lint, typecheck, build, and host a basic runtime/API/UI stub.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: High  
- **Suggested tools/skills**: Python packaging, FastAPI, SQLite, Playwright, docs  
- **Worktree recommendation**: main worktree

### Copy-paste prompt

```text
Goal
Bootstrap a minimal reproducible greenfield repo for Footage Data Manager at `~/desktop/datamanager` with a runnable application shell, validation tooling, and a static remote console shell.

Context
- This is a greenfield implementation.
- The architecture split is fixed:
  - local runtime executes real work
  - API/Sync layer exposes REST + WebSocket
  - remote web console only consumes API/state
- Prefer a conservative Python-first stack for v1.
- Unless you document a concrete limitation first in `docs/plan.md`, keep the remote web console as static HTML/CSS/JS modules served by FastAPI instead of introducing a heavy front-end framework.

Constraints
- Work in `~/desktop/datamanager`; create it if missing.
- Read these files first:
  - `AGENTS.md`
  - `docs/prompt.md`
  - `docs/plan.md`
  - `docs/api-contract.md`
  - `docs/ui-spec.md`
  - `docs/qa.md`
- Set up a repo structure aligned with the product boundary. Recommended structure:
  - `app/runtime/`
  - `app/api/`
  - `app/persistence/`
  - `app/parsers/`
  - `app/web_console/`
  - `app/local_panel/`
  - `tests/`
  - `scripts/`
  - `docs/`
- Add project tooling so these commands can exist by the end of the stage:
  - lint
  - format check
  - typecheck
  - tests
  - package build
  - Playwright smoke
- Keep functionality shallow in this stage: shell only, not the real offload pipeline.

Deliverables
1. Python project/package metadata (`pyproject.toml` or equivalent) with dev dependencies.
2. FastAPI app skeleton with:
   - `/api/runtime/status` returning a stub runtime payload
   - a WebSocket stub endpoint
   - static file or template serving for the web console shell
3. Initial package layout under `app/`.
4. SQLite/bootstrap configuration skeleton and migration discipline (Alembic or a documented equivalent).
5. Static web console shell with:
   - top-level layout
   - placeholder runtime status region
   - primary CTA placeholder
   - empty/loading/error placeholders
   - shared design tokens CSS
6. Testing/tooling:
   - Pytest
   - Ruff
   - MyPy
   - Python build command
   - Python Playwright smoke test
7. Repo basics:
   - `.gitignore`
   - `.env.example`
   - `README.md` stub
   - developer scripts or make-like commands for local run/test

Done when
- The application starts locally.
- `/api/runtime/status` returns a stub payload.
- The console home shell loads in a browser.
- Lint, typecheck, tests, build, and Playwright smoke all pass.
- The repo layout does not imply direct file-system logic in the web console.

Validation
- Run all of the following and fix until they pass:
  - `mkdir -p ~/desktop/datamanager && cd ~/desktop/datamanager`
  - project install command
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest -q`
  - `python -m build`
  - start the app locally
  - `curl -fsS http://127.0.0.1:8000/api/runtime/status`
  - Playwright smoke for the home page and the primary CTA shell
- If any command is missing, add the missing tooling/scripts before stopping.

Reporting / update files
- Update `docs/implement.md` with:
  - chosen bootstrap stack
  - repo layout
  - exact commands to run
  - known gaps intentionally left for later stages
- Update `docs/documentation.md` and `README.md` with the local run/bootstrap path.
- Keep diffs small and reviewable.
```

### Expected artifacts/files
- `pyproject.toml` (or documented equivalent)
- app skeleton under `app/`
- `tests/`
- `scripts/`
- `.env.example`
- `README.md`
- Playwright smoke test assets
- updated docs

### Validation / Done when
- A minimal app shell runs and all baseline validations pass.

### Failure repair prompt

```text
Repair Stage 1 only.

Re-open `~/desktop/datamanager`, read the Stage 1 requirements from the docs, and fix whichever bootstrap validation commands still fail.
Do not implement deep product features yet.
Keep the architecture boundary intact, keep diffs narrow, rerun all Stage 1 validations, and update `docs/implement.md` with exactly what was repaired.
```

---

## [Stage 2] Architecture & Milestone Planning

- **Why this stage exists**  
  Convert the product spec into implementation-ready contracts so later stages stay small, verifiable, and consistent.

- **Recommended Codex mode**: Plan  
- **Suggested reasoning level**: High  
- **Suggested tools/skills**: docs, architecture, state machines, QA planning  
- **Worktree recommendation**: main worktree

### Copy-paste prompt

```text
Goal
Turn the frozen product spec and bootstrap repo into implementation-ready architecture and milestone contracts.

Context
- The product boundary is already fixed.
- The repo shell exists.
- The next work must be milestone-driven, with explicit acceptance criteria and validation commands.

Constraints
- Work in `~/desktop/datamanager`.
- Read first:
  - `AGENTS.md`
  - `docs/plan.md`
  - `docs/api-contract.md`
  - `docs/ui-spec.md`
  - `docs/qa.md`
  - current repo layout
- This stage is planning-first. Avoid significant implementation work unless a tiny scaffold change is required to make a contract concrete.
- Break the work into small milestones. Each milestone must define:
  - scope
  - out-of-scope
  - touched modules/files
  - acceptance criteria
  - validation commands
  - rollback / risk notes
- Explicitly document:
  - request flow: browser -> API -> runtime -> persistence -> WebSocket -> browser
  - module ownership boundaries
  - state transition matrix
  - command acceptance/rejection rules
  - report generation pipeline boundaries
  - data model inventory for jobs, events, file results, clips, reports, settings, volumes
  - fixture strategy for testing without proprietary media
  - real-BRAW integration gate vs mock-based development

Deliverables
1. Update `docs/plan.md` into an implementation-ready milestone plan.
2. Expand `docs/api-contract.md` with:
   - endpoint contracts
   - request/response shapes
   - error shapes
   - event shapes
   - auth assumptions
3. Expand `docs/ui-spec.md` with:
   - screen-by-screen responsibilities
   - state inventory (empty/loading/error/success/warn/paused/etc.)
   - mobile vs desktop behavior
   - action hierarchy
   - design-token rules
4. Add or update a data-model document (create `docs/data-model.md` if helpful) containing:
   - entities
   - candidate keys
   - nullable fields
   - report artifact relationships
   - recovery-critical fields
5. Update `docs/qa.md` with milestone-specific validation matrices and scenario tests.

Done when
- Milestones are small, ordered, and independently verifiable.
- Every major module has a clear owner boundary.
- The state machine and command matrix are explicit enough to implement without guessing.
- Real-media/BRAW uncertainty is isolated behind a documented gate.

Validation
- Run:
  - `grep -n "Milestone" docs/plan.md`
  - `grep -n "state" docs/api-contract.md docs/plan.md`
  - `grep -n "WebSocket" docs/api-contract.md`
  - `grep -n "mobile" docs/ui-spec.md`
  - `grep -n "validation" docs/qa.md`
  - `test -f docs/data-model.md || true`
- Manually verify there is no milestone that mixes unrelated major concerns into one large untestable step.
- If a milestone is too large, split it before stopping.

Reporting / update files
- Update `docs/implement.md` with the final milestone list and the next concrete implementation stage.
- If you create `docs/data-model.md`, add it to `docs/documentation.md`.
```

### Expected artifacts/files
- updated `docs/plan.md`
- updated `docs/api-contract.md`
- updated `docs/ui-spec.md`
- updated `docs/qa.md`
- optional `docs/data-model.md`

### Validation / Done when
- Milestones are actionable and testable without hidden assumptions.

### Failure repair prompt

```text
Repair Stage 2 planning only.

Find any milestone that is too broad, under-specified, or missing validation.
Tighten the contracts, clarify module ownership, and make the state/command matrix explicit.
Do not start major feature implementation in this repair pass.
```

---

## [Stage 3] Foundation Build

- **Why this stage exists**  
  Build the reusable foundations that every later feature sprint depends on.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: High  
- **Suggested tools/skills**: FastAPI, SQLite, migrations, state models, Playwright  
- **Worktree recommendation**: main worktree

### Copy-paste prompt

```text
Goal
Implement the project foundations for runtime orchestration, persistence, API/auth skeletons, and the console shell without building the full feature depth yet.

Context
- The repo bootstrap and milestone plan already exist.
- The app must support a local executor and a remote observer/controller.
- This stage creates the common substrate for all later sprints.

Constraints
- Work in `~/desktop/datamanager`.
- Read before changing code:
  - `AGENTS.md`
  - `docs/plan.md`
  - `docs/api-contract.md`
  - `docs/ui-spec.md`
  - `docs/qa.md`
- Keep this stage focused on foundations only.
- Implement:
  - runtime settings/config loader
  - persistence base, sessions, migrations, and initial models for:
    - jobs
    - job_events
    - job_files
    - clips
    - reports
    - system_volumes
    - settings
  - repository/service boundaries
  - state enums and command models
  - runtime agent skeleton
  - scheduler skeleton for single-active-job policy
  - event bus / publisher abstraction
  - volume provider abstraction with a mock provider
  - token auth skeleton for API access
  - REST/WS skeleton endpoints
  - console shell with global layout, nav, status banner, primary CTA placeholder, and empty/loading/error states
  - minimal local operator panel stub (not the full feature)
  - fixture generator scripts for local test media directories
- Do not implement full copy/verify/parse/report logic here.

Deliverables
1. Foundation code for runtime, persistence, API, and console shell.
2. Initial migrations and model definitions.
3. Mock-ready abstractions for volumes and events.
4. A basic but truthful UI shell that communicates the local-runtime executor model.
5. Test coverage for the foundations.

Done when
- The server boots from the new foundation code.
- The database initializes cleanly.
- A console shell renders and can fetch/display stub runtime state.
- Auth skeleton exists.
- Foundation validations pass.

Validation
- Run and fix until passing:
  - repo install command
  - migration apply command
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest -q`
  - `python -m build`
  - start the app locally
  - `curl -fsS http://127.0.0.1:8000/api/runtime/status`
  - Playwright smoke against the console shell
- Add targeted tests for:
  - settings loading
  - DB/session lifecycle
  - state enum import and serialization
  - auth guard behavior
  - console shell rendering/loading/error placeholder states

Reporting / update files
- Update `docs/implement.md` with:
  - foundation modules added
  - migrations introduced
  - known intentionally stubbed areas
  - exact next sprint
- Update `docs/documentation.md` with a short architecture map.
- Keep diffs small and avoid speculative abstractions.
```

### Expected artifacts/files
- foundation code across `app/runtime`, `app/api`, `app/persistence`, `app/web_console`, `app/local_panel`
- migrations
- fixture scripts
- tests
- updated docs

### Validation / Done when
- The substrate exists and later sprints can build on it without architectural rework.

### Failure repair prompt

```text
Repair Stage 3 foundations only.

Find whichever foundation validations are failing or whichever boundaries are still blurred.
Do not add deep feature behavior.
Fix the foundations, add missing tests, rerun all Stage 3 validations, and update `docs/implement.md` with the repair summary.
```

---

## [Stage 4.1] Sprint 0 — BRAW Capability Gate

- **Why this stage exists**  
  BRAW media handling was an early uncertainty. Current production scope is clone-only; keep parser/capability work legacy and do not depend on frame capture here.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: Extra High  
- **Suggested tools/skills**: parser design, SDK boundary design, tests, docs  
- **Worktree recommendation**: separate worktree recommended, e.g. `wt/braw-gate`

### Copy-paste prompt

#### A. Sprint Contract Prompt

```text
Goal
Create a precise sprint contract for the BRAW capability gate.

Context
- This sprint exists to preserve truthful legacy BRAW parser boundaries without making frame capture part of this app.
- The parser runs only inside the local runtime.
- The project must never fake BRAW capability if SDK/media access is unavailable.

Constraints
- Work in `~/desktop/datamanager`.
- Read all planning docs and the foundation code first.
- Create `docs/sprints/sprint-0-braw-gate.md`.
- The contract must define:
  - scope
  - out-of-scope
  - touched files/modules
  - acceptance criteria
  - validation commands
  - blockers
  - how mock development differs from real BRAW integration
  - exact rules for “truthful unavailable capability”

Deliverables
- `docs/sprints/sprint-0-braw-gate.md`

Done when
- The contract is concrete enough that implementation can proceed without guessing.

Validation
- `test -f docs/sprints/sprint-0-braw-gate.md`
- Ensure the contract explicitly forbids fake metadata/frame outputs.

Reporting / update files
- Update `docs/implement.md` with the sprint contract path and the next implementation action.
```

#### B. Implementation Prompt

```text
Goal
Implement the BRAW capability gate: parser contract, registry, capability model, truthful real-adapter boundary, mocks, and a proof command for metadata capability.

Context
- The parser layer executes only in the local runtime.
- Real BRAW support may depend on SDK/media availability.
- A truthful unavailable state is acceptable in development; fake success is not.

Constraints
- Work in `~/desktop/datamanager`.
- Read:
  - `AGENTS.md`
  - `docs/sprints/sprint-0-braw-gate.md`
  - `docs/plan.md`
  - `docs/data-model.md` if present
- Touch parser-related modules and minimal supporting docs/tests/scripts only.
- Implement:
  - parser base contract
  - registry
  - probe result / capability result models
  - explicit capability states (e.g. available / unavailable / partial)
  - BRAW adapter boundary
  - environment/config-based SDK detection
  - deterministic mock parser for tests
  - `scripts/check_braw_capability.py`
- If no real BRAW SDK or sample file exists, return truthful unavailable/partial results and document the blocker.
- Do not fake parsed metadata or frame captures.
- Do not implement unrelated runtime/API/UI features here.

Deliverables
- parser base + registry
- BRAW adapter boundary
- capability check script
- tests for mock parser and failure/unavailable behavior
- docs updates describing the real-integration gate

Done when
- The parser contract is stable and tested.
- The capability check script truthfully reports the environment status.
- Mock-based tests pass.
- The repo clearly separates mock development from real-BRAW readiness.

Validation
- Run and fix until passing:
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest tests/parsers -q`
  - `python scripts/check_braw_capability.py`
  - if a real sample exists: `BRAW_SAMPLE=/path/to/sample.braw python scripts/check_braw_capability.py`
  - `python -m build`

Reporting / update files
- Update `docs/implement.md` with:
  - what is real vs mocked
  - exact blockers for full BRAW readiness
  - next sprint dependency status
- Update the sprint doc with final implementation notes.
```

#### C. Evaluator / QA Prompt

```text
Goal
Evaluate Sprint 0 — BRAW Capability Gate without modifying implementation code.

Context
- The sprint should produce a truthful parser contract and capability gate.
- False claims of BRAW support are a hard fail.

Constraints
- Work in `~/desktop/datamanager`.
- Read:
  - `docs/sprints/sprint-0-braw-gate.md`
  - changed parser files
  - parser tests
  - `docs/implement.md`
- Do not edit implementation code in this evaluator pass.
- Create `docs/qa/sprint-0-braw-gate-eval.md`.

Deliverables
Score each area from 0 to 5 and produce a pass/fail verdict:
- Spec fidelity / product depth
- Functionality
- Code quality / maintainability
- Validation completeness
- Risk honesty / capability truthfulness
For UI-related categories, mark N/A if untouched and explain why.

Done when
- The evaluator document exists with explicit pass/fail.
- If any scored category is below 4/5, or if any required validation is missing, mark FAIL.
- If FAIL, list exact repair actions.
- Do not allow the next milestone to begin on FAIL.

Validation
- Re-run the sprint validation commands as part of the audit.
- Verify that no code path fabricates successful metadata/frame capture when the capability is unavailable.

Reporting / update files
- Save the verdict to `docs/qa/sprint-0-braw-gate-eval.md`.
- Update `docs/implement.md` with pass/fail status and next action.
```

### Expected artifacts/files
- `docs/sprints/sprint-0-braw-gate.md`
- parser contract modules
- `scripts/check_braw_capability.py`
- `docs/qa/sprint-0-braw-gate-eval.md`

### Validation / Done when
- The BRAW risk is isolated behind a truthful, testable contract.

### Failure repair prompt

```text
Re-open `~/desktop/datamanager` and repair only the failures recorded in `docs/qa/sprint-0-braw-gate-eval.md`.

Focus on the exact failing parser behaviors, tests, or documentation gaps.
Do not broaden scope.
Rerun the full sprint validation set, overwrite the evaluator result if the fixes now pass, and keep the next milestone blocked until the evaluator is PASS.
```

---

## [Stage 4.2] Sprint 1 — Runtime State Machine & Persistence

- **Why this stage exists**  
  The job lifecycle, scheduler, and persistence model define the backbone of the product and must be correct before real copy work is layered in.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: High  
- **Suggested tools/skills**: state machines, SQLite, migrations, recovery testing  
- **Worktree recommendation**: main worktree

### Copy-paste prompt

#### A. Sprint Contract Prompt

```text
Goal
Create the sprint contract for runtime state machine, scheduler policy, and persistence behavior.

Context
- v1 allows exactly one active offload job.
- Recoverable jobs after restart include `QUEUED`, `PAUSED`, `WARN`, and `FAILED`.
- Commands are requests; the runtime decides whether they are accepted based on current state.

Constraints
- Work in `~/desktop/datamanager`.
- Read planning docs and existing foundations first.
- Create `docs/sprints/sprint-1-runtime-state.md`.
- Define:
  - canonical states
  - allowed transitions
  - command acceptance rules
  - recovery semantics
  - persistence responsibilities
  - out-of-scope boundary (no deep copy pipeline yet)

Deliverables
- `docs/sprints/sprint-1-runtime-state.md`

Done when
- The contract defines the runtime lifecycle precisely enough to implement and test.

Validation
- `test -f docs/sprints/sprint-1-runtime-state.md`
- Verify the contract does not add accidental extra executor logic to the API/UI layers.

Reporting / update files
- Update `docs/implement.md` with the contract path and the next implementation task.
```

#### B. Implementation Prompt

```text
Goal
Implement the runtime state machine, scheduler, repositories, event history, and restart-recovery scaffolding.

Context
- This sprint builds the lifecycle backbone, not the full copy engine.
- The scheduler must enforce one active job at a time.
- The runtime owns state transitions and command acceptance.

Constraints
- Work in `~/desktop/datamanager`.
- Read the sprint contract and planning docs first.
- Implement:
  - canonical job state enum and transition rules
  - command request models and acceptance/rejection results
  - persistence for jobs/job_events and related lifecycle fields
  - append-only event recording
  - single-active-job scheduler
  - recovery loader that can restore eligible jobs after restart
  - deterministic test helpers or stub workers for state progression
- Preserve the architecture boundary:
  - API transports commands
  - runtime decides
  - persistence records
- Do not implement deep file copy/verification here.

Deliverables
- runtime lifecycle code
- scheduler code
- persistence/repository updates
- migration updates
- tests for transitions, command rules, and restart recovery

Done when
- Jobs can be created, queued, advanced through stubbed lifecycle transitions, and recovered after restart according to contract.
- Command acceptance/rejection is deterministic and tested.
- Append-only event history is persisted.

Validation
- Run and fix until passing:
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest tests/runtime tests/persistence -q`
  - any recovery simulation script you add
  - `python -m build`

Reporting / update files
- Update `docs/implement.md` with:
  - state model details implemented
  - recovery behavior
  - any open edge cases
- Update the sprint contract with final implementation notes.
```

#### C. Evaluator / QA Prompt

```text
Goal
Evaluate Sprint 1 — Runtime State Machine & Persistence.

Context
- This sprint should make lifecycle behavior explicit, deterministic, and recoverable.
- Hidden or ad-hoc transitions are a fail condition.

Constraints
- Work in `~/desktop/datamanager`.
- Read the sprint contract, changed files, and tests.
- Do not edit implementation code in this evaluator pass.
- Create `docs/qa/sprint-1-runtime-state-eval.md`.

Deliverables
Score 0 to 5 and give pass/fail for:
- Spec fidelity / product depth
- Functionality
- Code quality / maintainability
- Validation completeness
- Recovery correctness
- Module boundary discipline

Done when
- The evaluation file exists.
- Any category below 4/5 is FAIL.
- On FAIL, list exact repairs and block the next milestone.

Validation
- Re-run the sprint validation commands.
- Specifically inspect restart-recovery behavior and command rejection paths.

Reporting / update files
- Save to `docs/qa/sprint-1-runtime-state-eval.md`.
- Update `docs/implement.md` with the verdict and next action.
```

### Expected artifacts/files
- `docs/sprints/sprint-1-runtime-state.md`
- runtime lifecycle modules
- persistence/migration updates
- `docs/qa/sprint-1-runtime-state-eval.md`

### Validation / Done when
- State transitions, scheduler policy, and recovery scaffolding are explicit and test-backed.

### Failure repair prompt

```text
Re-open `~/desktop/datamanager` and repair only the issues recorded in `docs/qa/sprint-1-runtime-state-eval.md`.

Keep scope limited to lifecycle, scheduler, persistence, and recovery correctness.
Rerun the full sprint validation set, update the evaluator file, and do not move to the next milestone until the verdict is PASS.
```

---

## [Stage 4.3] Sprint 2 — Offload & Checksum Pipeline

- **Why this stage exists**  
  This sprint implements the real file-work core of the product: scan, copy, verify, collision policy, and destination handling.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: Extra High  
- **Suggested tools/skills**: filesystem operations, checksum workflows, temp-fixture testing  
- **Worktree recommendation**: main worktree

### Copy-paste prompt

#### A. Sprint Contract Prompt

```text
Goal
Create the sprint contract for volume scan, offload execution, checksum verification, destination policy, and file-level result recording.

Context
- The local runtime is the only executor of actual file operations.
- v1 supports one active job.
- The web console will later consume only the persisted results and runtime events.
- The spec requires:
  - source scan
  - main and backup copy
  - checksum verification
  - no blind overwrite on name collision
  - exclusion of `.DS_Store` and `._*`

Constraints
- Work in `~/desktop/datamanager`.
- Create `docs/sprints/sprint-2-offload-checksum.md`.
- Define:
  - scope and out-of-scope
  - touched files/modules
  - folder-structure policy
  - collision policy
  - partial-failure semantics (`WARN` vs `FAILED`)
  - device removal handling as reason/error codes unless the docs explicitly introduce a justified extra state
  - validation plan using temp directories and synthetic fixtures

Deliverables
- `docs/sprints/sprint-2-offload-checksum.md`

Done when
- The contract makes the offload rules concrete enough to implement and test without ambiguity.

Validation
- `test -f docs/sprints/sprint-2-offload-checksum.md`

Reporting / update files
- Update `docs/implement.md` with the contract path and the next implementation action.
```

#### B. Implementation Prompt

```text
Goal
Implement the real offload and checksum pipeline for the local runtime.

Context
- This is the first sprint that performs real file operations.
- The runtime must:
  - discover source/allowed destination volumes
  - scan supported files
  - build destination structure
  - copy to main/backup
  - compute and compare checksums
  - persist file-level outcomes
- The web console is still not allowed to touch the file system directly.

Constraints
- Work in `~/desktop/datamanager`.
- Read the sprint contract and lifecycle code first.
- Implement:
  - volume discovery service for macOS + mock provider for tests
  - source scan logic and supported-file filtering
  - exclude patterns for `.DS_Store` and `._*`
  - destination scaffold creation following the project folder policy
  - main/backup copy workers
  - checksum generation and comparison
  - file-level result persistence
  - collision handling with no blind overwrite
  - partial failure semantics (`WARN` when allowed by spec, `FAILED` when unrecoverable)
  - safe checkpoints to support future pause/cancel integration
- Use temp directories and synthetic fixtures for tests.
- Do not move parsing/report/UI logic into this sprint.

Deliverables
- offload worker implementation
- verify/checksum implementation
- persistence wiring for file results
- tests for success, collision, backup failure, excluded files, and device-removal/error simulation
- any helper scripts needed for local fixture generation

Done when
- A synthetic source set can be offloaded to main/backup destinations through the runtime.
- File results and checksum outcomes are persisted.
- Partial-failure behavior is deterministic and tested.
- The implementation remains strictly inside the runtime layer.

Validation
- Run and fix until passing:
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest tests/runtime tests/persistence -q`
  - any offload/checksum scenario tests you add
  - `python -m build`

Reporting / update files
- Update `docs/implement.md` with:
  - offload rules implemented
  - current known limitations
  - remaining work before full end-to-end completion
- Update the sprint contract with implementation notes.
```

#### C. Evaluator / QA Prompt

```text
Goal
Evaluate Sprint 2 — Offload & Checksum Pipeline.

Context
- This sprint is successful only if the runtime is the sole executor of file work and file-level results are correctly persisted.
- Hidden overwrite behavior or unclear warning/failure semantics are fail conditions.

Constraints
- Work in `~/desktop/datamanager`.
- Read the sprint contract, changed files, tests, and `docs/implement.md`.
- Do not edit implementation code in this evaluator pass.
- Create `docs/qa/sprint-2-offload-checksum-eval.md`.

Deliverables
Score 0 to 5 and give pass/fail for:
- Spec fidelity / product depth
- Functionality
- Code quality / maintainability
- Validation completeness
- Runtime-only file authority
- Failure-handling correctness

Done when
- The evaluator doc exists.
- Any category below 4/5 is FAIL and blocks the next milestone.
- FAIL must include exact repair actions.

Validation
- Re-run the sprint validation commands.
- Inspect that collision handling, excluded files, and partial-failure behavior are explicitly tested.

Reporting / update files
- Save to `docs/qa/sprint-2-offload-checksum-eval.md`.
- Update `docs/implement.md` with the verdict and next action.
```

### Expected artifacts/files
- `docs/sprints/sprint-2-offload-checksum.md`
- offload/checksum runtime modules
- scenario tests and fixtures
- `docs/qa/sprint-2-offload-checksum-eval.md`

### Validation / Done when
- The runtime can perform the core offload/verify path using synthetic fixtures with deterministic results.

### Failure repair prompt

```text
Re-open `~/desktop/datamanager` and repair only the failures recorded in `docs/qa/sprint-2-offload-checksum-eval.md`.

Keep the scope constrained to scan/copy/verify/collision/result-recording behavior.
Rerun the full sprint validation set, update the evaluator file, and do not move forward until the verdict is PASS.
```

---

## [Stage 4.4] Sprint 3 — Parsing, Frame Capture & Reports

- **Why this stage exists**  
  This sprint converts verified footage results into metadata, preview imagery, and deliverable report artifacts.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: Extra High  
- **Suggested tools/skills**: parser integration, PDF/XLSX artifact generation, report design  
- **Worktree recommendation**: separate worktree recommended if BRAW integration remains risky

### Copy-paste prompt

#### A. Sprint Contract Prompt

```text
Goal
Create the sprint contract for clone report generation and artifact persistence.

Context
- The clone/offload pipeline already exists.
- This sprint should generate report artifacts after copy/verification.
- Required artifacts:
  - checksum PDF
  - manifest.json

Constraints
- Work in `~/desktop/datamanager`.
- Create `docs/sprints/sprint-3-parse-capture-reports.md`.
- Define:
  - scope and out-of-scope
  - touched files/modules
  - when reporting occurs in the job lifecycle
  - required artifact outputs and persistence records
  - fallback/partial behavior when clone artifacts cannot be created
  - what blocks v1 completion vs what is acceptable as a documented development gap

Deliverables
- `docs/sprints/sprint-3-parse-capture-reports.md`

Done when
- The contract clearly distinguishes ready, partial, and failed clone artifact states.

Validation
- `test -f docs/sprints/sprint-3-parse-capture-reports.md`

Reporting / update files
- Update `docs/implement.md` with the contract path and next implementation action.
```

#### B. Implementation Prompt

```text
Goal
Implement clone report artifact generation in the runtime.

Context
- Report outputs must be persisted and exposed later through the API as read-only artifacts.
- Truthful artifact handling still applies: do not fake reports.

Constraints
- Work in `~/desktop/datamanager`.
- Read:
  - `docs/sprints/sprint-3-parse-capture-reports.md`
  - offload/checksum implementation
- Implement:
  - checksum PDF generation
  - final manifest.json generation
  - report/artifact persistence records
- Keep report visual language simple, clean, black/white-first, and operationally useful.
- Do not move report-generation concerns into the web console.

Deliverables
- runtime clone report module
- artifact generation code
- persistence for reports
- tests using mock parser and conditional real-BRAW integration checks
- docs updates on capability status and artifact behavior

Done when
- Verified jobs can produce checksum and manifest artifacts through the runtime path.
- Artifacts are persisted and indexable.
- Mock/integration tests cover both success and unavailable paths.

Validation
- Run and fix until passing:
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest tests/parsers tests/runtime tests/persistence -q`
  - any artifact-generation smoke commands you add
  - `python scripts/check_braw_capability.py`
  - `python -m build`

Reporting / update files
- Update `docs/implement.md` with:
  - which artifact paths are complete
  - what is real vs mocked
  - any blockers for full production-grade BRAW support
- Update the sprint contract with implementation notes.
```

#### C. Evaluator / QA Prompt

```text
Goal
Evaluate Sprint 3 — Parsing, Frame Capture & Reports.

Context
- This sprint is complete only if report artifacts are runtime-generated and capability truthfulness is preserved.
- Fake image/report completeness is a hard fail.

Constraints
- Work in `~/desktop/datamanager`.
- Read the sprint contract, changed files, tests, and `docs/implement.md`.
- Do not edit implementation code in this evaluator pass.
- Create `docs/qa/sprint-3-parse-capture-reports-eval.md`.

Deliverables
Score 0 to 5 and give pass/fail for:
- Spec fidelity / product depth
- Functionality
- Code quality / maintainability
- Validation completeness
- Artifact quality / usefulness
- Capability truthfulness

Done when
- The evaluation file exists.
- Any category below 4/5 is FAIL and blocks the next milestone.
- FAIL must include exact repair actions.

Validation
- Re-run the sprint validation commands.
- Verify that artifacts come from runtime code and that unavailable capture does not produce fake outputs.

Reporting / update files
- Save to `docs/qa/sprint-3-parse-capture-reports-eval.md`.
- Update `docs/implement.md` with the verdict and next action.
```

### Expected artifacts/files
- `docs/sprints/sprint-3-parse-capture-reports.md`
- parse/capture/report runtime code
- report artifact tests
- `docs/qa/sprint-3-parse-capture-reports-eval.md`

### Validation / Done when
- The runtime can generate truthful metadata/report outputs and record them.

### Failure repair prompt

```text
Re-open `~/desktop/datamanager` and repair only the failures recorded in `docs/qa/sprint-3-parse-capture-reports-eval.md`.

Do not broaden scope beyond parsing/capture/report generation and artifact persistence.
Rerun the full sprint validation set, update the evaluator file, and keep the next milestone blocked until the verdict is PASS.
```

---

## [Stage 4.5] Sprint 4 — API / WebSocket / Command Layer

- **Why this stage exists**  
  This sprint exposes the runtime to the remote console without leaking execution authority into the web layer.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: High  
- **Suggested tools/skills**: FastAPI, WebSocket, auth, API testing  
- **Worktree recommendation**: main worktree

### Copy-paste prompt

#### A. Sprint Contract Prompt

```text
Goal
Create the sprint contract for the API, WebSocket sync, token auth, and command transport layer.

Context
- The runtime already owns state, file execution, parsing, and report generation.
- The API layer must expose that state and forward commands without becoming a second executor.

Constraints
- Work in `~/desktop/datamanager`.
- Create `docs/sprints/sprint-4-api-sync.md`.
- Define:
  - scope and out-of-scope
  - exact endpoints to implement
  - exact WebSocket event contract
  - auth expectations
  - read-only vs command-writing routes
  - accepted/rejected command response behavior
  - reconnect semantics

Deliverables
- `docs/sprints/sprint-4-api-sync.md`

Done when
- The contract is explicit enough to implement and test without guessing.

Validation
- `test -f docs/sprints/sprint-4-api-sync.md`

Reporting / update files
- Update `docs/implement.md` with the contract path and next implementation action.
```

#### B. Implementation Prompt

```text
Goal
Implement the runtime-facing API, WebSocket sync, token auth, and command transport layer.

Context
- The spec requires endpoints for runtime status, volumes, jobs, job detail, logs, reports, clips, settings, and command dispatch.
- The API is not allowed to implement direct file work.
- The runtime remains the decision-maker for actual state transitions.

Constraints
- Work in `~/desktop/datamanager`.
- Read:
  - `docs/sprints/sprint-4-api-sync.md`
  - `docs/api-contract.md`
  - runtime and persistence code
- Implement:
  - runtime status route
  - volumes route
  - jobs list/create/detail routes
  - logs route
  - reports list/download route
  - clips route
  - settings get/patch route
  - command dispatch route
  - WebSocket event streaming
  - token auth guard
  - accepted/rejected command persistence/audit behavior
- Keep all file execution inside runtime/service modules.
- Add API tests, WebSocket tests, and auth negative tests.
- Avoid business logic duplication between API and runtime.

Deliverables
- API routes and schemas
- WebSocket broadcaster/subscription flow
- auth implementation for v1 token model
- tests for route behavior, command rejection, and reconnect/state sync basics

Done when
- The remote layer can query state, read logs/reports, and send commands through the API/WS contract.
- Command acceptance/rejection behavior is explicit and persisted.
- Unauthorized access is rejected.
- No direct file logic appears in API route handlers.

Validation
- Run and fix until passing:
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest tests/api tests/runtime tests/persistence -q`
  - any live API/WS smoke commands you add
  - `python -m build`

Reporting / update files
- Update `docs/implement.md` with:
  - API coverage implemented
  - auth model status
  - any remaining gaps before UI integration
- Update the sprint contract with implementation notes.
```

#### C. Evaluator / QA Prompt

```text
Goal
Evaluate Sprint 4 — API / WebSocket / Command Layer.

Context
- This sprint should expose the runtime cleanly without moving execution logic into the transport layer.
- Route handlers that do direct file work are a fail condition.

Constraints
- Work in `~/desktop/datamanager`.
- Read the sprint contract, changed files, tests, and `docs/implement.md`.
- Do not edit implementation code in this evaluator pass.
- Create `docs/qa/sprint-4-api-sync-eval.md`.

Deliverables
Score 0 to 5 and give pass/fail for:
- Spec fidelity / product depth
- Functionality
- Code quality / maintainability
- Validation completeness
- Auth/security correctness
- Module boundary discipline

Done when
- The evaluation file exists.
- Any category below 4/5 is FAIL and blocks the next milestone.
- FAIL must include exact repair actions.

Validation
- Re-run the sprint validation commands.
- Verify that route handlers delegate to runtime/service layers and do not perform file execution directly.

Reporting / update files
- Save to `docs/qa/sprint-4-api-sync-eval.md`.
- Update `docs/implement.md` with the verdict and next action.
```

### Expected artifacts/files
- `docs/sprints/sprint-4-api-sync.md`
- API/WS/auth code
- route and socket tests
- `docs/qa/sprint-4-api-sync-eval.md`

### Validation / Done when
- The remote-control transport contract exists and remains a pure transport/observation layer.

### Failure repair prompt

```text
Re-open `~/desktop/datamanager` and repair only the failures recorded in `docs/qa/sprint-4-api-sync-eval.md`.

Keep scope limited to API, WebSocket, auth, and command transport behavior.
Rerun the full sprint validation set, update the evaluator file, and do not proceed until the verdict is PASS.
```

---

## [Stage 4.6] Sprint 5 — Remote Web Console Core UX

- **Why this stage exists**  
  This sprint turns the transport/API layer into an operator-facing browser console that is clear, responsive, and faithful to the executor/console split.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: High  
- **Suggested tools/skills**: HTML/CSS/JS, responsive UI, Playwright, accessibility  
- **Worktree recommendation**: separate UI worktree recommended, e.g. `wt/remote-console`

### Copy-paste prompt

#### A. Sprint Contract Prompt

```text
Goal
Create the sprint contract for the remote web console’s core screens, interactions, and responsive behavior.

Context
- The web console is a remote control and monitoring surface, not the execution engine.
- Required screens:
  - Home
  - New Job flow
  - Job Detail
  - Queue
  - Report Center
  - Settings
- The design language is black/white, no shadows, with clear CTA priority and explicit selection states.

Constraints
- Work in `~/desktop/datamanager`.
- Create `docs/sprints/sprint-5-remote-console.md`.
- Define:
  - scope and out-of-scope
  - screen responsibilities
  - primary CTA hierarchy
  - mobile/desktop behavior
  - empty/loading/error/success states
  - accessibility expectations
  - how the UI repeatedly communicates that real file work happens in the local runtime
  - exact Playwright flows

Deliverables
- `docs/sprints/sprint-5-remote-console.md`

Done when
- The contract makes the UI implementation and QA path concrete.

Validation
- `test -f docs/sprints/sprint-5-remote-console.md`

Reporting / update files
- Update `docs/implement.md` with the contract path and next implementation action.
```

#### B. Implementation Prompt

```text
Goal
Implement the remote web console core UX on top of the existing API/WS contract.

Context
- The console must let the user:
  - start a new offload job from runtime-detected sources/destinations
  - inspect runtime status
  - monitor job progress, speed, ETA, current file, warnings/errors
  - send pause/resume/cancel/retry
  - inspect queue state
  - open/download report artifacts
  - view/update allowed settings within the v1 scope
- The console must never browse the local file system directly.

Constraints
- Work in `~/desktop/datamanager`.
- Read:
  - `docs/sprints/sprint-5-remote-console.md`
  - `docs/ui-spec.md`
  - `docs/api-contract.md`
- Implement core screens:
  - Home
  - New Job flow
  - Job Detail
  - Queue
  - Report Center
  - Settings
- UX and visual rules:
  - black/white-first
  - no shadows
  - strong spacing and hierarchy
  - primary CTA visible in first viewport
  - selected states must use background change, not border only
  - avoid “card soup”; compose each screen intentionally
  - mobile should use a fixed bottom action bar or similarly obvious primary action pattern
  - repeatedly label that real file operations are running on the local runtime
- Technical rules:
  - consume REST + WebSocket only
  - no direct file-system access
  - use semantic HTML, keyboard-focus visibility, and accessible labels
- Add Playwright tests for desktop and mobile flows.

Deliverables
- implemented console screens and interactions
- shared UI tokens/styles
- REST/WS integration code
- empty/loading/error/success states
- Playwright tests and screenshot artifacts if useful

Done when
- Core operator flows work in the browser.
- The UI is responsive and clear on desktop and mobile.
- The console consistently reflects the runtime-executor model.
- Playwright flows pass.

Validation
- Run and fix until passing:
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest -q`
  - `python -m build`
  - Playwright desktop flows
  - Playwright mobile flows
- Ensure the browser code never attempts direct local file browsing or arbitrary path entry outside the runtime-provided options.

Reporting / update files
- Update `docs/implement.md` with:
  - screens completed
  - interaction gaps
  - responsive notes
  - any deferred UI polish
- Update the sprint contract with implementation notes.
```

#### C. Evaluator / QA Prompt

```text
Goal
Evaluate Sprint 5 — Remote Web Console Core UX.

Context
- This sprint is successful only if the browser console is functional, visually clear, responsive, and faithful to the architecture boundary.
- Any browser path that acts like a direct executor is a fail condition.

Constraints
- Work in `~/desktop/datamanager`.
- Read the sprint contract, changed files, Playwright coverage, and `docs/implement.md`.
- Do not edit implementation code in this evaluator pass.
- Create `docs/qa/sprint-5-remote-console-eval.md`.

Deliverables
Score 0 to 5 and give pass/fail for:
- Spec fidelity / product depth
- Functionality
- Visual design / UX clarity
- Code quality / maintainability
- Accessibility / responsiveness
- Validation completeness

Done when
- The evaluation file exists.
- Any category below 4/5 is FAIL and blocks the next milestone.
- FAIL must include exact repair actions.
- Explicitly call out any layout that looks generic, cluttered, or like “card soup.”

Validation
- Re-run the sprint validation commands.
- Inspect desktop and mobile screenshots/flows.
- Verify the UI text and actions reinforce that the runtime is doing the actual file work.

Reporting / update files
- Save to `docs/qa/sprint-5-remote-console-eval.md`.
- Update `docs/implement.md` with the verdict and next action.
```

### Expected artifacts/files
- `docs/sprints/sprint-5-remote-console.md`
- web console screens and styles
- Playwright flows and artifacts
- `docs/qa/sprint-5-remote-console-eval.md`

### Validation / Done when
- The remote console is operational, responsive, and visually intentional.

### Failure repair prompt

```text
Re-open `~/desktop/datamanager` and repair only the failures recorded in `docs/qa/sprint-5-remote-console-eval.md`.

Prioritize broken flows, poor hierarchy, weak responsive behavior, and any UI that obscures the runtime-executor model.
Rerun the full sprint validation set, update the evaluator file, and do not move forward until the verdict is PASS.
```

---

## [Stage 4.7] Sprint 6 — Recovery, Resilience & Local Operator Panel

- **Why this stage exists**  
  This sprint closes the loop on operational resilience: reconnects, restart recovery, end-to-end control actions, and a minimal local emergency/status surface.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: High  
- **Suggested tools/skills**: resilience testing, restart simulation, UI/state recovery  
- **Worktree recommendation**: separate worktree recommended if restart simulations are invasive

### Copy-paste prompt

#### A. Sprint Contract Prompt

```text
Goal
Create the sprint contract for browser reconnect behavior, runtime restart recovery, end-to-end control actions, and the minimal local operator panel.

Context
- The spec requires that browser disconnects do not stop the job.
- Recoverable jobs must survive runtime restart.
- The local operator panel is optional/minimal and must not become a second full product.

Constraints
- Work in `~/desktop/datamanager`.
- Create `docs/sprints/sprint-6-recovery-resilience.md`.
- Define:
  - scope and out-of-scope
  - restart/reconnect scenarios
  - pause/resume/cancel/retry end-to-end expectations
  - local operator panel responsibilities only
  - exact scenario tests required
  - how log parity will be checked between runtime persistence and remote views

Deliverables
- `docs/sprints/sprint-6-recovery-resilience.md`

Done when
- The contract is explicit enough to implement resilience without guesswork.

Validation
- `test -f docs/sprints/sprint-6-recovery-resilience.md`

Reporting / update files
- Update `docs/implement.md` with the contract path and next implementation action.
```

#### B. Implementation Prompt

```text
Goal
Implement recovery/resilience behavior end-to-end, plus a minimal local operator panel.

Context
- The runtime must continue running when browsers disconnect.
- On reconnect, the browser should reload current state and resume event subscription.
- Runtime restart should recover eligible jobs.
- The local operator panel is only for status, emergency control, and quick access to logs/results.

Constraints
- Work in `~/desktop/datamanager`.
- Read:
  - `docs/sprints/sprint-6-recovery-resilience.md`
  - lifecycle/offload/API/UI code
- Implement:
  - reconnect flow for browser sessions
  - runtime restart recovery for eligible jobs
  - end-to-end pause/resume/cancel/retry behavior wired through API -> runtime -> persistence -> UI
  - log parity checks between stored events and remote views
  - minimal local operator panel with:
    - runtime/network status
    - current active job summary
    - open logs/results
    - emergency stop/restart entry points if appropriate
- Keep the local panel minimal; choose the lowest-risk surface and document the choice.
- Do not turn the local panel into a second feature-complete UI.

Deliverables
- recovery/resilience code
- local operator panel implementation
- scenario tests for disconnect/reconnect, restart recovery, and end-to-end control actions
- docs updates

Done when
- Browser disconnect/reconnect no longer disrupts work.
- Recoverable jobs can be restored after runtime restart.
- Pause/resume/cancel/retry work end-to-end.
- The local operator panel remains intentionally minimal.

Validation
- Run and fix until passing:
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest -q`
  - `python -m build`
  - Playwright reconnect/reload scenarios
  - any restart simulation scripts you add
- Explicitly test:
  - browser reload during active job
  - runtime restart with recoverable jobs
  - backup-destination failure path
  - control-command acceptance/rejection reflected in logs and UI

Reporting / update files
- Update `docs/implement.md` with:
  - resilience scenarios completed
  - local panel technology choice and why
  - remaining operational gaps
- Update the sprint contract with implementation notes.
```

#### C. Evaluator / QA Prompt

```text
Goal
Evaluate Sprint 6 — Recovery, Resilience & Local Operator Panel.

Context
- This sprint is complete only if reconnect/restart/control scenarios are operationally credible.
- A bloated local panel or broken recovery path is a fail condition.

Constraints
- Work in `~/desktop/datamanager`.
- Read the sprint contract, changed files, scenario tests, and `docs/implement.md`.
- Do not edit implementation code in this evaluator pass.
- Create `docs/qa/sprint-6-recovery-resilience-eval.md`.

Deliverables
Score 0 to 5 and give pass/fail for:
- Spec fidelity / product depth
- Functionality
- Code quality / maintainability
- Validation completeness
- Operational resilience
- Scope discipline of local operator panel

Done when
- The evaluation file exists.
- Any category below 4/5 is FAIL and blocks the next milestone.
- FAIL must include exact repair actions.

Validation
- Re-run the sprint validation commands.
- Specifically inspect reconnect/restart scenarios and local-panel scope discipline.

Reporting / update files
- Save to `docs/qa/sprint-6-recovery-resilience-eval.md`.
- Update `docs/implement.md` with the verdict and next action.
```

### Expected artifacts/files
- `docs/sprints/sprint-6-recovery-resilience.md`
- resilience/recovery code
- local operator panel
- scenario tests
- `docs/qa/sprint-6-recovery-resilience-eval.md`

### Validation / Done when
- The product can survive disconnect/restart conditions without losing its executor/console model.

### Failure repair prompt

```text
Re-open `~/desktop/datamanager` and repair only the failures recorded in `docs/qa/sprint-6-recovery-resilience-eval.md`.

Keep scope limited to resilience, control-loop correctness, restart recovery, and minimal local-panel behavior.
Rerun the full sprint validation set, update the evaluator file, and do not move forward until the verdict is PASS.
```

---

## [Stage 5] UI/UX Refinement

- **Why this stage exists**  
  After functionality lands, refine the operator experience so the app feels intentional, calm under pressure, and easy to use on both desktop and mobile.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: Medium-High  
- **Suggested tools/skills**: Playwright, responsive design, accessibility review, screenshot comparison  
- **Worktree recommendation**: separate UI-polish worktree recommended, e.g. `wt/ui-polish`

### Copy-paste prompt

```text
Goal
Refine the remote web console UI/UX to improve hierarchy, spacing, responsiveness, action clarity, and operational calm without changing the core architecture.

Context
- No visual screenshots were provided, so `docs/ui-spec.md` is the visual source of truth.
- The product must avoid generic AI-template aesthetics, cluttered card grids, weak CTA priority, and decorative noise.
- The operator should understand the product purpose and the primary action immediately on first load.

Constraints
- Work in `~/desktop/datamanager`.
- Read:
  - `docs/ui-spec.md`
  - `docs/sprints/sprint-5-remote-console.md`
  - `docs/qa/sprint-5-remote-console-eval.md`
- Focus on:
  - stronger layout composition
  - clearer typography and spacing
  - CTA clarity
  - selected-state visibility
  - empty/loading/error/success states
  - desktop/mobile harmony
  - keyboard/focus behavior
  - status-chip clarity
  - report/log readability
- Keep the black/white-first design language and no-shadow rule.
- Do not introduce a new design system or visual parallel architecture.
- Do not change API contracts unless a specific UX blocker requires it and the reason is documented.

Deliverables
1. Refined UI implementation.
2. Playwright screenshot captures for desktop and mobile key screens.
3. `docs/ui-audit.md` (create if missing) summarizing:
   - before/after problems fixed
   - remaining weaknesses
   - accessibility/responsiveness observations

Done when
- The UI feels intentionally composed rather than assembled from unrelated cards.
- Primary actions are obvious.
- Key screens are cleaner and more legible on desktop and mobile.
- Playwright screenshot and flow checks pass.

Validation
- Run and fix until passing:
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest -q`
  - `python -m build`
  - Playwright desktop flows + screenshots
  - Playwright mobile flows + screenshots
- Manually inspect screenshot outputs and fix any weak hierarchy, crowded layout, or ambiguous selection state before stopping.

Reporting / update files
- Update `docs/implement.md` with:
  - screens refined
  - key UX problems solved
  - remaining polish backlog
- Save the audit to `docs/ui-audit.md`.
```

### Expected artifacts/files
- refined UI files
- screenshot artifacts
- `docs/ui-audit.md`

### Validation / Done when
- The UI is clearer, calmer, and more field-usable without architectural drift.

### Failure repair prompt

```text
Repair only the UI/UX issues that remain after Stage 5.

Use `docs/ui-audit.md`, Playwright screenshots, and the existing UI spec to identify the most visible hierarchy, spacing, responsiveness, and interaction-clarity problems.
Do not start new features.
Patch the UI, rerun the full Stage 5 validation set, refresh screenshots, and update the audit document.
```

---

## [Stage 6] Hardening

- **Why this stage exists**  
  Turn a feature-complete build into an operationally credible one by tightening QA, accessibility, security, performance, and edge-case handling.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: High  
- **Suggested tools/skills**: test design, security review, performance review, failure injection  
- **Worktree recommendation**: separate hardening worktree recommended, e.g. `wt/hardening`

### Copy-paste prompt

```text
Goal
Harden Footage Data Manager for operational use: deeper tests, stronger accessibility, safer auth/error handling, performance checks, migration stability, and cleanup without changing the core architecture.

Context
- The core features should already exist.
- This stage is about confidence, not feature expansion.
- Any refactor must stay bounded and justified by testability, correctness, or maintainability.

Constraints
- Work in `~/desktop/datamanager`.
- Read:
  - `docs/qa.md`
  - all sprint evaluator docs
  - `docs/ui-audit.md` if present
  - `docs/implement.md`
- Focus on:
  - deeper scenario coverage
  - auth/security negative tests
  - invalid-command handling
  - accessibility fixes
  - performance and bottleneck review
  - migration/recovery stability
  - logging/observability clarity
  - cleanup of risky code smells
- Do not add large new features.
- Keep refactors bounded, reviewable, and covered by tests.

Deliverables
1. Expanded QA coverage and scenario tests.
2. Accessibility and auth/security improvements.
3. Performance observations with concrete fixes if low-risk.
4. `docs/hardening.md` (create if missing) summarizing:
   - what was hardened
   - what remains risky
   - evidence from tests/scenarios
5. Updated `docs/qa.md` with final mandatory validation matrix.

Done when
- The app has credible coverage for the risky paths.
- Accessibility, auth, and failure-handling gaps are materially reduced.
- No validation class is silently skipped.
- The codebase is cleaner but not over-abstracted.

Validation
- Run and fix until passing:
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest -q`
  - `python -m build`
  - Playwright desktop flows
  - Playwright mobile flows
  - recovery/restart scenarios
  - auth negative tests
  - any targeted performance smoke or large-fixture tests you add
- Do not declare hardening done if any major risk remains untested and undocumented.

Reporting / update files
- Update `docs/implement.md` with the hardening summary and any known residual risks.
- Save the hardening report to `docs/hardening.md`.
- Update `docs/qa.md` with the final validation matrix.
```

### Expected artifacts/files
- expanded tests
- `docs/hardening.md`
- updated `docs/qa.md`
- possible small refactors and observability improvements

### Validation / Done when
- The risky paths are tested, documented, and materially safer.

### Failure repair prompt

```text
Repair only the failing or weak hardening areas.

Use `docs/hardening.md`, `docs/qa.md`, and the evaluator documents to identify the remaining gaps in tests, accessibility, security, performance, or failure handling.
Do not expand feature scope.
Patch the issues, rerun the full Stage 6 validation matrix, and update the hardening report with the final evidence.
```

---

## [Stage 7] Release Wrap-Up

- **Why this stage exists**  
  Package the work into something another developer or operator can run, understand, demo, and maintain.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: Medium-High  
- **Suggested tools/skills**: docs, packaging prep, handoff, smoke testing  
- **Worktree recommendation**: main worktree or dedicated release-prep worktree

### Copy-paste prompt

```text
Goal
Complete the release wrap-up for Footage Data Manager: docs, setup, demo flow, smoke scripts, deployment/packaging notes, known issues, and handoff materials.

Context
- The implementation should already be feature-complete and hardened.
- This stage is about making the project reproducible and handoff-ready.
- Do not claim packaging success if SDK/dependency constraints block a real packaged build.

Constraints
- Work in `~/desktop/datamanager`.
- Read:
  - `README.md`
  - `docs/documentation.md`
  - `docs/implement.md`
  - `docs/hardening.md`
  - `docs/qa.md`
- Produce or update:
  - `README.md`
  - setup instructions
  - `.env.example`
  - architecture note
  - demo script
  - sample data/fixture usage guide
  - deployment checklist
  - smoke-test checklist or scripts
  - known-issues doc
  - follow-up backlog
  - handoff notes
- If a packaging/build artifact is feasible, create or validate the packaging script.
- If packaging is blocked, document the exact blocker and the next concrete step.

Deliverables
1. Release-quality `README.md`.
2. `docs/deployment.md` (create if missing).
3. `docs/known-issues.md` (create if missing).
4. `docs/handoff.md` (create if missing).
5. `scripts/demo_run.*` and/or `scripts/smoke_release.*`.
6. Clear setup instructions that work from a fresh environment.

Done when
- Another developer can understand the architecture, boot the app, run validations, and demo the main flows from the docs alone.
- Known blockers are documented honestly.
- Smoke scripts/checklists exist.

Validation
- Run and fix until passing:
  - fresh-environment setup steps from the docs
  - `ruff check .`
  - `ruff format --check .`
  - `mypy app`
  - `pytest -q`
  - `python -m build`
  - Playwright core flows
  - release smoke script/checklist
- If packaging is attempted, validate that the packaging script runs or clearly document why it does not.

Reporting / update files
- Update `docs/implement.md` with the release-wrap summary and final known issues.
- Update `docs/documentation.md` with the final document index and reading order.
```

### Expected artifacts/files
- polished `README.md`
- `docs/deployment.md`
- `docs/known-issues.md`
- `docs/handoff.md`
- smoke/demo scripts
- final doc index

### Validation / Done when
- The repo is reproducible, honest about gaps, and handoff-ready.

### Failure repair prompt

```text
Repair only the release-wrap deficiencies.

Use the release docs and smoke scripts to identify what a new developer or operator still could not do reliably.
Do not add new product features.
Fix the documentation, scripts, or packaging notes, rerun the Stage 7 validations, and update the final handoff materials.
```

---

## [Stage R] Resume / Recovery Prompt

- **Why this stage exists**  
  Long-running Codex work may stop midstream. This prompt safely restarts work from durable repo memory instead of unstable chat memory.

- **Recommended Codex mode**: Agent  
- **Suggested reasoning level**: Medium-High  
- **Suggested tools/skills**: docs, git status, QA triage  
- **Worktree recommendation**: use the worktree for the target stage you are resuming

### Copy-paste prompt

```text
Goal
Resume Footage Data Manager work safely from durable repo memory after an interrupted Codex session.

Context
- The repo root is `~/desktop/datamanager`.
- Durable state must come from repo files, not from assumed chat memory.
- The project uses stage-based execution with strict validation gates.

Constraints
- Work in `~/desktop/datamanager`.
- Read first:
  - `AGENTS.md`
  - `docs/plan.md`
  - `docs/implement.md`
  - `docs/documentation.md`
  - `docs/qa.md`
  - the latest sprint contract/evaluator docs
- Determine:
  - the last completed stage
  - the latest PASS/FAIL status
  - the next blocked item
  - the minimum scope required to continue
- Do not restart from scratch.
- Do not skip failed validations.
- If the repo is mid-failure, continue with the relevant repair prompt rather than starting a later milestone.

Deliverables
1. A concise resume summary in `docs/implement.md`:
   - current stage
   - blocking issues
   - exact next action
2. Code/doc changes only for the correct next milestone or repair.
3. Validation evidence for the resumed stage.

Done when
- The repo has an updated durable status entry.
- Work continues from the correct stage rather than repeating or skipping.
- The relevant validation set has been rerun.

Validation
- Re-run the validation commands for the resumed stage.
- If there is no clear PASS/FAIL evidence, create it before proceeding.

Reporting / update files
- Append the resume summary to `docs/implement.md`.
- Update any relevant evaluator or QA document with the new result.
```

### Expected artifacts/files
- updated `docs/implement.md`
- targeted repair or next-stage changes
- refreshed validation evidence

### Validation / Done when
- The project resumes from durable state without skipping blocked work.

### Failure repair prompt

```text
Resume in repair mode only.

Read `docs/implement.md`, the latest sprint evaluator, and `docs/qa.md`, then continue from the exact failed stage.
Do not advance to a later milestone.
Apply the smallest repair that can make the failed validation pass, rerun that stage’s full validation set, and update the durable docs with the new status.
```

---

## Recommended execution order for Codex

1. Stage 0  
2. Stage 1  
3. Stage 2  
4. Stage 3  
5. Stage 4.1  
6. Stage 4.2  
7. Stage 4.3  
8. Stage 4.4  
9. Stage 4.5  
10. Stage 4.6  
11. Stage 4.7  
12. Stage 5  
13. Stage 6  
14. Stage 7  
15. Stage R only when a session is interrupted

---

## Final note for Codex

- Treat the uploaded spec and repo docs as the source of truth.
- Prefer explicit assumptions over stalled progress.
- Keep diffs small.
- Update durable docs every stage.
- Never mark a milestone complete while its validation or evaluator status is failing.
