import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import scanner as scanner_module


class ScanAllSourcesTests(unittest.TestCase):
    def _config(self, sources, tmp):
        return {
            "max_internal_items_per_folder": 200,
            "sources": sources,
            "_desktop_path_was_empty": False,
        }

    def test_merges_items_from_multiple_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            d1 = Path(tmp) / "src1" / "sub"; d1.mkdir(parents=True)
            d2 = Path(tmp) / "src2" / "sub"; d2.mkdir(parents=True)
            (d1 / "one.txt").write_text("1", encoding="utf-8")
            (d2 / "two.txt").write_text("2", encoding="utf-8")

            config = self._config([
                {"id": "s1", "label": "S1", "path": str(d1), "enabled": True, "scan_mode": "full"},
                {"id": "s2", "label": "S2", "path": str(d2), "enabled": True, "scan_mode": "full"},
            ], tmp)

            with mock.patch.object(scanner_module, "load_config", return_value=config), \
                 mock.patch.object(scanner_module, "save_json"), \
                 mock.patch.object(scanner_module, "update_state"):
                obs = scanner_module.scan_all_sources()

            names = sorted(i["name"] for i in obs["items"])
            self.assertEqual(names, ["one.txt", "two.txt"])
            self.assertEqual(sorted(obs["sources_scanned"]), ["s1", "s2"])

    def test_deduplicates_when_two_sources_point_to_same_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "shared" / "sub"; shared.mkdir(parents=True)
            (shared / "dup.txt").write_text("x", encoding="utf-8")

            config = self._config([
                {"id": "a", "label": "A", "path": str(shared), "enabled": True, "scan_mode": "full"},
                {"id": "b", "label": "B", "path": str(shared), "enabled": True, "scan_mode": "full"},
            ], tmp)

            with mock.patch.object(scanner_module, "load_config", return_value=config), \
                 mock.patch.object(scanner_module, "save_json"), \
                 mock.patch.object(scanner_module, "update_state"):
                obs = scanner_module.scan_all_sources()

            dup_items = [i for i in obs["items"] if i["name"] == "dup.txt"]
            self.assertEqual(len(dup_items), 1)

    def test_invalid_source_path_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good" / "sub"; good.mkdir(parents=True)
            (good / "g.txt").write_text("g", encoding="utf-8")

            config = self._config([
                {"id": "good", "label": "G", "path": str(good), "enabled": True, "scan_mode": "full"},
                {"id": "bad", "label": "B", "path": r"C:\Nope\Missing\xyz", "enabled": True, "scan_mode": "full"},
            ], tmp)

            with mock.patch.object(scanner_module, "load_config", return_value=config), \
                 mock.patch.object(scanner_module, "save_json"), \
                 mock.patch.object(scanner_module, "update_state"):
                obs = scanner_module.scan_all_sources()

            self.assertEqual(obs["sources_scanned"], ["good"])
            self.assertEqual([i["name"] for i in obs["items"]], ["g.txt"])

    def test_no_enabled_sources_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config([
                {"id": "a", "label": "A", "path": str(tmp), "enabled": False, "scan_mode": "full"},
            ], tmp)
            with mock.patch.object(scanner_module, "load_config", return_value=config):
                obs = scanner_module.scan_all_sources()
            self.assertEqual(obs, {})


if __name__ == "__main__":
    unittest.main()
