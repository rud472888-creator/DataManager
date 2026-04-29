# Footage Data Manager Prompt Baseline

Working root: `~/desktop/datamanager`.

## Product Summary

Footage Data Manager is a macOS local runtime plus remote web console for field media cloning. The local runtime detects media volumes, scans camera footage, copies to main and backup destinations, verifies checksums, generates clone reports, persists state to SQLite, and emits logs/events. The web console creates jobs, monitors progress, shows logs/reports, and sends remote commands through REST and WebSocket only.

## Non-Negotiable Boundary

The macOS local runtime is the only executor of real file operations. The remote web console is command and observation UI only. The web console must never directly access local files, open OS file pickers for source/destination selection, copy files, calculate checksums, execute parsers, capture frames, run BRAW SDK/ffmpeg, write arbitrary paths, or mutate SQLite directly.

## Users

- Local operator, DIT, or data wrangler running the macOS runtime on the field machine.
- Remote supervisor, producer, or assistant monitoring and sending commands from a browser.
- Optional local operator panel user who needs a minimal emergency/status view on the runtime machine.

## Core Flows

1. Field start: card inserted, local runtime detects volume, console loads runtime-provided source and destination candidates, operator creates a job.
2. Clone: runtime scans, prepares folders, copies to main and backup, verifies checksums, and writes clone reports.
3. Remote monitoring: browser shows state, current file, speed, ETA, warnings, errors, logs, and reports from API/WebSocket data.
4. Remote command: browser sends pause, resume, cancel, or retry; API validates; runtime accepts or rejects; the result is persisted and streamed.
5. Recovery: browser reconnect does not stop work; app restart can recover queued, paused, warning, and failed jobs.

## Required v1 Features

- macOS local runtime/agent as sole executor
- BRAW-focused ingest
- Volume detection and allowed destination discovery
- Single active offload queue
- Job state machine
- Main and backup destination copy
- Checksum verification
- Clone manifest and checksum report generation
- Checksum PDF and `manifest.json`
- SQLite persistence and append-only events/logs
- REST API and WebSocket event stream
- Remote web console for home, new job, job detail, queue, reports, and settings
- Responsive browser support for mobile and iPad
- Runtime/browser disconnect tolerance
- Restart recovery for recoverable jobs

## Non-Goals

- Native iOS app
- Web console direct file-system access
- Browser source/destination picker for local paths
- Multiple active offload jobs
- Multi-format ingest beyond BRAW for v1
- Resolve project generation, Telegram, Notion, proxy generation, or similar integrations
- Complex enterprise RBAC

## Assumptions

- Python-first stack is preferred for v1.
- FastAPI serves REST, WebSocket, and the static web console unless a later stage documents a stronger reason.
- SQLite is the persistence layer.
- v1 auth can be simple token auth for trusted local/LAN use.
- Frame capture and deeper image-processing SDK integrations are handled by a separate program, not this clone app.
