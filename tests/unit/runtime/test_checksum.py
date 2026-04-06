from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from app.runtime.checksum import sha256_file


class ChecksumTests(unittest.IsolatedAsyncioTestCase):
    async def test_sha256_file_matches_hashlib(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "clip.braw"
            payload = b"frame-data" * 128
            path.write_bytes(payload)

            digest = await sha256_file(path)

            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
