"""Report artifact routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.status import HTTP_404_NOT_FOUND

from app.persistence.repositories import ReportRepository

router = APIRouter(prefix="/api/jobs", tags=["reports"])


@router.get("/{job_id}/reports")
def job_reports(request: Request, job_id: str) -> dict[str, list[dict[str, object]]]:
    """Return report artifact metadata."""

    with request.app.state.agent.database.session() as connection:
        reports = ReportRepository(connection).list_for_job(job_id)
    return {"reports": [_report_payload(job_id, report.__dict__) for report in reports]}


@router.get("/{job_id}/reports/{report_id}/download")
def download_report(request: Request, job_id: str, report_id: str) -> FileResponse:
    """Serve a runtime-generated report artifact if it is under the data dir."""

    with request.app.state.agent.database.session() as connection:
        reports = ReportRepository(connection).list_for_job(job_id)
    report = next((item for item in reports if item.report_id == report_id), None)
    if report is None or report.status != "ready":
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="report unavailable")
    root = request.app.state.agent.settings.data_dir.resolve()
    path = (root / report.artifact_relpath).resolve()
    if not _is_relative_to(path, root) or not path.exists():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="report file not found")
    return FileResponse(path)


def _report_payload(job_id: str, report: dict[str, object]) -> dict[str, object]:
    payload = dict(report)
    payload["download_url"] = f"/api/jobs/{job_id}/reports/{report['report_id']}/download"
    return payload


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
