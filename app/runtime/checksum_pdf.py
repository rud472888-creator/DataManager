"""Readable, evidence-preserving checksum documents from persisted job records."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.enums import TA_LEFT  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.persistence.models import JobFile, JobFileReplica

INK = colors.HexColor("#172C32")
MUTED = colors.HexColor("#5F7278")
ACCENT = colors.HexColor("#146C66")
LINE = colors.HexColor("#D9E2E3")
PALE = colors.HexColor("#F1F6F5")
FONT = "DH-Sans"
BOLD = "DH-Sans-Bold"
WIDTH = A4[0] - 80
MISSING = "미기록"


def _fonts() -> None:
    root = Path(__file__).with_name("fonts")
    for name, weight in ((FONT, "Regular"), (BOLD, "Bold")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(root / f"DataHandlerSans-{weight}.ttf")))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=BOLD)


def _p(
    value: object,
    *,
    size: float = 9,
    bold: bool = False,
    color: colors.Color = INK,
    breakable: bool = False,
) -> Paragraph:
    text = MISSING if value is None or value == "" else str(value)
    return Paragraph(
        escape(text).replace("\n", "<br/>"),
        ParagraphStyle(
            "text",
            fontName=BOLD if bold else FONT,
            fontSize=size,
            leading=size * 1.5,
            textColor=color,
            alignment=TA_LEFT,
            splitLongWords=breakable,
            wordWrap=None,
            spaceAfter=0,
        ),
    )


def _hash_valid(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[0-9a-fA-F]{64}", value))


def _comparison(file: JobFile, replica: JobFileReplica | None) -> str:
    if replica is None:
        return "복제 기록 없음"
    if not _hash_valid(file.checksum_source) or not _hash_valid(replica.checksum):
        return "해시 미기록 / 형식 확인 필요"
    if file.checksum_source.lower() != replica.checksum.lower():  # type: ignore[union-attr]
        return "불일치"
    if (
        replica.status != "verified"
        or not replica.dest_relpath
        or replica.error_code
        or replica.error_message
    ):
        return "해시 일치 / 복제 상태 확인 필요"
    return "일치"


def _verified(file: JobFile, expected: tuple[str, ...]) -> bool:
    by_id = {replica.path_id: replica for replica in file.replica_results}
    return bool(
        expected
        and file.status == "verified"
        and not file.error_code
        and not file.error_message
        and all(_comparison(file, by_id.get(path_id)) == "일치" for path_id in expected)
        and all(_comparison(file, replica) == "일치" for replica in file.replica_results)
    )


def _table(rows: list[list[object]], widths: list[float], *, header: bool = False) -> Table:
    table = Table(
        rows,
        colWidths=widths,
        repeatRows=1 if header else 0,
        hAlign="LEFT",
        splitByRow=1,
        splitInRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, -1), 0.45, LINE),
                *(([("BACKGROUND", (0, 0), (-1, 0), PALE)]) if header else []),
            ]
        )
    )
    return table


def _fields(rows: list[tuple[str, object]]) -> Table:
    table = _table(
        [[_p(label, size=8, color=MUTED), _p(value, breakable=True)] for label, value in rows],
        [100, WIDTH - 100],
    )
    table.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


class _NumberedCanvas(canvas.Canvas):  # type: ignore[misc]
    """Replay finished pages only to add their bounded page-count footer."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._saved_pages: list[dict[str, object]] = []

    def showPage(self) -> None:
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self.setStrokeColor(LINE)
            self.setLineWidth(0.5)
            self.line(40, 37, A4[0] - 40, 37)
            self.setFont(FONT, 7.5)
            self.setFillColor(MUTED)
            self.drawString(40, 24, "DATA HANDLER  /  COPY INTEGRITY")
            self.drawRightString(A4[0] - 40, 24, f"{self._pageNumber:02} / {total:02}")
            super().showPage()
        super().save()


def _page_header(pdf: canvas.Canvas, doc: SimpleDocTemplate) -> None:
    pdf.saveState()
    pdf.setFont(BOLD, 7)
    pdf.setFillColor(ACCENT)
    pdf.drawString(40, A4[1] - 26, "DATA HANDLER     /     VERIFICATION REPORT")
    pdf.restoreState()


