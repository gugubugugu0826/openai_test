import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import incremental_scanner as inc
from desktop_agent.incremental_scanner import (
    filter_new_items,
    load_snapshot,
    save_snapshot,
    scan_incremental_or_full,
)
from desktop_agent.source_manager import Source


def _item(path, name=None):
    return {"path": path, "name": name or Path(path).name}


class SnapshotIOTests(unittest.TestCase):
    def test_load_missing_snapshot_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "downloads_snapshot.json"
            with mock.patch.object(inc, "get_source_snapshot_path", return_value=snap):
                self.assertEqual(load_snapshot("downloads"), {})

    def test_load_corrupt_snapshot_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "downloads_snapshot.json"
            snap.write_text("{ not valid json", encoding="utf-8")
            with mock.patch.object(inc, "get_source_snapshot_path", return_value=snap):
                self.assertEqual(load_snapshot("downloads"), {})

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "downloads_snapshot.json"
            with mock.patch.object(inc, "get_source_snapshot_path", return_value=snap):
                save_snapshot("downloads", [_item(r"D:\a.txt"), _item(r"D:\b.txt")])
                loaded = load_snapshot("downloads")
            self.assertIn(r"D:\a.txt", loaded)
            self.assertIn(r"D:\b.txt", loaded)

    def test_save_preserves_first_seen_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "s.json"
            with mock.patch.object(inc, "get_source_snapshot_path", return_value=snap):
                with mock.patch.object(inc, "now_str", return_value="2020-01-01 00:00:00"):
                    save_snapshot("x", [_item(r"D:\a.txt")])
                first_seen = load_snapshot("x")[r"D:\a.txt"]
                # Re-save with a new timestamp; existing item keeps its first_seen
                with mock.patch.object(inc, "now_str", return_value="2099-12-31 23:59:59"):
                    save_snapshot("x", [_item(r"D:\a.txt"), _item(r"D:\new.txt")])
                reloaded = load_snapshot("x")
            self.assertEqual(reloaded[r"D:\a.txt"], first_seen)
            self.assertEqual(reloaded[r"D:\new.txt"], "2099-12-31 23:59:59")


class FilterNewItemsTests(unittest.TestCase):
    def test_returns_only_unseen(self):
        snapshot = {r"D:\a.txt": "t"}
        current = [_item(r"D:\a.txt"), _item(r"D:\b.txt")]
        new = filter_new_items(current, snapshot)
        self.assertEqual([i["path"] for i in new], [r"D:\b.txt"])

    def test_empty_snapshot_returns_all(self):
        current = [_item(r"D:\a.txt"), _item(r"D:\b.txt")]
        self.assertEqual(len(filter_new_items(current, {})), 2)


class ScanIncrementalOrFullTests(unittest.TestCase):
    def _src(self, mode):
        return Source(id="downloads", label="下载", path=r"D:\Downloads", enabled=True, scan_mode=mode)

    def test_full_mode_returns_all(self):
        items = [_item(r"D:\a.txt"), _item(r"D:\b.txt")]
        result = scan_incremental_or_full(self._src("full"), items)
        self.assertEqual(result, items)

    def test_incremental_first_run_no_snapshot_returns_all(self):
        items = [_item(r"D:\a.txt")]
        with mock.patch.object(inc, "load_snapshot", return_value={}):
            result = scan_incremental_or_full(self._src("incremental"), items)
        self.assertEqual(result, items)

    def test_incremental_with_snapshot_returns_only_new(self):
        items = [_item(r"D:\a.txt"), _item(r"D:\b.txt")]
        with mock.patch.object(inc, "load_snapshot", return_value={r"D:\a.txt": "t"}):
            result = scan_incremental_or_full(self._src("incremental"), items)
        self.assertEqual([i["path"] for i in result], [r"D:\b.txt"])

    def test_incremental_empty_snapshot_falls_back_to_full(self):
        # An empty (or corrupt → {}) snapshot must behave like first run
        items = [_item(r"D:\a.txt"), _item(r"D:\b.txt")]
        with mock.patch.object(inc, "load_snapshot", return_value={}):
            result = scan_incremental_or_full(self._src("incremental"), items)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
