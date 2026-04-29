# Known Issues And Follow-up Backlog

## External Blockers

- Real BRAW SDK command is not configured.
- Real `.braw` sample media is not available.
- Real R3D and ARRIRAW SDK/CLI adapters are not configured.
- Real frame capture remains unavailable.
- macOS app signing/notarization credentials are not available.

## Product Gaps

- WebSocket event fanout is basic; richer live progress payloads should be added.
- Active interrupted copy repair is conservative and not a full resume engine.
- UI report center is sparse until real report artifacts exist.
- Local panel is a minimal status renderer, not packaged native UI.

## Follow-up Backlog

- Validate real BRAW metadata extraction with `FDM_BRAW_METADATA_COMMAND`.
- Add and validate real R3D/ARRIRAW metadata extraction adapters.
- Add real frame capture adapter if SDK/licensing allows.
- Add richer progress/speed/ETA WebSocket event stream.
- Package as a signed macOS app or documented launch agent.
- Add optional TLS/reverse-proxy guidance for LAN deployments.
