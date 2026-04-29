#!/usr/bin/env python3
"""Print clone pipeline capability status as JSON."""

from __future__ import annotations

import json

from app.runtime.media_formats import supported_format_names, supported_suffixes


def main() -> None:
    payload = {
        "checksum": "available",
        "reports": ["checksum_pdf", "manifest_json"],
        "supported_offload_formats": supported_format_names(),
        "supported_offload_suffixes": supported_suffixes(),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
