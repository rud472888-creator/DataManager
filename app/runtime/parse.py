"""Runtime metadata parsing integration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.parsers.base import Parser
from app.parsers.errors import ParserUnavailableError
from app.parsers.registry import ParserRegistry
from app.persistence.db import Database
from app.persistence.models import Clip, JobFile
from app.persistence.repositories import ClipRepository, JobFileRepository, deterministic_id


@dataclass(frozen=True)
class ParseResult:
    clips: list[Clip]
    unavailable_reason: str | None = None


class ParseService:
    """Parse verified file results through a runtime parser."""

    def __init__(self, database: Database, parser: Parser | ParserRegistry) -> None:
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
                source = footage_root / file_result.source_path_id / file_result.source_relpath
                parser = self._parser_for(source)
                if parser is None:
                    unavailable_reason = f"no parser registered for {source.suffix.lower()}"
                    continue
                try:
                    metadata = parser.parse_metadata(source)
                    integrity = parser.check_integrity(source)
                except (ParserUnavailableError, OSError) as exc:
                    unavailable_reason = str(exc)
                    continue
                clip = _clip_from_metadata(
                    job_id=job_id,
                    file_result=file_result,
                    format_name=metadata.format_name,
                    parser_version=parser.get_version(),
                    metadata=metadata.metadata,
                    integrity_status=integrity.state.value,
                    capture_status="pending",
                )
                clips.append(clip_repo.upsert(clip))
        return ParseResult(clips=clips, unavailable_reason=unavailable_reason)

    def _parser_for(self, file_path: Path) -> Parser | None:
        if isinstance(self.parser, ParserRegistry):
            for parser in self.parser.all():
                if parser.probe(file_path).supported:
                    return parser
            return None
        if self.parser.probe(file_path).supported:
            return self.parser
        return None


def _clip_from_metadata(
    *,
    job_id: str,
    file_result: JobFile,
    format_name: str,
    parser_version: str,
    metadata: dict[str, str | int | float | bool | None],
    integrity_status: str,
    capture_status: str,
) -> Clip:
    return Clip(
        clip_id=deterministic_id("clip", job_id, file_result.file_id),
        job_id=job_id,
        file_id=file_result.file_id,
        format_name=format_name,
        parser_version=parser_version,
        metadata_json=json.dumps(metadata, sort_keys=True),
        integrity_status=integrity_status,
        capture_status=capture_status,
    )
