"""Shared parser exceptions."""

from __future__ import annotations


class ParserUnavailableError(RuntimeError):
    """Raised when parser behavior is requested but unavailable."""
