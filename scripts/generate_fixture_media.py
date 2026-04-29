#!/usr/bin/env python3
"""Generate tiny local fixture media directories for tests and manual smoke runs."""

from __future__ import annotations

from pathlib import Path


def create_fixture_tree(root: Path) -> None:
    source = root / "source" / "A001"
    main = root / "main"
    backup = root / "backup"
    for directory in (source, main, backup):
        directory.mkdir(parents=True, exist_ok=True)
    (source / "A001_C001.braw").write_bytes(b"fake-braw-foundation-fixture\n")
    (source / "A001_C002.braw").write_bytes(b"fake-braw-foundation-fixture-2\n")


def main() -> None:
    root = Path(".fdm_fixtures")
    create_fixture_tree(root)
    print(f"Created fixture media tree at {root}")


if __name__ == "__main__":
    main()
