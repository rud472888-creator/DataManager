#!/usr/bin/env sh
set -eu

.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python scripts/apply_migrations.py
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest -q
.venv/bin/python scripts/check_braw_capability.py
.venv/bin/python -m build
