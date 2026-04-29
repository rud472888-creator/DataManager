# API Contract

Working root: `~/desktop/datamanager`.

## Boundary

The API/sync layer exposes the macOS local runtime through REST and WebSocket. It validates remote web console requests, forwards accepted command requests to the runtime, and returns runtime-owned state. It is not a browser filesystem bridge.

The web console may consume only these API responses and WebSocket events. It must never access local files directly, execute parsers, capture frames, compute checksums, run SDKs, or write arbitrary paths.

## REST Routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/runtime/status` | Runtime status, version, dependency/capability status |
| GET | `/api/volumes` | Runtime-discovered source volumes and allowed destination candidates |
| GET | `/api/jobs` | Recent jobs and queue |
| POST | `/api/jobs` | Request creation of a new job from runtime-known source/destination IDs |
| GET | `/api/jobs/{job_id}` | Job detail |
| GET | `/api/jobs/{job_id}/logs` | Job event and error log view |
| GET | `/api/jobs/{job_id}/reports` | Runtime-generated report artifacts |
| POST | `/api/jobs/{job_id}/command` | Request pause, resume, cancel, retry, or refresh |
| GET | `/api/clips` | Legacy parsed clip metadata query; empty for clone-only jobs |
| GET | `/api/settings` | Runtime settings view |
| PATCH | `/api/settings` | Supported settings update, excluding arbitrary path writes |

## Common Error Shape

All JSON errors should use this shape where possible:

```json
{
  "error": {
    "code": "invalid_command",
    "message": "Command resume is not allowed from COPYING.",
    "details": {
      "job_id": "JOB-20260404-001",
      "state": "COPYING"
    }
  }
}
```

Recommended HTTP status mapping:

| Status | Use |
|---|---|
| `400` | malformed request or unsupported enum |
| `401` | missing/invalid token |
| `403` | authenticated but operation is forbidden by policy |
| `404` | runtime-owned resource ID not found |
| `409` | state conflict such as invalid command for current state |
| `422` | shape validation error |
| `503` | runtime dependency unavailable |

## Endpoint Contracts

### `GET /api/runtime/status`

Response: `RuntimeStatus`. It includes runtime online/degraded/offline state, version, platform, active job ID, clone capabilities, supported offload formats/suffixes, and operator messages.

### `GET /api/volumes`

Response:

```json
{
  "sources": [
    {
      "volume_id": "src-A001",
      "label": "A001",
      "kind": "source",
      "status": "available",
      "display_path": "/Volumes/A001",
      "bytes_available": 128000000000
    }
  ],
  "destinations": [
    {
      "volume_id": "dest-main",
      "label": "Main RAID",
      "kind": "destination",
      "status": "available",
      "display_path": "/Volumes/MainRAID",
      "bytes_available": 3000000000000
    }
  ]
}
```

The runtime owns `volume_id` and `display_path`. The browser must submit IDs, not arbitrary paths.

### `POST /api/jobs`

Request:

```json
{
  "project_name": "Spring Shoot",
  "source_volume_id": "src-A001",
  "dest_main_id": "dest-main",
  "dest_backup_id": "dest-backup",
  "policy": {
    "checksum": "xxhash64",
    "exclude_patterns": [".DS_Store", "._*"]
  }
}
```

Response: `201` with `JobDetail` in `QUEUED`, or `409` if single-active-job policy rejects a new active job.

### `GET /api/jobs`

Response: queue and recent job summaries ordered by creation/update time.

### `GET /api/jobs/{job_id}`

Response: `JobDetail` with state, current step, stats, source/destination IDs, timestamps, and latest warning/error summaries.

### `GET /api/jobs/{job_id}/logs`

Response: append-only runtime events. The web console displays logs but does not create them.

### `GET /api/jobs/{job_id}/reports`

Response: report artifact metadata and runtime-served URLs for checksum PDF and manifest JSON when present.

### `POST /api/jobs/{job_id}/command`

Request:

```json
{
  "command": "pause",
  "operator_origin": "remote_web",
  "request_id": "cmd-20260404-001"
}
```

Response:

```json
{
  "job_id": "JOB-20260404-001",
  "command": "pause",
  "accepted": true,
  "state_before": "COPYING",
  "state_after": "PAUSING",
  "reason": "pause requested after current file checkpoint"
}
```

