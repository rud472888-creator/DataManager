from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

from app.parsers.base import BaseParser
from app.parsers.registry import get_registered_parsers, select_parser
from app.persistence.db import Database
from app.runtime.events import utc_now_iso


class FrameCaptureService:
    """Runtime-local frame capture and persistence adapter.

    Capture outputs are always produced and moved by the local runtime.
    """

    def __init__(self, database: Database, parsers: Iterable[BaseParser] | None = None) -> None:
        self.database = database
        self.parsers = list(parsers or get_registered_parsers())

    def capture_file(
        self,
        *,
        job_file_id: int,
        relative_path: str,
        source_path: str,
        output_root: Path,
        indices: list[int],
    ) -> dict[str, Any]:
        parser = select_parser(Path(source_path), self.parsers)
        if parser is None:
            return self._persist_capability_gated(
                job_file_id=job_file_id,
                relative_path=relative_path,
                reason="No registered parser accepted this file.",
            )

        capabilities = parser.capabilities()
        if not capabilities.frame_capture:
            return self._persist_capability_gated(
                job_file_id=job_file_id,
                relative_path=relative_path,
                reason="Registered parser does not currently support frame capture.",
                parser_name=parser.__class__.__name__,
            )

        output_root.mkdir(parents=True, exist_ok=True)
        temp_output_root = Path(tempfile.mkdtemp(prefix="fdm-capture-"))
        try:
            generated_paths = parser.capture_frames(Path(source_path), indices)
            if len(generated_paths) != len(indices):
                raise RuntimeError("Frame capture adapter returned an unexpected frame count")

            frames: list[dict[str, Any]] = []
            for index_value, generated_path in zip(indices, generated_paths, strict=True):
                generated_path = generated_path.resolve()
                if not generated_path.exists():
                    raise RuntimeError(f"Captured frame does not exist: {generated_path}")
                destination = output_root / f"{Path(relative_path).stem}-frame-{index_value}{generated_path.suffix.lower()}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(generated_path), destination)
                frames.append(
                    {
                        "index": index_value,
                        "label": _label_for_index(index_value),
                        "path": str(destination),
                        "file_name": destination.name,
                        "file_size_bytes": destination.stat().st_size,
                        "captured_at": utc_now_iso(),
                    }
                )

            metadata = self._load_job_file_metadata(job_file_id)
            metadata["capture"] = {
                "status": "captured",
                "parser": parser.__class__.__name__,
                "frame_count": len(frames),
                "frames": frames,
            }
            with self.database.connect() as connection:
                connection.execute(
                    """
                    UPDATE job_files
                    SET capture_state = 'CAPTURED', metadata_json = ?, updated_at = ?
                    WHERE job_file_id = ?
                    """,
                    (json_dumps(metadata), utc_now_iso(), job_file_id),
                )
                connection.commit()
            return {
                "capture_state": "CAPTURED",
                "frames": frames,
                "parser_name": parser.__class__.__name__,
            }
        finally:
            shutil.rmtree(temp_output_root, ignore_errors=True)

    def _persist_capability_gated(
        self,
        *,
        job_file_id: int,
        relative_path: str,
        reason: str,
        parser_name: str | None = None,
    ) -> dict[str, Any]:
        metadata = self._load_job_file_metadata(job_file_id)
        metadata["capture"] = {
            "status": "capability_gated",
            "reason": reason,
            "parser": parser_name,
            "frames": [],
        }
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE job_files
                SET capture_state = 'CAPABILITY_GATED', warning_code = COALESCE(warning_code, 'frame_capture_unavailable'),
                    metadata_json = ?, updated_at = ?
                WHERE job_file_id = ?
                """,
                (json_dumps(metadata), utc_now_iso(), job_file_id),
            )
            connection.commit()
        return {
            "capture_state": "CAPABILITY_GATED",
            "frames": [],
            "reason": reason,
            "relative_path": relative_path,
        }

    def mark_capture_failure(
        self,
        *,
        job_file_id: int,
        reason: str,
    ) -> None:
        metadata = self._load_job_file_metadata(job_file_id)
        metadata["capture"] = {
            "status": "failed",
            "reason": reason,
            "frames": [],
        }
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE job_files
                SET capture_state = 'FAILED', warning_code = COALESCE(warning_code, 'frame_capture_failed'),
                    metadata_json = ?, updated_at = ?
                WHERE job_file_id = ?
                """,
                (json_dumps(metadata), utc_now_iso(), job_file_id),
            )
            connection.commit()

    def _load_job_file_metadata(self, job_file_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT metadata_json FROM job_files WHERE job_file_id = ?",
                (job_file_id,),
            ).fetchone()
        if row is None or not row["metadata_json"]:
            return {}
        import json

        loaded = json.loads(row["metadata_json"])
        return loaded if isinstance(loaded, dict) else {}


def _label_for_index(index_value: int) -> str:
    if index_value == 0:
        return "first"
    if index_value == 50:
        return "middle"
    if index_value == 100:
        return "last"
    return f"frame-{index_value}"


def json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, sort_keys=True)
