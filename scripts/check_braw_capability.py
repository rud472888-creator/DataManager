#!/usr/bin/env python3
"""Print truthful BRAW parser capability status as JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.parsers.braw_parser import BrawAdapter


def main() -> None:
    sample = os.getenv("BRAW_SAMPLE")
    sample_path = Path(sample) if sample else None
    check = BrawAdapter.from_environment().check_capability(sample_path)
    print(json.dumps(check.as_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
