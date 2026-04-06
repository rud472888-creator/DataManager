from __future__ import annotations

import unittest
from pathlib import Path


class WebConsoleFilesystemSafetyTests(unittest.TestCase):
    def test_web_console_contains_no_direct_filesystem_access_calls(self) -> None:
        web_dir = Path(__file__).resolve().parents[2] / "app" / "web_console"
        forbidden_tokens = [
            "showOpenFilePicker",
            "showDirectoryPicker",
            "window.__TAURI__",
            "require('fs')",
            'require("fs")',
            "node:fs",
            "fileSystem",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in web_dir.iterdir() if path.is_file())
        for token in forbidden_tokens:
            self.assertNotIn(token, combined)
