# Real-Media Validation Checklist

Run these steps on the target macOS system before claiming the full intended v1 product capability.

## Prerequisites

1. Configure a writable destination root:
   - `FDM_ALLOWED_DEST_ROOTS=/absolute/path/to/destination-root`
2. Configure the optional BRAW metadata adapter if deep metadata is required:
   - `FDM_BRAW_METADATA_COMMAND=/absolute/path/to/braw_metadata_adapter`
3. Configure the BRAW frame capture adapter:
   - `FDM_BRAW_FRAME_CAPTURE_COMMAND=/absolute/path/to/braw_frame_capture_adapter`
4. Confirm runtime dependency status:
   - `GET /api/runtime/status`
   - Expect `braw_metadata_adapter.status = ok` if deep metadata is required
   - Expect `frame_capture.status = ok` if image-report generation is required

## Validation Steps

1. Mount a real BRAW source volume under `/Volumes`.
2. Start the runtime locally.
3. Confirm source and destination discovery:
   - `GET /api/volumes`
4. Create a real job using only runtime-discovered IDs:
   - `POST /api/jobs`
5. Observe the full runtime lifecycle:
   - `QUEUED`
   - `SCANNING`
   - `PREPARING`
   - `COPYING`
   - `VERIFYING`
   - `PARSING`
   - `CAPTURING`
   - `REPORTING`
   - `COMPLETED` or `WARN`
6. During an active copy:
   - issue `cancel`
   - issue `pause`
   - issue `resume`
7. During an active job:
   - close/disconnect the browser client
   - confirm the runtime continues and the job still reaches a terminal state
8. During `COPYING`:
   - restart the runtime process
   - inspect recovery outcome
9. During `VERIFYING`:
   - restart the runtime process
   - inspect recovery outcome

## Evidence to Inspect

1. SQLite tables:
   - `jobs`
   - `job_events`
   - `job_files`
   - `clips`
   - `reports`
2. Artifact routes:
   - `GET /api/jobs/{id}/reports`
   - `GET /api/reports/{report_id}/content`
3. Logs:
   - `GET /api/jobs/{id}/logs`
4. Clips:
   - `GET /api/clips?job_id=<job_id>`

## Acceptance Evidence

1. Main copy exists and is readable.
2. Backup copy exists or an explicit backup warning is persisted.
3. File-level SHA-256 values are stored and consistent.
4. Metadata rows exist in `clips`.
5. Image report contains real captured frames, not placeholder text.
6. `manifest.json` reflects the job, files, and generated artifacts.
7. Browser disconnect does not stop runtime-owned work.
8. Recovery behavior after restart is explicit and matches the documented policy.
