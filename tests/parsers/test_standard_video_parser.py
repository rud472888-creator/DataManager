import json

import pytest

from app.parsers.errors import ParserUnavailableError
from app.parsers.standard_video_parser import StandardVideoParser
from app.parsers.types import CapabilityState, IntegrityState


def test_standard_video_parser_reports_unavailable_without_ffprobe(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("FDM_FFPROBE_COMMAND", raising=False)
    monkeypatch.setenv("PATH", "")
    sample = tmp_path / "B001_C001.mov"
    sample.write_bytes(b"quicktime")

    parser = StandardVideoParser.from_environment()

    assert parser.capabilities().metadata is CapabilityState.UNAVAILABLE
    with pytest.raises(ParserUnavailableError, match="ffprobe"):
        parser.parse_metadata(sample)


def test_standard_video_parser_reads_ffprobe_json(tmp_path) -> None:
    ffprobe = _write_ffprobe_command(
        tmp_path,
        {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "prores",
                    "width": 3840,
                    "height": 2160,
                    "r_frame_rate": "24000/1000",
                    "tags": {"timecode": "01:00:00:00"},
                }
            ],
            "format": {
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                "duration": "12.5",
                "size": "123456",
                "bit_rate": "987654",
            },
        },
    )
    sample = tmp_path / "B001_C001.mov"
    sample.write_bytes(b"quicktime")

    parser = StandardVideoParser(str(ffprobe))
    metadata = parser.parse_metadata(sample)
    integrity = parser.check_integrity(sample)

    assert metadata.format_name == "STANDARD_VIDEO"
    assert metadata.clip_name == "B001_C001"
    assert metadata.metadata["video_codec"] == "prores"
    assert metadata.metadata["width"] == 3840
    assert metadata.metadata["height"] == 2160
    assert metadata.metadata["fps"] == 24.0
    assert metadata.metadata["duration_seconds"] == 12.5
    assert metadata.metadata["size_bytes"] == 123456
    assert metadata.metadata["timecode"] == "01:00:00:00"
    assert integrity.state is IntegrityState.OK


def _write_ffprobe_command(tmp_path, payload: dict[str, object]):
    command = tmp_path / "ffprobe.py"
    command.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        f"print(json.dumps({json.dumps(payload)}))\n"
    )
    command.chmod(0o755)
    return command
