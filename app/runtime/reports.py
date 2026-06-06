"""Runtime report artifact generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.persistence.db import Database
from app.persistence.models import JobFile, Report
from app.persistence.repositories import (
    JobFileRepository,
    ReportRepository,
    deterministic_id,
)
from app.runtime.checksum import sha256_file


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
            reports = [
                _write_checksum_pdf(job_id, report_root, files),
                _write_manifest(job_id, manifest_root, files),
            ]
            repo = ReportRepository(connection)
            return ReportResult(reports=[repo.upsert(report) for report in reports])


def _write_checksum_pdf(job_id: str, report_root: Path, files: list[JobFile]) -> Report:
    path = report_root / "checksum.pdf"
    lines = ["Footage Data Manager Checksum Report", f"Job: {job_id}", ""]
    for file in files:
        lines.extend(
            [
                f"File: {file.source_relpath}",
                f"Source path: {file.source_path_id}",
                f"Status: {file.status} | Size: {file.size_bytes} bytes",
                f"Source SHA256: {file.checksum_source or '-'}",
            ]
        )
        for replica in file.replica_results:
            lines.extend(
                [
                    f"Replica {replica.path_id} SHA256: {replica.checksum or '-'}",
                    f"Replica {replica.path_id} path: {replica.dest_relpath or '-'}",
                    f"Replica {replica.path_id} status: {replica.status}",
                ]
            )
        if file.error_code or file.error_message:
            lines.append(f"Error: {file.error_code or '-'} {file.error_message or ''}".strip())
        lines.append("")
    _write_simple_pdf(path, lines)
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


def _write_simple_pdf(path: Path, lines: list[str]) -> None:
    pages = _paginate_lines(lines)
    font_id = 3 + len(pages) * 2
    page_ids = [3 + index * 2 for index in range(len(pages))]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] "
            f"/Count {len(page_ids)} >>"
        ).encode("ascii"),
        font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    for index, page_lines in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        content = _pdf_page_content(page_lines)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = (
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream"
        )

    body = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id in sorted(objects):
        offsets.append(len(body))
        body.extend(f"{object_id} 0 obj\n".encode("ascii"))
        body.extend(objects[object_id])
        body.extend(b"\nendobj\n")

    xref_offset = len(body)
    body.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    body.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(bytes(body))


def _paginate_lines(lines: list[str]) -> list[list[str]]:
    lines_per_page = 58
    pages = [
        lines[index : index + lines_per_page] for index in range(0, len(lines), lines_per_page)
    ]
    return pages or [[]]


def _pdf_page_content(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 9 Tf", "12 TL", "40 760 Td"]
    for line in lines:
        commands.append(f"({_pdf_literal(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1")


def _pdf_literal(value: str) -> str:
    encoded = value.encode("latin-1", errors="replace").decode("latin-1")
    return encoded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
