from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from app.config import Settings
from app.persistence.manifests import write_manifest
from app.persistence.models import JobFileRecord, JobRecord
from app.persistence.repositories import PersistenceBundle
from app.runtime.events import utc_now_iso


REPORT_MIME_TYPES = {
    "checksum_pdf": "application/pdf",
    "image_pdf": "application/pdf",
    "metadata_xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "manifest_json": "application/json",
}

REPORT_FILENAMES = {
    "checksum_pdf": "checksum.pdf",
    "image_pdf": "image.pdf",
    "metadata_xlsx": "metadata.xlsx",
    "manifest_json": "manifest.json",
}


@dataclass(frozen=True, slots=True)
class ReportArtifact:
    report_id: str
    job_id: str
    report_type: str
    status: str
    relative_path: str
    size_bytes: int
    created_at: str


@dataclass(frozen=True, slots=True)
class ArtifactRoots:
    base_root: Path
    reports_root: Path
    manifests_root: Path


def ensure_reports_for_job(*, job_id: str, settings: Settings, persistence: PersistenceBundle) -> list[dict[str, Any]]:
    job = persistence.jobs.get_job(job_id)
    if job is None:
        raise KeyError(job_id)

    job_files = persistence.job_files.list_for_job(job_id)
    roots = _resolve_artifact_roots(job=job, settings=settings)
    created_at = utc_now_iso()

    manifest_path = roots.manifests_root / REPORT_FILENAMES["manifest_json"]
    checksum_pdf_path = roots.reports_root / REPORT_FILENAMES["checksum_pdf"]
    metadata_xlsx_path = roots.reports_root / REPORT_FILENAMES["metadata_xlsx"]
    image_pdf_path = roots.reports_root / REPORT_FILENAMES["image_pdf"]

    checksum_lines = _build_checksum_lines(job=job, job_files=job_files)
    metadata_rows = _build_metadata_rows(job_files)
    captured_frames = _collect_captured_frames(job_files)

    _write_text_pdf(checksum_pdf_path, title="Checksum Verification Report", lines=checksum_lines)
    _write_metadata_xlsx(metadata_xlsx_path, metadata_rows)

    artifacts = [
        _artifact_for_path(
            job_id=job_id,
            report_type="checksum_pdf",
            path=checksum_pdf_path,
            base_root=roots.base_root,
            created_at=created_at,
        ),
        _artifact_for_path(
            job_id=job_id,
            report_type="metadata_xlsx",
            path=metadata_xlsx_path,
            base_root=roots.base_root,
            created_at=created_at,
        ),
    ]
    if captured_frames:
        _write_image_pdf(image_pdf_path, frames=captured_frames)
        artifacts.append(
            _artifact_for_path(
                job_id=job_id,
                report_type="image_pdf",
                path=image_pdf_path,
                base_root=roots.base_root,
                created_at=created_at,
            )
        )

    manifest_preview = ReportArtifact(
        report_id=f"{job_id}:manifest_json",
        job_id=job_id,
        report_type="manifest_json",
        status="ready",
        relative_path=str(manifest_path.resolve().relative_to(roots.base_root.resolve())),
        size_bytes=0,
        created_at=created_at,
    )
    write_manifest(
        manifest_path,
        _build_manifest_payload(
            job=job,
            job_files=job_files,
            artifacts=[*artifacts, manifest_preview],
        ),
    )
    manifest_artifact = _artifact_for_path(
        job_id=job_id,
        report_type="manifest_json",
        path=manifest_path,
        base_root=roots.base_root,
        created_at=created_at,
    )
    artifacts.append(manifest_artifact)
    write_manifest(
        manifest_path,
        _build_manifest_payload(
            job=job,
            job_files=job_files,
            artifacts=artifacts,
        ),
    )

    _replace_reports_index(job_id=job_id, artifacts=artifacts, persistence=persistence)
    persistence.events.append_event(
        job_id=job_id,
        event_type="job.report_ready",
        level="INFO",
        origin="runtime.reports",
        message=f"Generated {len(artifacts)} report artifacts",
        payload={"report_types": [artifact.report_type for artifact in artifacts]},
    )
    return [_serialize_artifact(artifact) for artifact in artifacts]


