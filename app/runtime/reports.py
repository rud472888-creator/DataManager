"""Runtime report artifact generation."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from html import escape as xml_escape
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
    for file in files:
        lines.extend(
            [
                f"File: {file.source_relpath}",
                f"Status: {file.status} | Size: {file.size_bytes} bytes",
                f"Source SHA256: {file.checksum_source or '-'}",
                f"Main SHA256:   {file.checksum_main or '-'}",
                f"Backup SHA256: {file.checksum_backup or '-'}",
                f"Main path: {file.dest_main_relpath or '-'}",
                f"Backup path: {file.dest_backup_relpath or '-'}",
            ]
        )
        if file.error_code or file.error_message:
            lines.append(f"Error: {file.error_code or '-'} {file.error_message or ''}".strip())
        lines.append("")
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
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii")
            + content
            + b"\nendstream"
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
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(bytes(body))


def _paginate_lines(lines: list[str]) -> list[list[str]]:
    lines_per_page = 58
    pages = [
        lines[index : index + lines_per_page]
        for index in range(0, len(lines), lines_per_page)
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
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/docProps/app.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            '<Override PartName="/docProps/core.xml" '
            'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/package/2006/'
            'relationships/metadata/core-properties" '
            'Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/extended-properties" '
            'Target="docProps/app.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "docProps/app.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
            'extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            "<Application>Footage Data Manager</Application></Properties>",
        )
        archive.writestr(
            "docProps/core.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
            'metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            "<dc:creator>Footage Data Manager</dc:creator>"
            "<dc:title>Metadata Report</dc:title>"
            "</cp:coreProperties>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Metadata" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>",
        )


def _xml(value: str) -> str:
    return xml_escape(value, quote=False)