def write_checksum_pdf(
    path: Path,
    *,
    job_id: str,
    project_name: str,
    files: list[JobFile],
    expected_replica_ids: tuple[str, ...],
) -> None:
    """Render every stored row, including failed and missing destinations, in input order."""
    _fonts()
    path.parent.mkdir(parents=True, exist_ok=True)
    verified = sum(_verified(file, expected_replica_ids) for file in files)
    review = len(files) - verified
    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z (UTC%z)")
    story: list[object] = [
        Spacer(1, 18),
        _p("복제 무결성 보고서", size=29, bold=True),
        Spacer(1, 10),
        _p(project_name, size=16, bold=True, breakable=True),
        Spacer(1, 8),
        _p(f"생성 {generated}", size=8, color=MUTED),
        Spacer(1, 24),
    ]
    verdict = (
        "복제 증거 확인 완료"
        if files and not review
        else ("확인이 필요한 파일이 있습니다" if files else "검증할 파일이 없습니다")
    )
    story.extend(
        [
            _p(verdict, size=16, bold=True, color=ACCENT if files and not review else INK),
            Spacer(1, 13),
            _table(
                [
                    [
                        _p("전체 파일", size=8, color=MUTED),
                        _p("검증 완료", size=8, color=MUTED),
                        _p("확인 필요", size=8, color=MUTED),
                        _p("원본 용량", size=8, color=MUTED),
                    ],
                    [
                        _p(f"{len(files):,}", size=24, bold=True),
                        _p(f"{verified:,}", size=24, bold=True),
                        _p(f"{review:,}", size=24, bold=True),
                        _p(
                            f"{sum(file.size_bytes for file in files) / (1024**3):,.2f} GiB",
                            size=17,
                            bold=True,
                        ),
                    ],
                ],
                [WIDTH / 4] * 4,
            ),
            Spacer(1, 16),
            _p("검증 기준", size=10, bold=True),
            Spacer(1, 4),
            _p(
                "저장된 원본 SHA-256과 각 복제본의 SHA-256을 비교합니다. "
                "모든 지정 경로에 해시, 저장 경로와 verified 상태가 있고 오류가 없는 파일만 "
                "검증 완료로 집계합니다. 이 문서는 저장된 작업 결과를 기록하며 "
                "파일을 다시 읽어 검사하지 않습니다.",
                size=9,
                color=MUTED,
            ),
            Spacer(1, 14),
            _fields(
                [
                    ("작업 ID", job_id),
                    ("지정 복제 경로 ID", ", ".join(expected_replica_ids) or MISSING),
                    ("전체 원본 바이트", f"{sum(file.size_bytes for file in files):,} bytes"),
                ]
            ),
            Spacer(1, 18),
        ]
    )
    if review:
        story.extend([_p("먼저 확인할 파일", size=12, bold=True), Spacer(1, 8)])
        rows: list[list[object]] = [
            [
                _p("순서", bold=True, size=8),
                _p("원본 파일", bold=True, size=8),
                _p("기록 상태", bold=True, size=8),
            ]
        ]
        rows += [
            [
                _p(f"{i:03}", size=8),
                _p(file.source_relpath, size=8, breakable=True),
                _p(file.status, size=8, breakable=True),
            ]
            for i, file in enumerate(files, 1)
            if not _verified(file, expected_replica_ids)
        ]
        story += [_table(rows, [43, WIDTH - 125, 82], header=True), Spacer(1, 18)]

    if files:
        story.append(PageBreak())
    for index, file in enumerate(files, 1):
        file_start = len(story)
        result = "검증 완료" if _verified(file, expected_replica_ids) else "확인 필요"
        story.extend(
            [
                Spacer(1, 8),
                _p(f"{index:03}  /  파일 검증", size=9, bold=True, color=ACCENT),
                Spacer(1, 5),
                _p(file.source_relpath, size=14, bold=True, breakable=True),
                Spacer(1, 6),
                _p(f"{result}  |  기록 상태: {file.status}", size=9, bold=True),
                Spacer(1, 8),
            ]
        )
        story.extend(
            [
                _p(
                    f"파일 ID: {file.file_id}  /  원본 경로 ID: {file.source_path_id}  /  "
                    f"크기: {file.size_bytes:,} bytes",
                    size=8,
                    color=MUTED,
                    breakable=True,
                ),
                Spacer(1, 7),
            ]
        )
        story.append(
            _fields(
                [
                    ("Source SHA256", file.checksum_source),
                ]
            )
        )
        by_id = {replica.path_id: replica for replica in file.replica_results}
        # Preserve recorded replica order; append missing configured destinations.
        destinations = list(file.replica_results) + [
            JobFileReplica(file.file_id, key, None, None, "missing")
            for key in expected_replica_ids
            if key not in by_id
        ]
        if not expected_replica_ids:
            story += [
                Spacer(1, 8),
                _p("지정 복제 경로 정보가 없어 전체 완료를 확인할 수 없습니다.", size=9),
            ]
        for replica in destinations:
            comparison = _comparison(file, by_id.get(replica.path_id))
            story += [
                Spacer(1, 12),
                _p(f"복제본  /  {replica.path_id}", size=10, bold=True, breakable=True),
                Spacer(1, 4),
                _p(
                    f"{comparison}  |  기록 상태: {replica.status}",
                    size=9,
                    color=ACCENT if comparison == "일치" else colors.HexColor("#9F422D"),
                ),
                Spacer(1, 4),
                _fields(
                    [
                        ("저장 경로", replica.dest_relpath),
                        ("Replica SHA256", replica.checksum),
                        *(
                            (
                                [
                                    ("오류 코드", replica.error_code),
                                    ("오류 내용", replica.error_message),
                                ]
                            )
                            if replica.error_code or replica.error_message
                            else []
                        ),
                    ]
                ),
            ]
        if file.error_code or file.error_message:
            story += [
                Spacer(1, 8),
                _fields(
                    [("파일 오류 코드", file.error_code), ("파일 오류 내용", file.error_message)]
                ),
            ]
        # Keep ordinary file evidence together; oversized evidence remains splittable.
        story[file_start:] = [KeepTogether(story[file_start:])]
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=45,
        bottomMargin=51,
        title=f"{project_name} | 복제 무결성 보고서",
        author="Data Handler",
        pageCompression=1,
    )
    doc.build(
        story, onFirstPage=_page_header, onLaterPages=_page_header, canvasmaker=_NumberedCanvas
    )
