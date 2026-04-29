# Sprint 5 - Remote Web Console Core UX Contract

Working root: `~/desktop/datamanager`.

## Goal

Implement the browser console as a REST/WebSocket command and monitoring surface for the macOS local runtime.

## Scope

- Home runtime overview.
- New Job flow using runtime-provided source/destination IDs.
- Job Detail/active job state.
- Queue list and command buttons.
- Report Center.
- Settings token/operator controls.
- Loading, empty, error, success states.
- Desktop and mobile Playwright flows.

## Out Of Scope

- Browser local file access.
- OS file pickers or arbitrary path inputs.
- Full visual polish beyond clear black/white operational UX.
- Complex auth UX.

## Screen Responsibilities

- Home: runtime status, local executor reminder, primary CTA.
- New Job: project name, source, main destination, backup destination, create request.
- Job Detail: selected/active job state, command actions, warnings/errors placeholder.
- Queue: all jobs and selected state.
- Report Center: report artifact records and download links.
- Settings: bearer token and operator label for API requests.

## Primary CTA Hierarchy

First viewport primary CTA is `New offload job`. Mobile keeps it in a fixed action area. Job commands are secondary and only operate through API command requests.

## Mobile/Desktop Behavior

Desktop uses a two-column operational layout below the hero. Mobile stacks sections and keeps the primary action fixed at the bottom.

## Accessibility

Use semantic sections, labels, buttons, status regions, visible focus, and text state indicators. Color is not the only state cue.

## Runtime Executor Messaging

The UI must repeatedly state that the local runtime performs real file work and the browser sends requests/observes state only.

## Playwright Flows

- Desktop: load home, open new job, create runtime-backed job, see queue/detail.
- Mobile: load home at narrow viewport, fixed CTA visible, no horizontal overflow.
- Boundary: assert there is no `input[type=file]`.

## Validation Commands

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest -q
.venv/bin/python -m build
```

## Implementation Notes

Implemented static remote console core UX:

- Home/runtime overview with first-viewport CTA.
- New Job form using runtime-provided source/destination options only.
- Job Detail with selected job, state, and command request buttons.
- Queue list with selected background state.
- Report Center list/download links.
- Settings token/operator controls with token kept in browser session.
- REST integration for runtime, volumes, jobs, commands, reports, settings.
- WebSocket runtime status integration.
- Mobile layout with fixed `New offload job` action.

Boundary behavior:

- No `input[type=file]`.
- No arbitrary source/destination path entry.
- UI repeatedly states that local runtime performs file work and browser only sends requests/observes state.

Validation run:

- `.venv/bin/ruff check .` PASS
- `.venv/bin/ruff format --check .` PASS
- `.venv/bin/mypy app` PASS
- `.venv/bin/pytest -q` PASS, 42 tests including desktop/mobile Playwright flows
- `.venv/bin/python -m build` PASS

Deferred polish:

- Rich progress/speed/ETA visualization waits for deeper live event payloads.
- Visual refinement and accessibility pass continue in Stage 5/6.
