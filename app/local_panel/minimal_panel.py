"""Minimal local operator panel.

This panel is deliberately a read-oriented status surface. It does not execute
file work directly and does not duplicate the remote web console.
"""

from __future__ import annotations

from app.runtime.agent import RuntimeAgent


def describe_panel_scope() -> str:
    """Describe the local panel without creating a second executor."""

    return "Minimal local status panel; real file work remains in the local runtime."


def render_panel(agent: RuntimeAgent) -> str:
    """Render a tiny HTML status panel for the local operator."""

    status = agent.status_payload()
    active = status["active_job_id"] or "none"
    return (
        "<!doctype html><html><body>"
        "<main>"
        "<h1>Footage Data Manager Local Panel</h1>"
        f"<p>{describe_panel_scope()}</p>"
        f"<p>Runtime: {status['runtime']}</p>"
        f"<p>Active job: {active}</p>"
        "<p>Logs and results are available through the local runtime API.</p>"
        "<p>Emergency controls must use the command API; this panel is not a file executor.</p>"
        "</main>"
        "</body></html>"
    )
