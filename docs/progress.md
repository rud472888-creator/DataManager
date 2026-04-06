# Progress

## Acceptance blocker closure

Status: completed

Completed:

- runtime worker loop that promotes exactly one queued job when no active job exists
- local-runtime-only source scan with `job_files` population and default noise exclusion
- destination preparation under runtime-known destination roots only
- real local byte-copy execution for main destination and best-effort backup flow
- progress/event emission during copy/verify/parse/capture/reporting with persistence-backed job and file status
- real cancel handling during runtime execution
- safe file-boundary pause and runtime-backed resume
- recovery baseline for interrupted active jobs and in-progress file rows
- real SHA-256 verification with durable per-file checksum results
- runtime-local metadata parsing and `/api/clips`
- runtime-local frame capture adapter and persisted capture outputs
- runtime-owned report generation and safe `report_id` downloads
- real `/api/jobs/{id}/logs` and `/api/settings`
- explicit adapter contracts and real-media validation checklist
- remote console updates for status, dependency/stub visibility, volume selection, queue/job progress, warnings/errors, report readiness messaging, and command observation
- browser-authority guard coverage to keep the console REST/WebSocket-only and runtime-first
- verified compile, unit/integration/system tests, and live local server/API checks

Still partial:

- adapter-backed deep BRAW metadata without configured adapter
- frame capture when the capture adapter is unavailable
- richer retry/rebuild policy
