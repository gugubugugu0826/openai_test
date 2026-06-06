import tempfile
import unittest
from pathlib import Path

from desktop_agent.storage import json_exists, load_json, save_json


class StorageTests(unittest.TestCase):
    def test_save_and_load_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.json"
            payload = {"name": "demo", "count": 3, "items": [1, 2, 3]}

            save_json(path, payload)

            self.assertTrue(path.exists())
            self.assertEqual(load_json(path), payload)

    def test_json_exists_reflects_file_presence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exists.json"
            self.assertFalse(json_exists(path))
            save_json(path, {"ok": True})
            self.assertTrue(json_exists(path))