def resolve_report_content(
    *,
    report_id: str,
    settings: Settings,
    persistence: PersistenceBundle,
) -> tuple[dict[str, Any], Path, str]:
    row = _fetch_report_row(report_id=report_id, persistence=persistence)
    if row is None:
        raise KeyError(report_id)
    job = persistence.jobs.get_job(row["job_id"])
    if job is None:
        raise KeyError(row["job_id"])
    roots = _resolve_artifact_roots(job=job, settings=settings)
    relative_path = Path(row["relative_path"])
    resolved = (roots.base_root / relative_path).resolve()
    if not _is_relative_to(resolved, roots.base_root.resolve()) or not resolved.is_file():
        raise FileNotFoundError(row["relative_path"])
    mime_type = REPORT_MIME_TYPES.get(row["report_type"], "application/octet-stream")
    return dict(row), resolved, mime_type


def _resolve_artifact_roots(*, job: JobRecord, settings: Settings) -> ArtifactRoots:
    stats = job.stats()
    main_paths = stats.get("main_paths")
    if isinstance(main_paths, dict):
        base_root = Path(str(main_paths["project_root"])).resolve()
        reports_root = Path(str(main_paths["reports_root"])).resolve()
        manifests_root = Path(str(main_paths["manifests_root"])).resolve()
    else:
        base_root = (settings.reports_dir / job.job_id).resolve()
        reports_root = (base_root / "reports").resolve()
        manifests_root = (base_root / "manifests").resolve()
    reports_root.mkdir(parents=True, exist_ok=True)
    manifests_root.mkdir(parents=True, exist_ok=True)
    return ArtifactRoots(base_root=base_root, reports_root=reports_root, manifests_root=manifests_root)


def _artifact_for_path(
    *,
    job_id: str,
    report_type: str,
    path: Path,
    base_root: Path,
    created_at: str,
) -> ReportArtifact:
    return ReportArtifact(
        report_id=f"{job_id}:{report_type}",
        job_id=job_id,
        report_type=report_type,
        status="ready",
        relative_path=str(path.resolve().relative_to(base_root.resolve())),
        size_bytes=path.stat().st_size,
        created_at=created_at,
    )


def _serialize_artifact(artifact: ReportArtifact) -> dict[str, Any]:
    payload = {
        "report_id": artifact.report_id,
        "job_id": artifact.job_id,
        "report_type": artifact.report_type,
        "status": artifact.status,
        "relative_path": artifact.relative_path,
        "size_bytes": artifact.size_bytes,
        "created_at": artifact.created_at,
        "download_url": f"/api/reports/{artifact.report_id}/content",
    }
    payload["file_name"] = Path(artifact.relative_path).name
    return payload


