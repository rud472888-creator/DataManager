from __future__ import annotations

from app.parsers.braw_parser import BrawParser
from app.parsers.base import BaseParser


def get_registered_parsers() -> list[BaseParser]:
    return [BrawParser()]
