import re
from dataclasses import replace

from pypdf import PdfReader

from app.runtime.checksum_pdf import _comparison, _verified, write_checksum_pdf
from tests.runtime.checksum_pdf_fixtures import DESTINATIONS, PROJECT, pressure_files


def test_checksum_evidence_cannot_claim_success_without_complete_records():
    file = pressure_files(1)[0]
    replica = file.replica_results[0]
    assert _verified(file, DESTINATIONS)
    assert not _verified(file, ())
    assert not _verified(replace(file, status="failed"), DESTINATIONS)
    assert not _verified(replace(file, checksum_source=None), DESTINATIONS)
    assert not _verified(replace(file, replica_results=(replica,)), DESTINATIONS)
    for bad in [
        replace(replica, status="failed"),
        replace(replica, checksum="short"),
        replace(replica, checksum="f" * 64),
        replace(replica, dest_relpath=None),
        replace(replica, error_message="copy error"),
    ]:
        assert _comparison(file, bad) != "일치"
    assert _comparison(file, None) == "복제 기록 없음"
    assert _comparison(file, replace(replica, checksum="f" * 64)) == "불일치"


def test_checksum_pdf_preserves_korean_hashes_paths_errors_and_order(tmp_path):
    path = tmp_path / "DEBUG-DATA-checksum.pdf"
    files = pressure_files()
    write_checksum_pdf(
        path,
        job_id="DEBUG-JOB",
        project_name=PROJECT,
        files=files,
        expected_replica_ids=DESTINATIONS,
    )
    reader = PdfReader(path)
    texts = [page.extract_text() for page in reader.pages]
    text = "\n".join(texts)
    flat = "".join(text.split())
    assert len(reader.pages) > 2
    assert "".join(PROJECT.split()) in flat
    assert "복제기록없음" in flat
    assert "불일치" in text
    assert "촬영감독과스크립터가동시에확인해야하는상태값이다릅니다." in flat
    assert "재확인<take>&camera.mov" in flat
    assert "0 bytes" in text
    positions = []
    for file in files:
        assert "".join(file.source_relpath.split()) in flat
        assert file.checksum_source in flat
        positions.append(text.index(file.file_id))
    assert positions == sorted(positions)
    for i, page_text in enumerate(texts, 1):
        assert f"{i:02} / {len(texts):02}" in page_text
    font_descriptors = [
        font.get_object().get("/FontDescriptor")
        for page in reader.pages
        for font in page["/Resources"]["/Font"].values()
    ]
    assert any(ref and "/FontFile2" in ref.get_object() for ref in font_descriptors)


def test_empty_checksum_report_is_not_verified(tmp_path):
    path = tmp_path / "empty.pdf"
    write_checksum_pdf(
        path, job_id="empty", project_name="빈 작업", files=[], expected_replica_ids=DESTINATIONS
    )
    reader = PdfReader(path)
    assert len(reader.pages) == 1
    assert "검증할 파일이 없습니다" in reader.pages[0].extract_text()
    assert "복제 증거 확인 완료" not in reader.pages[0].extract_text()


def test_long_error_and_many_files_continue_without_losing_tail(tmp_path):
    files = pressure_files(40)
    files[0] = replace(
        files[0], error_message=("긴 오류 내용을 확인합니다. " * 500) + "FINAL-SENTINEL"
    )
    path = tmp_path / "pressure.pdf"
    write_checksum_pdf(
        path,
        job_id="pressure",
        project_name=PROJECT,
        files=files,
        expected_replica_ids=DESTINATIONS,
    )
    text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
    assert "FINAL-SENTINEL" in text
    assert "file-039" in text
    body = "".join(
        line
        for line in text.splitlines()
        if not line.startswith("DATA HANDLER") and not re.fullmatch(r"\d+ / \d+", line)
    )
    assert "".join(body.split()).count("긴오류내용을확인합니다.") == 500
