# Footage Data Manager

Footage Data Manager is a runtime-first macOS-local service with a browser remote console. The current integrated baseline executes a local-runtime-owned pipeline through scan, prepare, copy, verify, metadata parse, capture, and report generation while the browser remains a thin REST/WebSocket control and monitoring client.

## Current Scope

- Local runtime remains the only execution authority.
- The browser is a remote control and monitoring shell only.
- REST plus WebSocket are the only remote interfaces.
- Job creation, listing, fetching, runtime-driven scan/prepare/copy/verify/parse/capture/reporting, and command persistence are implemented.
- SQLite bootstraps on first start.
- Ordered runtime/job events are emitted over `/ws/events`.
- The browser console surfaces runtime status, detected volumes, queue depth, job progress, warnings/errors, reports, logs, and command results without claiming local execution authority.

## Run Locally

1. Create or activate a Python environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

3. Set runtime environment variables as needed:

```bash
export FDM_HOST=127.0.0.1
export FDM_PORT=4482
export FDM_TOKEN=change-me
export FDM_DATA_DIR="$PWD/.fdm_data"
export FDM_ALLOWED_DEST_ROOTS="$PWD/.fdm_dest"
export FDM_BRAW_METADATA_COMMAND="/absolute/path/to/braw_metadata_adapter"
export FDM_BRAW_FRAME_CAPTURE_COMMAND="/absolute/path/to/braw_frame_capture_adapter"
```

4. Start the app:

```bash
.venv/bin/python -m app.main
```

5. Verify the runtime status endpoint:

```bash
curl -H "Authorization: Bearer $FDM_TOKEN" http://127.0.0.1:4482/api/runtime/status
curl -H "Authorization: Bearer $FDM_TOKEN" http://127.0.0.1:4482/api/settings
```

6. Optionally open the shell UI:

```text
http://127.0.0.1:4482/?token=change-me
```

The browser shell is intentionally remote-only: it submits `remote_web` commands over REST, listens to `/ws/events`, and does not expose local file controls or direct media access.

## Run Verification

The current repository can run its A2 checks with the standard library test runner:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -t .
```

## Adapter Contracts

`FDM_BRAW_METADATA_COMMAND`

- Invocation: `<command> <file_path>`
- Output: stdout must be a single JSON object
- Expected keys when available: `clip_name`, `reel_name`, `camera_id`, `codec`, `resolution_width`, `resolution_height`, `fps`, `duration_frames`, `timecode_start`, `shot_date`, `iso_value`, `white_balance_kelvin`, `lens`

`FDM_BRAW_FRAME_CAPTURE_COMMAND`

- Invocation: `<command> <file_path> <output_dir> <indices_csv>`
- Output: stdout must be a JSON array
- Each item may be either a path string or an object with at least `path`
- The command must write JPEG capture files inside `<output_dir>`
- The runtime requests indices `0,50,100` for first/middle/last frames

## What Is Still Partial

- Adapter-backed deep BRAW metadata is capability-gated when `FDM_BRAW_METADATA_COMMAND` is unset or unavailable
- Real frame capture depends on `FDM_BRAW_FRAME_CAPTURE_COMMAND`; when absent, capture is explicitly downgraded and jobs finish with warnings rather than fake image reports
- Richer retry/rebuild policy is still pending
- Full local operator panel remains out of scope

## Safe Claim Language

- Safe to claim: "The macOS runtime is the only execution authority; the browser is a remote control and monitoring console."
- Safe to claim: "The runtime can scan, copy, verify, parse metadata, and generate reports when the required runtime adapters are available."
- Safe to claim: "Image reports are generated from runtime-captured frames when the BRAW frame-capture adapter is configured."
- Do not claim: "Deep BRAW metadata works without adapter configuration."
- Do not claim: "Frame capture is universally available on any machine without the capture adapter."
- Do not claim: "Restart fully resumes any interrupted active job." The current behavior is durable and explicit, but interrupted active jobs may be requeued or failed depending on stage.

## Real-Media Validation

Run the field checklist in [docs/real-media-validation.md](/Users/server_jay/Desktop/DataManager/docs/real-media-validation.md) before claiming full intended v1 acceptance.

## What Is Still Stubbed

- Rich retry/rebuild policy
- Full local operator panel

The runtime scan, prepare, copy, verify, parse, capture, and report paths are now real when their runtime adapters are configured. The browser console stays honest about the boundary: the runtime performs the work, and the browser only monitors and controls through REST/WebSocket.
