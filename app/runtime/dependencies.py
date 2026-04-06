from __future__ import annotations

from app.parsers.braw_parser import BrawFrameCaptureAdapter, BrawMetadataAdapter


def probe_runtime_dependencies() -> dict[str, object]:
    """Probe the runtime-owned dependency surface honestly."""

    adapter = BrawMetadataAdapter.from_environment()
    capture_adapter = BrawFrameCaptureAdapter.from_environment()
    adapter_status = "ok" if adapter.is_available() else "capability_gated"
    capture_status = "ok" if capture_adapter.is_available() else "capability_gated"

    return {
        "python": {"status": "ok"},
        "braw_metadata_adapter": {
            "status": adapter_status,
            "message": adapter.resolution_reason,
            "command": list(adapter.command) if adapter.command is not None else None,
        },
        "frame_capture": {
            "status": capture_status,
            "message": capture_adapter.resolution_reason,
            "command": list(capture_adapter.command) if capture_adapter.command is not None else None,
        },
        "report_generators": {
            "status": "ok",
            "message": "Stdlib-backed report generators are available",
        },
    }
