import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import suggestion_queue as sq
from desktop_agent.suggestion_queue import (
    SuggestionItem,
    append_suggestions,
    clear_queue,
    get_pending_count,
    load_queue,
    plan_items_from_queue,
    save_queue,
    validate_queue,
)


def _mk_item(path, name=None, category="临时文件", enabled=True, human=""):
    return SuggestionItem(
        source_id="desktop",
        path=path,
        name=name or Path(path).name,
        suggested_category=category,
        confidence="medium",
        reason="r",
        scanned_at="2026-01-01 00:00:00",
        enabled=enabled,
        human_category=human,
    )


class QueueTestBase(unittest.TestCase):
    """Each test runs in an isolated temp cwd so QUEUE_FILE is sandboxed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.getcwd()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._old)
        self._tmp.cleanup()


class LoadQueueTests(QueueTestBase):
    def test_missing_file_returns_empty_queue(self):
        q = load_queue()
        self.assertEqual(q.items, [])
        self.assertTrue(q.accumulated_since)

    def test_corrupt_file_returns_empty_queue(self):
        Path(sq.QUEUE_FILE).write_text("{ broken", encoding="utf-8")
        q = load_queue()  # must NOT raise
        self.assertEqual(q.items, [])


class AppendSuggestionsTests(QueueTestBase):
    def test_append_adds_items(self):
        q = append_suggestions([_mk_item(r"D:\a.txt"), _mk_item(r"D:\b.txt")])
        self.assertEqual(len(q.items), 2)

    def test_append_dedups_existing_paths(self):
        append_suggestions([_mk_item(r"D:\a.txt")])
        q = append_suggestions([_mk_item(r"D:\a.txt"), _mk_item(r"D:\b.txt")])
        paths = sorted(i.path for i in q.items)
        self.assertEqual(paths, [r"D:\a.txt", r"D:\b.txt"])

    def test_pending_count_counts_enabled_only(self):
        append_suggestions([_mk_item(r"D:\a.txt", enabled=True), _mk_item(r"D:\b.txt", enabled=False)])
        self.assertEqual(get_pending_count(), 1)


class ValidateQueueTests(QueueTestBase):
    def test_removes_items_whose_path_is_gone(self):
        real = Path(self._tmp.name) / "real.txt"
        real.write_text("x", encoding="utf-8")
        append_suggestions([_mk_item(str(real)), _mk_item(r"D:\ghost\missing.txt")])
        q = validate_queue()
        self.assertEqual([i.path for i in q.items], [str(real)])


class PlanItemsTests(QueueTestBase):
    def test_plan_items_use_human_category_override(self):
        real = Path(self._tmp.name) / "resume.pdf"
        real.write_text("x", encoding="utf-8")
        append_suggestions([_mk_item(str(real), category="无法判断", human="简历求职")])
        items = plan_items_from_queue()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["category"], "简历求职")
        self.assertEqual(items[0]["classified_by"], "suggestion_confirmed")

    def test_plan_items_skip_disabled(self):
        real = Path(self._tmp.name) / "f.txt"
        real.write_text("x", encoding="utf-8")
        append_suggestions([_mk_item(str(real), enabled=False)])
        self.assertEqual(plan_items_from_queue(), [])

    def test_plan_items_respect_selected_paths(self):
        a = Path(self._tmp.name) / "a.txt"; a.write_text("x", encoding="utf-8")
        b = Path(self._tmp.name) / "b.txt"; b.write_text("x", encoding="utf-8")
        append_suggestions([_mk_item(str(a)), _mk_item(str(b))])
        items = plan_items_from_queue(selected_paths=[str(a)])
        self.assertEqual([i["path"] for i in items], [str(a)])


class ClearQueueTests(QueueTestBase):
    def test_clear_removes_file(self):
        append_suggestions([_mk_item(r"D:\a.txt")])
        self.assertTrue(Path(sq.QUEUE_FILE).exists())
        clear_queue()
        self.assertFalse(Path(sq.QUEUE_FILE).exists())

    def test_clear_when_missing_is_noop(self):
        clear_queue()  # must not raise
        self.assertFalse(Path(sq.QUEUE_FILE).exists())


class SaveQueueTests(QueueTestBase):
    def test_save_recomputes_pending_count(self):
        from desktop_agent.suggestion_queue import SuggestionQueue
        q = SuggestionQueue(items=[_mk_item(r"D:\a.txt", enabled=True), _mk_item(r"D:\b.txt", enabled=False)])
        save_queue(q)
        on_disk = json.loads(Path(sq.QUEUE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(on_disk["pending_count"], 1)


if __name__ == "__main__":
    unittest.main()
