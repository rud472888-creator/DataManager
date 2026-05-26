"""Runtime parser registry."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.parsers.base import Parser
from app.parsers.braw_parser import BrawAdapter, MockBrawParser
from app.parsers.unavailable import (
    arriraw_unavailable_parser,
    r3d_unavailable_parser,
)
from app.parsers.standard_video_parser import StandardVideoParser


@dataclass
class ParserRegistry:
    """Simple in-process registry for runtime parser adapters."""

    parsers: list[Parser] = field(default_factory=list)

    def register(self, parser: Parser) -> None:
        self.parsers.append(parser)

    def by_format(self, format_name: str) -> Parser | None:
        for parser in self.parsers:
            if parser.get_format_name().lower() == format_name.lower():
                return parser
        return None

    def all(self) -> list[Parser]:
        return list(self.parsers)


def default_registry(*, include_mock: bool = False) -> ParserRegistry:
    """Build the runtime parser registry.

    Mock parsers are opt-in so tests cannot accidentally claim real BRAW support.
    """

    registry = ParserRegistry()
    registry.register(BrawAdapter.from_environment())
    registry.register(r3d_unavailable_parser())
    registry.register(arriraw_unavailable_parser())
    registry.register(StandardVideoParser.from_environment())
    if include_mock:
        registry.register(MockBrawParser())
    return registry


def registered_parsers() -> list[Parser]:
    """Return production runtime parser plugins."""

    return default_registry().all()
