import json

from app.parsers.braw_parser import BrawAdapter, MockBrawParser
from app.parsers.standard_video_parser import StandardVideoParser
from app.persistence.db import Database
from app.persistence.migrations import apply_migrations
from app.persistence.repositories import ClipRepository, JobRepository, ReportRepository
from app.runtime.offload import DestinationPlan, OffloadService
from app.runtime.parse import ParseService
from app.runtime.reports import ReportService


def _source_tree(tmp_path):
    source = tmp_path / "source"
    (source / "A001").mkdir(parents=True)
    (source / "A001" / "A001_C001.braw").write_bytes(b"clip-one")
    return source


def _offloaded_job(tmp_path):
    database = Database(tmp_path / "fdm.sqlite3")
    with database.session() as connection:
        apply_migrations(connection)
        job = JobRepository(connection).create_stub_job("Reports")
    source = _source_tree(tmp_path)
    plan = DestinationPlan("Reports", tmp_path / "main", tmp_path / "backup")
    OffloadService(database).execute(job_id=job.job_id, source_root=source, plan=plan)
    return database, job.job_id, plan.main_project_root


def _offloaded_video_job(tmp_path):
    database = Database(tmp_path / "fdm.sqlite3")
    with database.session() as connection:
        apply_migrations(connection)
        job = JobRepository(connection).create_stub_job("Video Reports")
    source = tmp_path / "source"
    (source / "Video").mkdir(parents=True)
    (source / "Video" / "B001_C001.mov").write_bytes(b"quicktime")
    plan = DestinationPlan("Video Reports", tmp_path / "main", tmp_path / "backup")
    OffloadService(database).execute(job_id=job.job_id, source_root=source, plan=plan)
    return database, job.job_id, plan.main_project_root


def test_mock_parse_persists_clip_metadata(tmp_path) -> None:
    database, job_id, project_root = _offloaded_job(tmp_path)

    result = ParseService(database, MockBrawParser()).parse_job(
        job_id,
        project_root / "01_Footage" / "R#1",
    )

    assert len(result.clips) == 1
    assert result.unavailable_reason is None
    with database.session() as connection:
        clips = ClipRepository(connection).list_for_job(job_id)

    assert len(clips) == 1
    assert json.loads(clips[0].metadata_json)["mock"] is True


def test_real_parser_unavailable_does_not_fabricate_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FDM_BRAW_METADATA_COMMAND", raising=False)
    database, job_id, project_root = _offloaded_job(tmp_path)

    result = ParseService(database, BrawAdapter.from_environment()).parse_job(
        job_id,
        project_root / "01_Footage" / "R#1",
    )

    assert result.clips == []
    assert "not configured" in (result.unavailable_reason or "")


def test_standard_video_parse_persists_ffprobe_metadata(tmp_path) -> None:
    database, job_id, project_root = _offloaded_video_job(tmp_path)
    ffprobe = _write_ffprobe_command(
        tmp_path,
        {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30000/1001",
                }
            ],
            "format": {"duration": "3.5", "size": "4096"},
        },
    )

    result = ParseService(database, StandardVideoParser(str(ffprobe))).parse_job(
        job_id,
        project_root / "01_Footage" / "R#1",
    )

    assert len(result.clips) == 1
    assert result.unavailable_reason is None
    with database.session() as connection:
        clips = ClipRepository(connection).list_for_job(job_id)

    assert len(clips) == 1
    assert clips[0].format_name == "STANDARD_VIDEO"
    assert clips[0].integrity_status == "ok"
    metadata = json.loads(clips[0].metadata_json)
    assert metadata["video_codec"] == "h264"
    assert metadata["width"] == 1920
    assert metadata["height"] == 1080


def test_clone_report_generation_persists_checksum_and_manifest(tmp_path) -> None:
    database, job_id, project_root = _offloaded_job(tmp_path)

    result = ReportService(database).generate(
        job_id=job_id,
        project_root=project_root,
    )

    reports = {report.report_type: report for report in result.reports}
    assert reports["checksum_pdf"].status == "ready"
    assert reports["manifest_json"].status == "ready"
    checksum_pdf = project_root / "00_Master/reports/checksum.pdf"
    pdf_bytes = checksum_pdf.read_bytes()
    assert pdf_bytes.startswith(b"%PDF")
    assert b"startxref" in pdf_bytes
    assert b"trailer" in pdf_bytes
    assert b"/BaseFont /Helvetica" in pdf_bytes
    assert b"Source SHA256" in pdf_bytes
    _assert_pdf_startxref_points_to_xref(pdf_bytes)
    manifest = json.loads((project_root / "00_Master/manifests/manifest.json").read_text())
    assert manifest["job_id"] == job_id
    assert len(manifest["files"]) == 1
    assert "clips" not in manifest
    assert not (project_root / "00_Master/reports/metadata.xlsx").exists()
    assert not (project_root / "00_Master/reports/image.pdf").exists()

    with database.session() as connection:
        persisted = ReportRepository(connection).list_for_job(job_id)

    assert {report.report_type for report in persisted} == {
        "checksum_pdf",
        "manifest_json",
    }


def _assert_pdf_startxref_points_to_xref(pdf_bytes: bytes) -> None:
    startxref = int(pdf_bytes.rsplit(b"startxref\n", maxsplit=1)[1].splitlines()[0])
    assert pdf_bytes[startxref : startxref + 4] == b"xref"


def _write_ffprobe_command(tmp_path, payload: dict[str, object]):
    command = tmp_path / "ffprobe.py"
    command.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        f"print(json.dumps({json.dumps(payload)}))\n"
    )
    command.chmod(0o755)
    return command
