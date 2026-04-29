"""Runtime metadata parsing integration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.parsers.base import Parser
from app.parsers.braw_parser import BrawUnavailableError
from app.persistence.db import Database
from app.persistence.models import Clip, JobFile
from app.persistence.repositories import ClipRepository, JobFileRepository, deterministic_id


@dataclass(frozen=True)
class ParseResult:
    clips: list[Clip]
    unavailable_reason: str | None = None


class ParseService:
    """Parse verified file results through a runtime parser."""

    def __init__(self, database: Database, parser: Parser) -> None:
        self.database = database
        self.parser = parser

    def parse_job(self, job_id: str, footage_root: Path) -> ParseResult:
        clips: list[Clip] = []
        unavailable_reason: str | None = None
        with self.database.session() as connection:
            files = JobFileRepository(connection).list_for_job(job_id)
            clip_repo = ClipRepository(connection)
            for file_result in files:
                if file_result.status not in {"verified", "warn"}:
                    continue
                source = footage_root / file_result.source_relpath
                try:
                    metadata = self.parser.parse_metadata(source)
                    integrity = self.parser.check_integrity(source)
                except (BrawUnavailableError, OSError) as exc:
                    unavailable_reason = str(exc)
                    continue
                clip = _clip_from_metadata(
                    job_id=job_id,
                    file_result=file_result,
                    parser_version=self.parser.get_version(),
                    metadata=metadata.metadata,
                    integrity_status=integrity.state.value,
                    capture_status="pending",
                )
                clips.append(clip_repo.upsert(clip))
        return ParseResult(clips=clips, unavailable_reason=unavailable_reason)


def _clip_from_metadata(
    *,
    job_id: str,
    file_result: JobFile,
    parser_version: str,
    metadata: dict[str, str | int | float | bool | None],
    integrity_status: str,
    capture_status: str,
) -> Clip:
    return Clip(
        clip_id=deterministic_id("clip", job_id, file_result.file_id),
        job_id=job_id,
        file_id=file_result.file_id,
        format_name="BRAW",
        parser_version=parser_version,
        metadata_json=json.dumps(metadata, sort_keys=True),
        integrity_status=integrity_status,
        capture_status=capture_status,
    )
