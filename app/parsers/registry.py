from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.parsers.braw_parser import BrawParser
from app.parsers.base import BaseParser


def get_registered_parsers() -> list[BaseParser]:
    return [BrawParser()]


def select_parser(file_path: Path, parsers: Iterable[BaseParser] | None = None) -> BaseParser | None:
    candidates = list(parsers or get_registered_parsers())
    best_match: tuple[float, BaseParser] | None = None
    for parser in candidates:
        probe = parser.probe(file_path)
        if not probe.supported:
            continue
        if best_match is None or probe.confidence > best_match[0]:
            best_match = (probe.confidence, parser)
    return best_match[1] if best_match is not None else None
