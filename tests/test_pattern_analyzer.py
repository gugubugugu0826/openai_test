import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import pattern_analyzer as pa
from desktop_agent import memory as memory_module
from desktop_agent.pattern_analyzer import (
    RuleSuggestion,
    accept_suggestion,
    analyze_correction_history,
)


def _review(items):
    return {"created_at": "2026-01-01 00:00:00", "items": items}


def _corr(name, ai, human, enabled=True):
    return {"name": name, "ai_category": ai, "human_category": human, "enabled": enabled}


class AnalyzeCorrectionHistoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.hist = Path(self._tmp.name) / "history"
        self.hist.mkdir()
        self.mem = Path(self._tmp.name) / "memory.json"
        self.mem.write_text(json.dumps({"rules": []}), encoding="utf-8")
        self._p1 = mock.patch.object(pa, "HISTORY_DIR", str(self.hist))
        self._p2 = mock.patch.object(memory_module, "MEMORY_FILE", str(self.mem))
        self._p1.start()
        self._p2.start()

    def tearDown(self):
        self._p1.stop()
        self._p2.stop()
        self._tmp.cleanup()

    def _write_review(self, idx, items):
        (self.hist / f"review_{idx}.json").write_text(json.dumps(_review(items)), encoding="utf-8")

    def test_empty_history_returns_no_suggestions(self):
        self.assertEqual(analyze_correction_history(), [])

    def test_single_correction_below_threshold_ignored(self):
        self._write_review(1, [_corr("myresume.pdf", "无法判断", "简历求职")])
        self.assertEqual(analyze_correction_history(), [])

    def test_repeated_correction_reaches_threshold(self):
        self._write_review(1, [_corr("myresume.pdf", "无法判断", "简历求职")])
        self._write_review(2, [_corr("myresume.pdf", "无法判断", "简历求职")])
        suggestions = analyze_correction_history()
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].to_category, "简历求职")
        self.assertEqual(suggestions[0].count, 2)

    def test_correction_already_in_memory_is_skipped(self):
        self.mem.write_text(json.dumps({"rules": [{"match": "myresume", "category": "简历求职"}]}), encoding="utf-8")
        self._write_review(1, [_corr("myresume.pdf", "无法判断", "简历求职")])
        self._write_review(2, [_corr("myresume.pdf", "无法判断", "简历求职")])
        self.assertEqual(analyze_correction_history(), [])

    def test_unchanged_category_not_counted(self):
        self._write_review(1, [_corr("report.pdf", "作业报告", "作业报告")])
        self._write_review(2, [_corr("report.pdf", "作业报告", "作业报告")])
        self.assertEqual(analyze_correction_history(), [])

    def test_invalid_human_category_ignored(self):
        self._write_review(1, [_corr("thing.pdf", "无法判断", "不存在的分类")])
        self._write_review(2, [_corr("thing.pdf", "无法判断", "不存在的分类")])
        self.assertEqual(analyze_correction_history(), [])

    def test_short_match_text_ignored(self):
        # stem "ab" < 3 chars
        self._write_review(1, [_corr("ab.pdf", "无法判断", "简历求职")])
        self._write_review(2, [_corr("ab.pdf", "无法判断", "简历求职")])
        self.assertEqual(analyze_correction_history(), [])

    def test_disabled_items_ignored(self):
        self._write_review(1, [_corr("myresume.pdf", "无法判断", "简历求职", enabled=False)])
        self._write_review(2, [_corr("myresume.pdf", "无法判断", "简历求职", enabled=False)])
        self.assertEqual(analyze_correction_history(), [])

    def test_suggestions_sorted_by_count_desc(self):
        for i in range(1, 4):  # "alpha" corrected 3x
            self._write_review(f"a{i}", [_corr("alphafile.pdf", "无法判断", "简历求职")])
        for i in range(1, 3):  # "beta" corrected 2x
            self._write_review(f"b{i}", [_corr("betafile.pdf", "无法判断", "课程资料")])
        suggestions = analyze_correction_history()
        self.assertEqual(len(suggestions), 2)
        self.assertGreaterEqual(suggestions[0].count, suggestions[1].count)


class AcceptSuggestionTests(unittest.TestCase):
    def test_accept_writes_rule_to_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "memory.json"
            with mock.patch.object(memory_module, "MEMORY_FILE", str(mem)):
                sug = RuleSuggestion(
                    match="myresume", from_category="无法判断",
                    to_category="简历求职", count=3, suggestion_text="x",
                )
                self.assertTrue(accept_suggestion(sug))
                data = json.loads(mem.read_text(encoding="utf-8"))
            matches = [(r["match"], r["category"]) for r in data["rules"]]
            self.assertIn(("myresume", "简历求职"), matches)


if __name__ == "__main__":
    unittest.main()
