# Known Issues And Follow-up Backlog

## External Blockers

- Real `.braw` sample media is not available.
- macOS app signing/notarization credentials are not available.

## Product Gaps

- WebSocket event fanout is basic; richer live progress payloads should be added.
- Active interrupted copy repair is conservative and not a full resume engine.
- UI report center is intentionally limited to clone/checksum artifacts.
- Local panel is a minimal status renderer, not packaged native UI.

## Follow-up Backlog

- Add richer progress/speed/ETA WebSocket event stream.
- Package as a signed macOS app or documented launch agent.
- Add optional TLS/reverse-proxy guidance for LAN deployments.
