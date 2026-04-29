# Handoff Notes

## Reading Order

1. `README.md`
2. `docs/Footage_DataManager_Spec_v2_2_Local_Runtime_Remote_Console.md`
3. `docs/Footage_DataManager_Codex_Prompt_Pack.md`
4. `docs/implement.md`
5. `docs/qa.md`
6. `docs/known-issues.md`
7. `docs/deployment.md`
8. `docs/release-manifest.md`

## What Works

- Runtime/API/web console shell.
- SQLite migrations and lifecycle persistence.
- State machine, command decisions, recovery candidates.
- Runtime-only synthetic offload/checksum path.
- Parser capability gate with truthful unavailable real BRAW state.
- Mock parser/report generation path.
- API routes for runtime, volumes, jobs, logs, reports, clips, settings, commands.
- Responsive browser console core UX.
- Recovery/reload/local-panel smoke behavior.

## What Not To Claim

- Do not claim real BRAW SDK support.
- Do not claim real frame capture support.
- Do not claim macOS signed packaging.
- Do not expose the service beyond trusted LAN/local use without more security work.

## Final Validation

Run:

```sh
scripts/smoke_release.sh
```