Rejected commands return `409` and must still be persisted as command events when the job exists.

### `GET /api/clips`

Response: legacy parsed clip metadata with filters by job, reel, camera, and parser capability. Clone-only jobs normally return an empty result.

### `GET/PATCH /api/settings`

Settings include token status, allowed destination roots by runtime-managed ID, clone capability status, and UI preferences. PATCH must not allow arbitrary raw path writes from the browser.

## Initial Runtime Status Shape

```json
{
  "runtime": "online",
  "version": "0.1.0",
  "platform": "macOS",
  "active_job_id": null,
  "capabilities": {
    "checksum": "available",
    "supported_offload_formats": ["BRAW", "R3D", "ARRIRAW"],
    "supported_offload_suffixes": [".ari", ".braw", ".mxf", ".r3d"]
  },
  "messages": []
}
```

## Job State Model

Canonical states:

- `QUEUED`
- `SCANNING`
- `PREPARING`
- `COPYING`
- `PAUSING`
- `PAUSED`
- `VERIFYING`
- `REPORTING`
- `WARN`
- `FAILED`
- `CANCELLED`
- `COMPLETED`

Only one active offload job is allowed in v1.

## WebSocket Event Shape

```json
{
  "type": "job_progress",
  "job_id": "JOB-20260404-001",
  "state": "COPYING",
  "current_file": "A001_C003.braw",
  "processed_files": 27,
  "total_files": 103,
  "bytes_done": 64892518400,
  "bytes_total": 109434593280,
  "speed_mbps": 846.4,
  "eta_sec": 133,
  "warnings": 1,
  "errors": 0,
  "message": "main copy ok, backup copying",
  "timestamp": "2026-04-04T13:32:12Z"
}
```

Event types:

| Type | Payload |
|---|---|
| `runtime_status` | runtime status snapshot |
| `job_created` | job summary |
| `job_progress` | state, step, current file, counters, bytes, speed, ETA |
| `job_event` | append-only event/log entry |
| `command_result` | accepted/rejected command decision |
| `report_ready` | report artifact metadata |
| `volume_changed` | runtime-discovered source/destination update |

Each event includes `timestamp`, `event_id`, and enough IDs for the browser to refresh via REST after reconnect.

## Command Rules

The remote web console sends command requests; the runtime decides state transitions.

| Command | Allowed examples | Runtime response |
|---|---|---|
| `pause` | `COPYING` | accepted, rejected, or failed with reason |
| `resume` | `PAUSED` | accepted, rejected, or failed with reason |
| `cancel` | queued or active non-terminal states | accepted, rejected, or failed with reason |
| `retry` | `WARN`, `FAILED` | accepted, rejected, or failed with reason |
| `refresh` | any non-terminal or terminal state | accepted or rejected with reason |

Every command decision must be persisted as an event with actor/channel, timestamp, command, accepted/rejected status, and reason.

## Command Matrix

| State | pause | resume | cancel | retry | refresh |
|---|---|---|---|---|---|
| `QUEUED` | reject | reject | accept | reject | accept |
| `SCANNING` | reject | reject | accept | reject | accept |
| `PREPARING` | reject | reject | accept | reject | accept |
| `COPYING` | accept | reject | accept | reject | accept |
| `PAUSING` | reject | reject | reject | reject | accept |
| `PAUSED` | reject | accept | accept | reject | accept |
| `VERIFYING` | reject | reject | accept | reject | accept |
| `REPORTING` | reject | reject | accept | reject | accept |
| `WARN` | reject | reject | reject | accept | accept |
| `FAILED` | reject | reject | reject | accept | accept |
| `CANCELLED` | reject | reject | reject | reject | accept |
| `COMPLETED` | reject | reject | reject | reject | accept |

Implementation tests must cover both accepted and rejected paths.

## Auth Assumption

v1 may use simple token-based auth for trusted local/LAN deployment. Invalid or missing tokens must be rejected by write routes and command routes. Later hardening must document any stronger network exposure model before enabling it.

Read-only status endpoints may be allowed in local development, but Stage 4.5 must decide and test the final v1 token behavior. Write routes and command routes require token validation.
