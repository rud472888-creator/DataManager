"""Runtime report artifact generation."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.persistence.db import Database
from app.persistence.models import Clip, JobFile, Report
from app.persistence.repositories import (
    ClipRepository,
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
        frames_available: bool,
    ) -> ReportResult:
        report_root = project_root / "00_master" / "reports"
        manifest_root = project_root / "00_master" / "manifests"
        report_root.mkdir(parents=True, exist_ok=True)
        manifest_root.mkdir(parents=True, exist_ok=True)
        with self.database.session() as connection:
            files = JobFileRepository(connection).list_for_job(job_id)
            clips = ClipRepository(connection).list_for_job(job_id)
            reports = [
                _write_checksum_pdf(job_id, report_root, files),
                _write_metadata_xlsx(job_id, report_root, clips),
                _write_manifest(job_id, manifest_root, files, clips),
            ]
            if frames_available:
                reports.append(_write_image_pdf(job_id, report_root))
            else:
                reports.append(
                    Report(
                        report_id=deterministic_id("report", job_id, "image_pdf"),
                        job_id=job_id,
                        report_type="image_pdf",
                        artifact_relpath="00_master/reports/image.pdf",
                        status="unavailable",
                        error_message="frame capture unavailable; no fake image report generated",
                    )
                )
            repo = ReportRepository(connection)
            return ReportResult(reports=[repo.upsert(report) for report in reports])


def _write_checksum_pdf(job_id: str, report_root: Path, files: list[JobFile]) -> Report:
    path = report_root / "checksum.pdf"
    lines = ["Footage Data Manager Checksum Report", f"Job: {job_id}", ""]
    lines.extend(
        f"{file.source_relpath} | {file.status} | {file.checksum_source or ''}" for file in files
    )
    _write_simple_pdf(path, lines)
    return _ready_report(job_id, "checksum_pdf", "00_master/reports/checksum.pdf", path)


def _write_image_pdf(job_id: str, report_root: Path) -> Report:
    path = report_root / "image.pdf"
    _write_simple_pdf(path, ["Footage Data Manager Image Report", f"Job: {job_id}"])
    return _ready_report(job_id, "image_pdf", "00_master/reports/image.pdf", path)


def _write_metadata_xlsx(job_id: str, report_root: Path, clips: list[Clip]) -> Report:
    path = report_root / "metadata.xlsx"
    rows = [["clip_id", "format_name", "parser_version", "metadata_json"]]
    rows.extend(
        [clip.clip_id, clip.format_name, clip.parser_version, clip.metadata_json] for clip in clips
    )
    _write_minimal_xlsx(path, rows)
    return _ready_report(job_id, "metadata_xlsx", "00_master/reports/metadata.xlsx", path)


def _write_manifest(
    job_id: str,
    manifest_root: Path,
    files: list[JobFile],
    clips: list[Clip],
) -> Report:
    path = manifest_root / "manifest.json"
    payload = {
        "job_id": job_id,
        "files": [file.__dict__ for file in files],
        "clips": [clip.__dict__ for clip in clips],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return _ready_report(job_id, "manifest_json", "00_master/manifests/manifest.json", path)


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
    text = "\\n".join(lines).replace("(", "[").replace(")", "]")
    path.write_bytes(
        (
            "%PDF-1.4\n"
            "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            "3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj\n"
            f"4 0 obj << /Length {len(text) + 32} >> stream\n"
            f"BT /F1 12 Tf 40 760 Td ({text}) Tj ET\n"
            "endstream endobj\n%%EOF\n"
        ).encode()
    )


def _write_minimal_xlsx(path: Path, rows: list[list[str]]) -> None:
    sheet_rows = []
    for index, row in enumerate(rows, start=1):
        cells = "".join(
            f'<c r="{chr(65 + col)}{index}" t="inlineStr"><is><t>{_xml(value)}</t></is></c>'
            for col, value in enumerate(row)
        )
        sheet_rows.append(f'<row r="{index}">{cells}</row>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="Metadata" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>",
        )


def _xml(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
