# Footage Data Manager

Footage Data Manager is a runtime-first macOS-local service with a browser remote console. A2 now adds the first real runtime-owned execution slice: queued jobs can be scanned, prepared, and copied by the local runtime while the browser remains a thin REST/WebSocket control and monitoring client.

## A2 Scope

- Local runtime remains the only execution authority.
- The browser is a remote control and monitoring shell only.
- REST plus WebSocket are the only remote interfaces.
- Job creation, listing, fetching, runtime-driven scan/prepare/copy, and command persistence are implemented.
- SQLite bootstraps on first start.
- Ordered runtime/job events are emitted over `/ws/events`.
- The minimal browser shell can observe runtime status, volumes, jobs, progress, and command actions.

## Run Locally

1. Create or activate a Python environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set runtime environment variables as needed:

```bash
export FDM_HOST=127.0.0.1
export FDM_PORT=4482
export FDM_TOKEN=change-me
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

The browser shell is intentionally minimal and does not expose local file controls.

## Run Verification

The current repository can run its A2 checks with the standard library test runner:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -t .
```

## What Is Still Stubbed

- checksum computation and verification
- BRAW metadata parsing
- BRAW frame capture
- report generation
- deeper retry/rebuild policy
- full local operator panel

The runtime scan, prepare, and copy path is now real. The remaining items stay explicitly stubbed so later milestones can plug into the same runtime-first boundaries without architecture drift.
