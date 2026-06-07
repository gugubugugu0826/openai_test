import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import workflow
from desktop_agent.suggestion_queue import (
    SuggestionItem,
    append_suggestions,
    load_queue,
)


class WorkflowTempCwd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.getcwd()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._old)
        self._tmp.cleanup()

    def _write_plan(self, items):
        Path("desktop_agent_plan.json").write_text(
            json.dumps({"created_at": "t", "items": items}), encoding="utf-8"
        )


class RunSuggestionWorkflowTests(WorkflowTempCwd):
    def test_converts_plan_items_into_queue(self):
        self._write_plan([
            {"path": r"D:\a.pdf", "name": "a.pdf", "category": "简历求职",
             "classified_by": "rule_file", "reason": "r", "source_id": "desktop"},
            {"path": r"D:\b.txt", "name": "b.txt", "category": "无法判断",
             "classified_by": "no_llm", "reason": "", "source_id": "desktop"},
        ])
        with mock.patch.object(workflow, "scan_all_sources"), \
             mock.patch("desktop_agent.planner.preview_plan"):
            added = workflow.run_suggestion_workflow(silent=True)

        self.assertEqual(added, 2)
        q = load_queue()
        self.assertEqual(len(q.items), 2)
        by_path = {i.path: i for i in q.items}
        self.assertEqual(by_path[r"D:\a.pdf"].confidence, "high")   # rule_* → high
        self.assertEqual(by_path[r"D:\b.txt"].confidence, "low")    # no_llm → low

    def test_missing_plan_returns_zero(self):
        with mock.patch.object(workflow, "scan_all_sources"), \
             mock.patch("desktop_agent.planner.preview_plan"):
            added = workflow.run_suggestion_workflow(silent=True)
        self.assertEqual(added, 0)

    def test_appends_without_duplicating(self):
        self._write_plan([
            {"path": r"D:\a.pdf", "name": "a.pdf", "category": "简历求职",
             "classified_by": "rule_file", "reason": "", "source_id": "desktop"},
        ])
        with mock.patch.object(workflow, "scan_all_sources"), \
             mock.patch("desktop_agent.planner.preview_plan"):
            workflow.run_suggestion_workflow(silent=True)
            workflow.run_suggestion_workflow(silent=True)  # second run, same path
        self.assertEqual(len(load_queue().items), 1)


class ConfirmSuggestionsTests(WorkflowTempCwd):
    def _seed_queue(self):
        a = Path(self._tmp.name) / "a.txt"; a.write_text("x", encoding="utf-8")
        b = Path(self._tmp.name) / "b.txt"; b.write_text("x", encoding="utf-8")
        append_suggestions([
            SuggestionItem("desktop", str(a), "a.txt", "临时文件", "high", "", "t"),
            SuggestionItem("desktop", str(b), "b.txt", "临时文件", "high", "", "t"),
        ])
        return str(a), str(b)

    def test_confirm_all_writes_review_and_clears_queue(self):
        self._seed_queue()
        with mock.patch("desktop_agent.executor.apply_plan") as m_apply:
            workflow.confirm_suggestions(learn=False)
            m_apply.assert_called_once()
        # Review file produced for the executor
        self.assertTrue(Path("desktop_human_review.json").exists())
        review = json.loads(Path("desktop_human_review.json").read_text(encoding="utf-8"))
        self.assertEqual(len(review["items"]), 2)
        # Whole queue cleared when selected_paths is None
        self.assertFalse(Path("suggestion_queue.json").exists())

    def test_confirm_selected_keeps_unselected(self):
        a, b = self._seed_queue()
        with mock.patch("desktop_agent.executor.apply_plan"):
            workflow.confirm_suggestions(selected_paths=[a], learn=False)
        remaining = [i.path for i in load_queue().items]
        self.assertEqual(remaining, [b])

    def test_confirm_empty_queue_does_not_call_apply(self):
        with mock.patch("desktop_agent.executor.apply_plan") as m_apply:
            workflow.confirm_suggestions(learn=False)
            m_apply.assert_not_called()


class AutoRunWorkflowTests(WorkflowTempCwd):
    def test_suggestion_mode_routes_to_suggestion_workflow(self):
        with mock.patch("desktop_agent.config.load_config", return_value={"suggestion_mode": True}), \
             mock.patch.object(workflow, "run_suggestion_workflow") as m_sug, \
             mock.patch.object(workflow, "run_multi_source_workflow") as m_multi:
            workflow.auto_run_workflow(silent=True)
            m_sug.assert_called_once()
            m_multi.assert_not_called()

    def test_normal_mode_routes_to_multi_source_workflow(self):
        with mock.patch("desktop_agent.config.load_config", return_value={"suggestion_mode": False}), \
             mock.patch.object(workflow, "run_suggestion_workflow") as m_sug, \
             mock.patch.object(workflow, "run_multi_source_workflow") as m_multi:
            workflow.auto_run_workflow(silent=True)
            m_multi.assert_called_once()
            m_sug.assert_not_called()


if __name__ == "__main__":
    unittest.main()
