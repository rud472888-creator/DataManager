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

    def test_web_console_declares_remote_only_contracts(self) -> None:
        web_dir = Path(__file__).resolve().parents[2] / "app" / "web_console"
        index_html = (web_dir / "index.html").read_text(encoding="utf-8")
        app_js = (web_dir / "app.js").read_text(encoding="utf-8")
        api_js = (web_dir / "api.js").read_text(encoding="utf-8")
        combined = "\n".join([index_html, app_js, api_js])

        self.assertIn("remote control and monitoring shell only", index_html)
        self.assertIn("The runtime does the real filesystem and media work.", index_html)
        self.assertIn("browser never browses local disks", index_html)
        self.assertIn("/api/runtime/status", combined)
        self.assertIn("/api/volumes", combined)
        self.assertIn("/api/jobs", combined)
        self.assertIn("/ws/events", combined)
        self.assertIn('operator_origin: "remote_web"', api_js)
