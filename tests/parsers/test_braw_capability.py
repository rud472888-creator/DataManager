import json

import pytest

from app.parsers.braw_parser import BrawAdapter, BrawUnavailableError, MockBrawParser
from app.parsers.registry import default_registry
from app.parsers.types import CapabilityState, IntegrityState


def test_real_braw_adapter_defaults_to_truthful_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("FDM_BRAW_METADATA_COMMAND", raising=False)
    adapter = BrawAdapter.from_environment()

    capabilities = adapter.capabilities()
    check = adapter.check_capability()

    assert capabilities.metadata is CapabilityState.UNAVAILABLE
    assert "not configured" in capabilities.reason
    assert check.capabilities.metadata is CapabilityState.UNAVAILABLE


def test_real_braw_adapter_does_not_fake_metadata(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("FDM_BRAW_METADATA_COMMAND", raising=False)
    sample = tmp_path / "A001_C001.braw"
    sample.write_bytes(b"not real braw")

    with pytest.raises(BrawUnavailableError, match="not configured"):
        BrawAdapter.from_environment().parse_metadata(sample)


def test_mock_braw_parser_is_explicit_and_deterministic(tmp_path) -> None:
    parser = MockBrawParser()
    sample = tmp_path / "A001_C001.braw"
    sample.write_bytes(b"mock")

    metadata = parser.parse_metadata(sample)
    integrity = parser.check_integrity(sample)

    assert parser.capabilities().is_mock is True
    assert metadata.is_mock is True
    assert metadata.metadata["mock"] is True
    assert integrity.state is IntegrityState.OK


def test_registry_keeps_mock_opt_in() -> None:
    production = default_registry()
    test_registry = default_registry(include_mock=True)

    assert production.by_format("BRAW") is not None
    assert production.by_format("R3D") is not None
    assert production.by_format("ARRIRAW") is not None
    assert production.by_format("STANDARD_VIDEO") is not None
    assert production.by_format("BRAW_MOCK") is None
    assert test_registry.by_format("BRAW_MOCK") is not None


def test_future_format_adapters_are_truthfully_unavailable(tmp_path) -> None:
    registry = default_registry()
    r3d = registry.by_format("R3D")
    arriraw = registry.by_format("ARRIRAW")
    standard_video = registry.by_format("STANDARD_VIDEO")
    r3d_sample = tmp_path / "R001_C001.r3d"
    arri_sample = tmp_path / "ALEXA_C001.ari"
    mov_sample = tmp_path / "B001_C001.mov"
    mp4_sample = tmp_path / "B001_C002.mp4"
    r3d_sample.write_bytes(b"red")
    arri_sample.write_bytes(b"arri")
    mov_sample.write_bytes(b"quicktime")
    mp4_sample.write_bytes(b"mpeg-4")

    assert r3d is not None
    assert arriraw is not None
    assert standard_video is not None
    assert r3d.probe(r3d_sample).supported is True
    assert arriraw.probe(arri_sample).supported is True
    assert arriraw.probe(tmp_path / "ALEXA_C002.mxf").supported is True
    assert standard_video.probe(mov_sample).supported is True
    assert standard_video.probe(mp4_sample).supported is True
    assert r3d.capabilities().metadata is CapabilityState.UNAVAILABLE
    assert arriraw.capabilities().metadata is CapabilityState.UNAVAILABLE


def test_adapter_can_report_partial_when_command_configured(monkeypatch) -> None:
    monkeypatch.setenv("FDM_BRAW_METADATA_COMMAND", "/bin/echo")

    capabilities = BrawAdapter.from_environment().capabilities()

    assert capabilities.metadata is CapabilityState.PARTIAL


def test_adapter_accepts_real_command_json(tmp_path) -> None:
    command = tmp_path / "metadata_command.py"
    command.write_text(
        "#!/usr/bin/env python3\n"
        "import json; print(json.dumps({'camera': 'Real-ish Adapter Test', 'fps': 24.0}))\n"
    )
    command.chmod(0o755)
    sample = tmp_path / "A001_C001.braw"
    sample.write_bytes(b"sample")

    check = BrawAdapter(str(command)).check_capability(sample)

    assert check.capabilities.metadata is CapabilityState.AVAILABLE
    assert check.metadata is not None
    assert check.metadata.is_mock is False
    assert "frames" not in json.loads(json.dumps(check.as_dict()))
