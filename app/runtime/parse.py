from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from app.parsers.base import BaseParser
from app.parsers.registry import get_registered_parsers, select_parser
from app.parsers.types import ClipMetadata
from app.persistence.db import Database
from app.runtime.events import utc_now_iso


class MetadataParseService:
    """Runtime-local metadata parsing and persistence surface.

    The browser should consume only the safe dict payloads returned here.
    Filesystem paths stay local to the runtime call-site.
    """

    def __init__(self, database: Database, parsers: Iterable[BaseParser] | None = None) -> None:
        self.database = database
        self.parsers = list(parsers or get_registered_parsers())

    def parse_file(
        self,
        *,
        job_id: str,
        job_file_id: int,
        relative_path: str,
        source_path: str,
    ) -> dict[str, Any]:
        parser = select_parser(Path(source_path), self.parsers)
        if parser is None:
            metadata = ClipMetadata(
                clip_name=Path(relative_path).stem,
                raw_metadata={
                    "metadata_status": "unsupported",
                    "metadata_source": "none",
                    "parser_notes": ["No registered parser accepted this file."],
                },
            )
            return self._persist_result(
                job_id=job_id,
                job_file_id=job_file_id,
                relative_path=relative_path,
                parser_name=None,
                parser_version=None,
                format_name=Path(relative_path).suffix.lstrip(".").upper() or "unknown",
                metadata=metadata,
                parse_state="UNSUPPORTED",
            )

        try:
            metadata = parser.parse_metadata(Path(source_path))
        except Exception as exc:
            self.mark_parse_failure(
                job_file_id=job_file_id,
                parser_name=parser.__class__.__name__,
                reason=str(exc),
            )
            raise
        parse_state = "PARSED" if parser.capabilities().metadata else "CAPABILITY_GATED"
        return self._persist_result(
            job_id=job_id,
            job_file_id=job_file_id,
            relative_path=relative_path,
            parser_name=parser.__class__.__name__,
            parser_version=parser.get_version(),
            format_name=parser.get_format_name(),
            metadata=metadata,
            parse_state=parse_state,
        )

    def mark_parse_failure(
        self,
        *,
        job_file_id: int,
        parser_name: str | None,
        reason: str,
    ) -> None:
        with self.database.connect() as connection:
            existing_row = connection.execute(
                "SELECT metadata_json FROM job_files WHERE job_file_id = ?",
                (job_file_id,),
            ).fetchone()
            metadata_json = existing_row["metadata_json"] if existing_row is not None else None
            metadata = self._load_json(metadata_json)
            metadata["parser"] = {
                "name": parser_name,
                "status": "failed",
                "reason": reason,
            }
            connection.execute(
                """
                UPDATE job_files
                SET parser_name = ?, parse_state = 'FAILED', error_code = 'metadata_parse_failed',
                    metadata_json = ?, updated_at = ?
                WHERE job_file_id = ?
                """,
                (parser_name, json.dumps(metadata, sort_keys=True), utc_now_iso(), job_file_id),
            )
            connection.commit()

    def list_clips(self, *, job_id: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        query = """
            SELECT c.*, jf.relative_path, jf.parse_state, jf.parser_name
            FROM clips c
            JOIN job_files jf ON jf.job_file_id = c.job_file_id
        """
        params: list[Any] = []
        if job_id is not None:
            query += " WHERE c.job_id = ?"
            params.append(job_id)
        query += " ORDER BY c.parsed_at DESC, c.clip_id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._serialize_clip_row(dict(row)) for row in rows]

    def _persist_result(
        self,
        *,
        job_id: str,
        job_file_id: int,
        relative_path: str,
        parser_name: str | None,
        parser_version: str | None,
        format_name: str,
        metadata: ClipMetadata,
        parse_state: str,
    ) -> dict[str, Any]:
        parsed_at = utc_now_iso()
        clip_id = f"{job_id}:{job_file_id}"
        with self.database.connect() as connection:
            existing_row = connection.execute(
                "SELECT metadata_json FROM job_files WHERE job_file_id = ?",
                (job_file_id,),
            ).fetchone()
            existing_metadata = self._load_json(
                existing_row["metadata_json"] if existing_row is not None else None
            )
            existing_metadata["parser"] = {
                "name": parser_name,
                "version": parser_version,
                "format_name": format_name,
                "parse_state": parse_state,
            }
            existing_metadata["clip"] = metadata.as_safe_payload()
            connection.execute(
                """
                UPDATE job_files
                SET parser_name = ?, parse_state = ?, metadata_json = ?, updated_at = ?
                WHERE job_file_id = ?
                """,
                (
                    parser_name,
                    parse_state,
                    json.dumps(existing_metadata, sort_keys=True),
                    parsed_at,
                    job_file_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO clips (
                    clip_id, job_id, job_file_id, format_name, parser_version,
                    clip_name, reel_name, camera_id, codec, resolution_width,
                    resolution_height, fps, duration_frames, timecode_start,
                    shot_date, iso_value, white_balance_kelvin, lens_json,
                    raw_metadata_json, parsed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(clip_id) DO UPDATE SET
                    format_name = excluded.format_name,
                    parser_version = excluded.parser_version,
                    clip_name = excluded.clip_name,
                    reel_name = excluded.reel_name,
                    camera_id = excluded.camera_id,
                    codec = excluded.codec,
                    resolution_width = excluded.resolution_width,
                    resolution_height = excluded.resolution_height,
                    fps = excluded.fps,
                    duration_frames = excluded.duration_frames,
                    timecode_start = excluded.timecode_start,
                    shot_date = excluded.shot_date,
                    iso_value = excluded.iso_value,
                    white_balance_kelvin = excluded.white_balance_kelvin,
                    lens_json = excluded.lens_json,
                    raw_metadata_json = excluded.raw_metadata_json,
                    parsed_at = excluded.parsed_at
                """,
                (
                    clip_id,
                    job_id,
                    job_file_id,
                    format_name,
                    parser_version or "unknown",
                    metadata.clip_name,
                    metadata.reel_name,
                    metadata.camera_id,
                    metadata.codec,
                    metadata.resolution_width,
                    metadata.resolution_height,
                    metadata.fps,
                    metadata.duration_frames,
                    metadata.timecode_start,
                    metadata.shot_date,
                    metadata.iso_value,
                    metadata.white_balance_kelvin,
                    json.dumps(metadata.lens, sort_keys=True) if metadata.lens is not None else None,
                    json.dumps(metadata.raw_metadata, sort_keys=True),
                    parsed_at,
                ),
            )
            connection.commit()

        return {
            "clip_id": clip_id,
            "job_id": job_id,
            "job_file_id": job_file_id,
            "relative_path": relative_path,
            "parser_name": parser_name,
            "parser_version": parser_version,
            "format_name": format_name,
            "parse_state": parse_state,
            "parsed_at": parsed_at,
            **metadata.as_safe_payload(),
        }

    @staticmethod
    def _load_json(raw_json: str | None) -> dict[str, Any]:
        if not raw_json:
            return {}
        loaded = json.loads(raw_json)
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _serialize_clip_row(row: dict[str, Any]) -> dict[str, Any]:
        raw_metadata = MetadataParseService._load_json(row.get("raw_metadata_json"))
        return {
            "clip_id": row["clip_id"],
            "job_id": row["job_id"],
            "job_file_id": row["job_file_id"],
            "relative_path": row["relative_path"],
            "format_name": row["format_name"],
            "parser_name": row["parser_name"],
            "parser_version": row["parser_version"],
            "parse_state": row["parse_state"],
            "clip_name": row["clip_name"],
            "reel_name": row["reel_name"],
            "camera_id": row["camera_id"],
            "codec": row["codec"],
            "resolution_width": row["resolution_width"],
            "resolution_height": row["resolution_height"],
            "fps": row["fps"],
            "duration_frames": row["duration_frames"],
            "timecode_start": row["timecode_start"],
            "shot_date": row["shot_date"],
            "iso_value": row["iso_value"],
            "white_balance_kelvin": row["white_balance_kelvin"],
            "lens": json.loads(row["lens_json"]) if row["lens_json"] else None,
            "metadata_status": raw_metadata.get("metadata_status", "unknown"),
            "metadata_source": raw_metadata.get("metadata_source", "unknown"),
            "parser_notes": list(raw_metadata.get("parser_notes", [])),
            "parsed_at": row["parsed_at"],
        }