def _replace_reports_index(
    *,
    job_id: str,
    artifacts: list[ReportArtifact],
    persistence: PersistenceBundle,
) -> None:
    with persistence.database.connect() as connection:
        connection.execute("DELETE FROM reports WHERE job_id = ?", (job_id,))
        connection.executemany(
            """
            INSERT INTO reports (
                report_id, job_id, report_type, status, relative_path, size_bytes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    artifact.report_id,
                    artifact.job_id,
                    artifact.report_type,
                    artifact.status,
                    artifact.relative_path,
                    artifact.size_bytes,
                    artifact.created_at,
                )
                for artifact in artifacts
            ],
        )
        connection.commit()


def _fetch_report_row(*, report_id: str, persistence: PersistenceBundle) -> Any:
    with persistence.database.connect() as connection:
        return connection.execute(
            "SELECT * FROM reports WHERE report_id = ?",
            (report_id,),
        ).fetchone()


def _build_manifest_payload(
    *,
    job: JobRecord,
    job_files: list[JobFileRecord],
    artifacts: list[ReportArtifact],
) -> dict[str, Any]:
    stats = job.stats()
    return {
        "generated_at": utc_now_iso(),
        "job": {
            "job_id": job.job_id,
            "project_name": job.project_name,
            "state": job.state,
            "current_step": job.current_step,
            "warning_count": job.warning_count,
            "error_count": job.error_count,
            "source_volume_id": job.source_volume_id,
            "dest_main_id": job.dest_main_id,
            "dest_backup_id": job.dest_backup_id,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "ended_at": job.ended_at,
        },
        "stats": stats,
        "reports": [_serialize_artifact(artifact) for artifact in artifacts],
        "files": [
            {
                "relative_path": file_record.relative_path,
                "size_bytes": file_record.size_bytes,
                "parser_name": file_record.parser_name,
                "states": {
                    "copy_main": file_record.copy_main_state,
                    "copy_backup": file_record.copy_backup_state,
                    "verify_main": file_record.verify_main_state,
                    "verify_backup": file_record.verify_backup_state,
                    "parse": file_record.parse_state,
                    "capture": file_record.capture_state,
                },
                "checksums": {
                    "source_sha256": file_record.source_checksum_sha256,
                    "main_sha256": file_record.main_checksum_sha256,
                    "backup_sha256": file_record.backup_checksum_sha256,
                },
                "warning_code": file_record.warning_code,
                "error_code": file_record.error_code,
                "metadata": _parse_metadata_json(file_record.metadata_json),
            }
            for file_record in job_files
        ],
    }


def _build_checksum_lines(*, job: JobRecord, job_files: list[JobFileRecord]) -> list[str]:
    lines = [
        f"Job: {job.job_id}",
        f"Project: {job.project_name}",
        f"State at generation: {job.state}",
        "",
    ]
    if not job_files:
        return lines + ["No scanned files are available yet."]

    checksum_present = any(
        record.source_checksum_sha256 or record.main_checksum_sha256 or record.backup_checksum_sha256
        for record in job_files
    )
    if not checksum_present:
        lines.extend(
            [
                "Checksum digests are not persisted for this job yet.",
                "This report is still generated so downstream tooling can see the current verification gap.",
                "",
            ]
        )

    for record in job_files:
        lines.extend(
            [
                record.relative_path,
                f"  size_bytes={record.size_bytes}",
                f"  copy_main={record.copy_main_state} copy_backup={record.copy_backup_state}",
                f"  verify_main={record.verify_main_state} verify_backup={record.verify_backup_state}",
                f"  source_sha256={record.source_checksum_sha256 or 'unavailable'}",
                f"  main_sha256={record.main_checksum_sha256 or 'unavailable'}",
                f"  backup_sha256={record.backup_checksum_sha256 or 'unavailable'}",
                "",
            ]
        )
    return lines


def _collect_captured_frames(job_files: list[JobFileRecord]) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for record in job_files:
        metadata = _parse_metadata_json(record.metadata_json)
        capture = metadata.get("capture")
        if not isinstance(capture, dict):
            continue
        capture_frames = capture.get("frames")
        if not isinstance(capture_frames, list):
            continue
        for item in capture_frames:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if not isinstance(path, str):
                continue
            frames.append(
                {
                    "path": Path(path),
                    "label": str(item.get("label") or item.get("index") or record.relative_path),
                    "relative_path": record.relative_path,
                }
            )
    return frames


def _build_metadata_rows(job_files: list[JobFileRecord]) -> list[list[object]]:
    metadata_keys: set[str] = set()
    flattened_rows: list[dict[str, Any]] = []
    for record in job_files:
        metadata = _parse_metadata_json(record.metadata_json)
        flat = {key: _stringify_cell_value(value) for key, value in metadata.items()}
        metadata_keys.update(flat)
        flattened_rows.append(flat)

    ordered_keys = sorted(metadata_keys)
    header: list[object] = [
        "relative_path",
        "size_bytes",
        "parser_name",
        "copy_main_state",
        "copy_backup_state",
        "verify_main_state",
        "verify_backup_state",
        "parse_state",
        "capture_state",
        *ordered_keys,
        "raw_metadata_json",
    ]
    rows: list[list[object]] = [header]
    for record, flat in zip(job_files, flattened_rows, strict=False):
        rows.append(
            [
                record.relative_path,
                record.size_bytes,
                record.parser_name or "",
                record.copy_main_state,
                record.copy_backup_state,
                record.verify_main_state,
                record.verify_backup_state,
                record.parse_state,
                record.capture_state,
                *[flat.get(key, "") for key in ordered_keys],
                json.dumps(_parse_metadata_json(record.metadata_json), sort_keys=True),
            ]
        )
    if len(rows) == 1:
        rows.append(["No files", 0, "", "", "", "", "", "", "", "{}"])
    return rows


def _write_metadata_xlsx(path: Path, rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    worksheet_rows: list[str] = []
    for row_index, values in enumerate(rows, start=1):
        cells: list[str] = []
        for column_index, value in enumerate(values, start=1):
            ref = f"{_excel_column_name(column_index)}{row_index}"
            cells.append(_xlsx_cell(ref, value))
        worksheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(worksheet_rows)}</sheetData>"
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Metadata" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        "</Relationships>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="1"><xf xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        archive.writestr("xl/styles.xml", styles_xml)


def _xlsx_cell(ref: str, value: object) -> str:
    if value is None:
        return f'<c r="{ref}"/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'


def _excel_column_name(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _write_text_pdf(path: Path, *, title: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wrapped_lines: list[str] = []
    for raw_line in [title, "", *lines]:
        wrapped = textwrap.wrap(raw_line, width=92) if raw_line else [""]
        wrapped_lines.extend(wrapped)
    page_size = 44
    pages = [wrapped_lines[index : index + page_size] for index in range(0, len(wrapped_lines), page_size)]
    if not pages:
        pages = [[""]]

    objects: list[bytes] = []
    page_object_numbers: list[int] = []
    content_object_numbers: list[int] = []
    next_object_number = 4
    for page_lines in pages:
        page_object_numbers.append(next_object_number)
        content_object_numbers.append(next_object_number + 1)
        next_object_number += 2

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects.append(
        f"<< /Type /Pages /Count {len(page_object_numbers)} /Kids [{kids}] >>".encode("utf-8")
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for _, content_number, page_lines in zip(
        page_object_numbers, content_object_numbers, pages, strict=False
    ):
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>"
            ).encode("utf-8")
        )
        content = _pdf_content_stream(page_lines)
        objects.append(
            f"<< /Length {len(content)} >>\nstream\n".encode("utf-8") + content + b"\nendstream"
        )

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    body = bytearray(header)
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body.extend(f"{index} 0 obj\n".encode("utf-8"))
        body.extend(obj)
        body.extend(b"\nendobj\n")
    xref_offset = len(body)
    body.extend(f"xref\n0 {len(offsets)}\n".encode("utf-8"))
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
    body.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("utf-8")
    )
    path.write_bytes(bytes(body))


def _write_image_pdf(path: Path, *, frames: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not frames:
        raise ValueError("Cannot build image PDF without captured frames")

    objects: list[bytes] = []
    page_object_numbers: list[int] = []
    content_object_numbers: list[int] = []
    image_object_numbers: list[int] = []
    next_object_number = 4
    for _ in frames:
        page_object_numbers.append(next_object_number)
        content_object_numbers.append(next_object_number + 1)
        image_object_numbers.append(next_object_number + 2)
        next_object_number += 3

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects.append(
        f"<< /Type /Pages /Count {len(page_object_numbers)} /Kids [{kids}] >>".encode("utf-8")
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page_number, frame in enumerate(frames, start=1):
        image_bytes = frame["path"].read_bytes()
        width, height = _image_dimensions(frame["path"], image_bytes)
        page_object = page_object_numbers[page_number - 1]
        content_object = content_object_numbers[page_number - 1]
        image_object = image_object_numbers[page_number - 1]
        content = _image_pdf_content_stream(
            label=f"{frame['relative_path']} [{frame['label']}]",
            width=width,
            height=height,
        )
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> /XObject << /Im1 {image_object} 0 R >> >> "
                f"/Contents {content_object} 0 R >>"
            ).encode("utf-8")
        )
        objects.append(
            f"<< /Length {len(content)} >>\nstream\n".encode("utf-8") + content + b"\nendstream"
        )
        objects.append(
            (
                f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
                f"/Length {len(image_bytes)} >>\nstream\n"
            ).encode("utf-8")
            + image_bytes
            + b"\nendstream"
        )

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    body = bytearray(header)
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body.extend(f"{index} 0 obj\n".encode("utf-8"))
        body.extend(obj)
        body.extend(b"\nendobj\n")
    xref_offset = len(body)
    body.extend(f"xref\n0 {len(offsets)}\n".encode("utf-8"))
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
    body.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("utf-8")
    )
    path.write_bytes(bytes(body))


def _image_pdf_content_stream(*, label: str, width: int, height: int) -> bytes:
    page_width = 612
    page_height = 792
    max_width = 512
    max_height = 640
    scale = min(max_width / width, max_height / height, 1.0)
    draw_width = width * scale
    draw_height = height * scale
    x = (page_width - draw_width) / 2
    y = 96
    text_y = y + draw_height + 24
    commands = [
        "BT",
        "/F1 12 Tf",
        f"50 {text_y:.2f} Td",
        f"({ _pdf_escape(label) }) Tj",
        "ET",
        "q",
        f"{draw_width:.2f} 0 0 {draw_height:.2f} {x:.2f} {y:.2f} cm",
        "/Im1 Do",
        "Q",
    ]
    return "\n".join(commands).encode("utf-8")


def _jpeg_dimensions(payload: bytes) -> tuple[int, int]:
    if not payload.startswith(b"\xff\xd8"):
        raise ValueError("Image report currently requires JPEG capture outputs")
    index = 2
    while index < len(payload):
        while index < len(payload) and payload[index] == 0xFF:
            index += 1
        if index >= len(payload):
            break
        marker = payload[index]
        index += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(payload):
            break
        segment_length = int.from_bytes(payload[index : index + 2], "big")
        if segment_length < 2 or index + segment_length > len(payload):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if index + 7 > len(payload):
                break
            height = int.from_bytes(payload[index + 3 : index + 5], "big")
            width = int.from_bytes(payload[index + 5 : index + 7], "big")
            return width, height
        index += segment_length
    raise ValueError("Unable to determine JPEG dimensions")


def _image_dimensions(path: Path, payload: bytes) -> tuple[int, int]:
    sips = shutil.which("sips")
    if sips is not None:
        completed = subprocess.run(
            [sips, "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            width = None
            height = None
            for line in completed.stdout.splitlines():
                if "pixelWidth:" in line:
                    raw = line.split(":", 1)[1].strip()
                    if raw.isdigit():
                        width = int(raw)
                if "pixelHeight:" in line:
                    raw = line.split(":", 1)[1].strip()
                    if raw.isdigit():
                        height = int(raw)
            if width and height:
                return width, height
    try:
        return _jpeg_dimensions(payload)
    except ValueError:
        return (1, 1)


def _pdf_content_stream(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 11 Tf", "50 770 Td", "14 TL"]
    first = True
    for line in lines:
        escaped = _pdf_escape(line)
        if first:
            commands.append(f"({escaped}) Tj")
            first = False
        else:
            commands.append(f"T* ({escaped}) Tj")
    commands.append("ET")
    return "\n".join(commands).encode("utf-8")


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _parse_metadata_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return data if isinstance(data, dict) else {"value": data}


def _stringify_cell_value(value: Any) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if value is not None else ""
    return json.dumps(value, sort_keys=True)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
