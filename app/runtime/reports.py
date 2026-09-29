"""Runtime report artifact generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.persistence.db import Database
from app.persistence.models import JobFile, Report
from app.persistence.repositories import (
    JobFileRepository,
    JobRepository,
    ReportRepository,
    deterministic_id,
)
from app.runtime.checksum import sha256_file
from app.runtime.checksum_pdf import write_checksum_pdf


@dataclass(frozen=True)
class ReportResult:
    reports: list[Report]


class ReportService:
    """Generate simple operational artifacts from persisted runtime data."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def generate(
        self,
        *,
        job_id: str,
        project_root: Path,
    ) -> ReportResult:
        report_root = project_root / "00_Master" / "reports"
        manifest_root = project_root / "00_Master" / "manifests"
        report_root.mkdir(parents=True, exist_ok=True)
        manifest_root.mkdir(parents=True, exist_ok=True)
        with self.database.session() as connection:
            files = JobFileRepository(connection).list_for_job(job_id)
            job = JobRepository(connection).get(job_id)
            reports = [
                _write_checksum_pdf(
                    job_id,
                    report_root,
                    files,
                    project_name=job.project_name if job else project_root.name,
                    expected_replica_ids=job.replica_path_ids if job else (),
                ),
                _write_manifest(job_id, manifest_root, files),
            ]
            repo = ReportRepository(connection)
            return ReportResult(reports=[repo.upsert(report) for report in reports])


def _write_checksum_pdf(
    job_id: str,
    report_root: Path,
    files: list[JobFile],
    *,
    project_name: str = "Data Handler",
    expected_replica_ids: tuple[str, ...] = (),
) -> Report:
    path = report_root / "checksum.pdf"
    write_checksum_pdf(
        path,
        job_id=job_id,
        project_name=project_name,
        files=files,
        expected_replica_ids=expected_replica_ids,
    )
    return _ready_report(job_id, "checksum_pdf", "00_Master/reports/checksum.pdf", path)


def _write_manifest(
    job_id: str,
    manifest_root: Path,
    files: list[JobFile],
) -> Report:
    path = manifest_root / "manifest.json"
    payload = {
        "job_id": job_id,
        "files": [_file_payload(file) for file in files],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return _ready_report(job_id, "manifest_json", "00_Master/manifests/manifest.json", path)


def _file_payload(file: JobFile) -> dict[str, object]:
    return {
        "file_id": file.file_id,
        "job_id": file.job_id,
        "source_path_id": file.source_path_id,
        "source_relpath": file.source_relpath,
        "size_bytes": file.size_bytes,
        "checksum_source": file.checksum_source,
        "status": file.status,
        "error_code": file.error_code,
        "error_message": file.error_message,
        "replica_results": [replica.__dict__ for replica in file.replica_results],
    }


def _ready_report(job_id: str, report_type: str, relpath: str, path: Path) -> Report:
    return Report(
        report_id=deterministic_id("report", job_id, report_type),
        job_id=job_id,
        report_type=report_type,
        artifact_relpath=relpath,
        status="ready",
        checksum=sha256_file(path),
    )
