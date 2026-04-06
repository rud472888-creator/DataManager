from __future__ import annotations


def probe_runtime_dependencies() -> dict[str, object]:
    """Dependency shell for A2.

    Actual BRAW and report-tool verification is deferred to later milestones.
    """

    return {
        "python": {"status": "ok"},
        "braw_sdk": {"status": "stubbed", "message": "Not validated in A2"},
        "frame_capture": {"status": "stubbed", "message": "Not validated in A2"},
        "report_generators": {"status": "stubbed", "message": "Not validated in A2"},
    }
