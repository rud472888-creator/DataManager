# Deployment Notes

Working root: `~/desktop/datamanager`.

## Local Runtime Deployment

1. Create a Python virtual environment.
2. Install the package with dev/runtime dependencies.
3. Configure `.env` values or environment variables:
   - `FDM_HOST`
   - `FDM_PORT`
   - `FDM_TOKEN`
   - `FDM_DATA_DIR`
   - `FDM_DATABASE_PATH`
   - `FDM_DEV_SOURCE_ROOT` for local fixture/dev runs
   - `FDM_ALLOWED_DEST_ROOTS`
   - `FDM_BRAW_METADATA_COMMAND` when a real adapter exists
4. Apply migrations.
5. Start Uvicorn on the field Mac.
6. Open the remote console from a trusted browser/LAN client.

## Packaging Status

Python package build is validated with `python -m build`.

macOS app bundle/signing is not complete. Blockers:

- Signing identity/certificate not provided.
- Real BRAW SDK/binary packaging requirements unknown.
- Real sample media validation not available.

Next concrete packaging step: choose a macOS packaging tool and verify how the BRAW adapter command/SDK may be distributed under its license.

## Security Posture

The v1 token model is suitable for trusted local/LAN use only. Do not expose this service to the public internet without stronger auth, TLS, and network policy.
