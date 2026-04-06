from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.parsers.types import ParserCapabilities, ProbeResult


class BaseParser(ABC):
    @abstractmethod
    def probe(self, file_path: Path) -> ProbeResult:
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> ParserCapabilities:
        raise NotImplementedError

    @abstractmethod
    def parse_metadata(self, file_path: Path) -> dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def check_integrity(self, file_path: Path) -> dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def capture_frames(self, file_path: Path, indices: list[int]) -> list[Path]:
        raise NotImplementedError

    @abstractmethod
    def get_format_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_version(self) -> str:
        raise NotImplementedError
