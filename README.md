# Footage Data Manager

Footage Data Manager is a runtime-first macOS-local service with a browser remote console. The current integrated baseline executes a local-runtime-owned pipeline through scan, prepare, copy, verify, metadata parse, capability-gated capture, and report generation while the browser remains a thin REST/WebSocket control and monitoring client.

## A2 Scope

- Local runtime remains the only execution authority.
- The browser is a remote control and monitoring shell only.
- REST plus WebSocket are the only remote interfaces.
- Job creation, listing, fetching, runtime-driven scan/prepare/copy/verify/parse/reporting, and command persistence are implemented.
- SQLite bootstraps on first start.
- Ordered runtime/job events are emitted over `/ws/events`.
- The browser console now surfaces runtime status, detected volumes, queue depth, job progress, warnings/errors, reports, and command results without claiming local execution authority.

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
```

4. Start the app:

```bash
.venv/bin/python -m app.main
```

5. Verify the runtime status endpoint:

```bash
curl -H "Authorization: Bearer $FDM_TOKEN" http://127.0.0.1:4482/api/runtime/status
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

## What Is Still Stubbed

- adapter-backed deep BRAW metadata is capability-gated when `FDM_BRAW_METADATA_COMMAND` is unset
- BRAW frame capture
- deeper retry/rebuild policy
- full local operator panel

The runtime scan, prepare, copy, verify, parse, and report paths are now real. The browser console stays honest about the boundary: the runtime performs the work, and the browser only monitors and controls through REST/WebSocket.
