from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent
from typing import Iterator


JPEG_BASE64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxAQEBAQEBAVFRUVFRUVFRUVFRUVFRUVFRUXFhUV"
    "FRUYHSggGBolHRUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGxAQGy0lICUtLS0tLS0tLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMBIgACEQEDEQH/"
    "xAAbAAEAAwEBAQEAAAAAAAAAAAAABQYHBAIDAf/EADUQAAIBAgQDBgQEBwAAAAAAAAECAwQRAAUS"
    "ITFBBhMiUWFxgZEHFDJCkaGx0fAHI0Lh8RX/xAAaAQEAAwEBAQAAAAAAAAAAAAAAAQIDBAUG/8QAKR"
    "EAAgIBAwMDBAMAAAAAAAAAAAECEQMEEiExQRMiUWEUMnGBkbHB8P/aAAwDAQACEQMRAD8A+8REQBER"
    "AEREAREQBERAEREAREQBERAEREAREQB//2Q=="
)


def create_fake_adapter_scripts(root: Path) -> tuple[Path, Path]:
    metadata_script = root / "fake_braw_metadata.py"
    metadata_script.write_text(
        dedent(
            """
            #!/usr/bin/env python3
            import json
            import sys
            from pathlib import Path

            file_path = Path(sys.argv[1])
            print(json.dumps({
                "clip_name": file_path.stem,
                "reel_name": "R01",
                "camera_id": "CAM-A",
                "codec": "BRAW",
                "resolution_width": 4096,
                "resolution_height": 2160,
                "fps": 24.0,
                "duration_frames": 240,
                "timecode_start": "01:00:00:00",
                "shot_date": "2026-04-06",
                "iso_value": 800,
                "white_balance_kelvin": 5600,
                "lens": {"model": "Prime 35mm", "focal_length_mm": 35, "aperture": 2.8}
            }))
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    capture_script = root / "fake_braw_capture.py"
    capture_script.write_text(
        dedent(
            f"""
            #!/usr/bin/env python3
            import base64
            import json
            import sys
            from pathlib import Path

            _, source_path, output_dir, indices_csv = sys.argv
            output_root = Path(output_dir)
            output_root.mkdir(parents=True, exist_ok=True)
            payload = base64.b64decode("{JPEG_BASE64}")
            frames = []
            for index in [int(item) for item in indices_csv.split(",") if item]:
                path = output_root / f"frame-{{index}}.jpg"
                path.write_bytes(payload)
                frames.append({{"path": str(path), "index": index}})
            print(json.dumps(frames))
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    for path in (metadata_script, capture_script):
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return metadata_script, capture_script


@contextmanager
def fake_adapter_environment(root: Path) -> Iterator[tuple[Path, Path]]:
    metadata_script, capture_script = create_fake_adapter_scripts(root)
    previous_metadata = os.environ.get("FDM_BRAW_METADATA_COMMAND")
    previous_capture = os.environ.get("FDM_BRAW_FRAME_CAPTURE_COMMAND")
    os.environ["FDM_BRAW_METADATA_COMMAND"] = str(metadata_script)
    os.environ["FDM_BRAW_FRAME_CAPTURE_COMMAND"] = str(capture_script)
    try:
        yield metadata_script, capture_script
    finally:
        if previous_metadata is None:
            os.environ.pop("FDM_BRAW_METADATA_COMMAND", None)
        else:
            os.environ["FDM_BRAW_METADATA_COMMAND"] = previous_metadata
        if previous_capture is None:
            os.environ.pop("FDM_BRAW_FRAME_CAPTURE_COMMAND", None)
        else:
            os.environ["FDM_BRAW_FRAME_CAPTURE_COMMAND"] = previous_capture
