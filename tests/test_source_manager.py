import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import source_manager as sm
from desktop_agent.source_manager import (
    Source,
    get_enabled_sources,
    get_source_snapshot_path,
    load_sources,
    validate_source_path,
)


class SourceDataclassTests(unittest.TestCase):
    def test_resolved_path_uses_explicit_path(self):
        s = Source(id="x", label="X", path=r"D:\Stuff", enabled=True, scan_mode="full")
        self.assertEqual(s.resolved_path, Path(r"D:\Stuff"))

    def test_resolved_path_desktop_default(self):
        s = Source(id="desktop", label="桌面", path="", enabled=True, scan_mode="full")
        self.assertEqual(s.resolved_path, Path.home() / "Desktop")

    def test_resolved_path_downloads_default(self):
        s = Source(id="downloads", label="下载", path="", enabled=True, scan_mode="incremental")
        self.assertEqual(s.resolved_path, Path.home() / "Downloads")

    def test_resolved_path_documents_default(self):
        s = Source(id="documents", label="文档", path="", enabled=True, scan_mode="incremental")
        self.assertEqual(s.resolved_path, Path.home() / "Documents")

    def test_as_dict_includes_core_fields_and_extra(self):
        s = Source(id="x", label="X", path="", enabled=False, scan_mode="full", extra={"foo": "bar"})
        d = s.as_dict()
        self.assertEqual(d["id"], "x")
        self.assertEqual(d["scan_mode"], "full")
        self.assertEqual(d["foo"], "bar")


class LoadSourcesTests(unittest.TestCase):
    def test_load_sources_parses_config(self):
        config = {
            "sources": [
                {"id": "desktop", "label": "桌面", "path": "", "enabled": True, "scan_mode": "full"},
                {"id": "downloads", "label": "下载", "path": "D:/D", "enabled": False, "scan_mode": "incremental"},
            ]
        }
        sources = load_sources(config)
        self.assertEqual(len(sources), 2)
        self.assertIsInstance(sources[0], Source)
        self.assertEqual(sources[0].id, "desktop")
        self.assertFalse(sources[1].enabled)

    def test_load_sources_defaults_scan_mode_full(self):
        config = {"sources": [{"id": "x", "label": "X", "path": "D:/X", "enabled": True}]}
        sources = load_sources(config)
        self.assertEqual(sources[0].scan_mode, "full")

    def test_get_enabled_sources_filters_disabled(self):
        config = {
            "sources": [
                {"id": "a", "label": "A", "path": "D:/A", "enabled": True, "scan_mode": "full"},
                {"id": "b", "label": "B", "path": "D:/B", "enabled": False, "scan_mode": "full"},
            ]
        }
        enabled = get_enabled_sources(config)
        self.assertEqual([s.id for s in enabled], ["a"])

    def test_unknown_keys_go_into_extra(self):
        config = {"sources": [{"id": "x", "label": "X", "path": "D:/X", "enabled": True, "scan_mode": "full", "custom": 1}]}
        sources = load_sources(config)
        self.assertEqual(sources[0].extra.get("custom"), 1)


class ValidateSourcePathTests(unittest.TestCase):
    def test_empty_path_rejected(self):
        self.assertFalse(validate_source_path(""))
        self.assertFalse(validate_source_path("   "))

    def test_nonexistent_path_rejected(self):
        self.assertFalse(validate_source_path(r"C:\This\Does\Not\Exist\xyz123"))

    def test_drive_root_rejected(self):
        # Use whichever drive the temp dir lives on so the test is portable
        with tempfile.TemporaryDirectory() as tmp:
            drive = Path(tmp).anchor  # e.g. "C:\\"
        self.assertFalse(validate_source_path(drive))

    def test_home_directory_rejected(self):
        self.assertFalse(validate_source_path(str(Path.home())))

    def test_file_instead_of_dir_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "file.txt"
            f.write_text("x", encoding="utf-8")
            self.assertFalse(validate_source_path(str(f)))

    def test_valid_deep_directory_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            deep = Path(tmp) / "a" / "b" / "c"
            deep.mkdir(parents=True)
            self.assertTrue(validate_source_path(str(deep)))


class SnapshotPathTests(unittest.TestCase):
    def test_snapshot_path_under_snapshots_dir(self):
        p = get_source_snapshot_path("downloads")
        self.assertEqual(p, Path("snapshots") / "downloads_snapshot.json")


class SaveSourcesTests(unittest.TestCase):
    def test_save_sources_writes_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(json.dumps({"existing": 1}), encoding="utf-8")
            sources = [Source(id="desktop", label="桌面", path="", enabled=True, scan_mode="full")]
            # save_sources hardcodes Path("config.json"); run inside tmp cwd
            import os
            old = os.getcwd()
            os.chdir(tmp)
            try:
                sm.save_sources(sources)
                written = json.loads(Path("config.json").read_text(encoding="utf-8"))
            finally:
                os.chdir(old)
            self.assertIn("sources", written)
            self.assertEqual(written["sources"][0]["id"], "desktop")
            self.assertEqual(written["existing"], 1)


if __name__ == "__main__":
    unittest.main()
