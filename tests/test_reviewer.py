import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import reviewer as reviewer_module
from desktop_agent.reviewer import create_human_review, learn_from_review
from desktop_agent.categories import CATEGORIES


SAMPLE_PLAN = {
    "created_at": "2026-01-01",
    "source_observation": "desktop_observation.json",
    "items": [
        {
            "path": r"C:\Desktop\Steam.lnk",
            "name": "Steam.lnk",
            "type": "shortcut",
            "category": "游戏相关",
            "reason": "rule match",
            "classified_by": "rule",
        },
        {
            "path": r"C:\Desktop\resume.pdf",
            "name": "resume.pdf",
            "type": "file",
            "category": "简历求职",
            "reason": "rule match",
            "classified_by": "rule",
            "desktop_root": r"C:\Desktop",
        },
    ]
}


class CreateHumanReviewTests(unittest.TestCase):
    def test_creates_review_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(SAMPLE_PLAN), encoding="utf-8")
            review_path = Path(tmp) / "review.json"

            with mock.patch.object(reviewer_module, "PLAN_FILE", str(plan_path)), \
                 mock.patch.object(reviewer_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch("desktop_agent.reviewer.update_state"):
                create_human_review()

            self.assertTrue(review_path.exists())
            review = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual(len(review["items"]), 2)

    def test_review_items_have_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(SAMPLE_PLAN), encoding="utf-8")
            review_path = Path(tmp) / "review.json"

            with mock.patch.object(reviewer_module, "PLAN_FILE", str(plan_path)), \
                 mock.patch.object(reviewer_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch("desktop_agent.reviewer.update_state"):
                create_human_review()

            review = json.loads(review_path.read_text(encoding="utf-8"))
            for item in review["items"]:
                self.assertIn("enabled", item)
                self.assertIn("path", item)
                self.assertIn("ai_category", item)
                self.assertIn("human_category", item)
                self.assertTrue(item["enabled"])

    def test_review_preserves_desktop_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(SAMPLE_PLAN), encoding="utf-8")
            review_path = Path(tmp) / "review.json"

            with mock.patch.object(reviewer_module, "PLAN_FILE", str(plan_path)), \
                 mock.patch.object(reviewer_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch("desktop_agent.reviewer.update_state"):
                create_human_review()

            review = json.loads(review_path.read_text(encoding="utf-8"))
            resume_item = next(i for i in review["items"] if i["name"] == "resume.pdf")
            self.assertEqual(resume_item.get("desktop_root"), r"C:\Desktop")

    def test_missing_plan_prints_hint_and_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_plan = Path(tmp) / "plan.json"
            with mock.patch.object(reviewer_module, "PLAN_FILE", str(missing_plan)):
                import io
                from contextlib import redirect_stdout
                out = io.StringIO()
                with redirect_stdout(out):
                    create_human_review()
                self.assertIn("找不到", out.getvalue())

    def test_ai_category_and_human_category_initially_equal(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(SAMPLE_PLAN), encoding="utf-8")
            review_path = Path(tmp) / "review.json"

            with mock.patch.object(reviewer_module, "PLAN_FILE", str(plan_path)), \
                 mock.patch.object(reviewer_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch("desktop_agent.reviewer.update_state"):
                create_human_review()

            review = json.loads(review_path.read_text(encoding="utf-8"))
            for item in review["items"]:
                self.assertEqual(item["ai_category"], item["human_category"])


class LearnFromReviewTests(unittest.TestCase):
    def _make_review(self, tmp, items):
        review_path = Path(tmp) / "review.json"
        review_data = {"items": items}
        review_path.write_text(json.dumps(review_data), encoding="utf-8")
        return review_path

    def test_learns_when_human_changes_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory_path = Path(tmp) / "memory.json"
            review_path = self._make_review(tmp, [
                {
                    "enabled": True,
                    "name": "lecture_notes.pdf",
                    "type": "file",
                    "ai_category": "无法判断",
                    "human_category": "课程资料",
                    "path": r"C:\Desktop\lecture_notes.pdf",
                }
            ])

            with mock.patch.object(reviewer_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch("desktop_agent.reviewer.load_memory", return_value={"rules": []}), \
                 mock.patch("desktop_agent.reviewer.save_memory") as mock_save_mem, \
                 mock.patch("desktop_agent.reviewer.update_state"):
                learn_from_review()
                saved_memory = mock_save_mem.call_args[0][0]
                self.assertEqual(len(saved_memory["rules"]), 1)
                self.assertEqual(saved_memory["rules"][0]["category"], "课程资料")

    def test_skips_when_category_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = self._make_review(tmp, [
                {
                    "enabled": True,
                    "name": "Steam.lnk",
                    "type": "shortcut",
                    "ai_category": "游戏相关",
                    "human_category": "游戏相关",
                    "path": r"C:\Desktop\Steam.lnk",
                }
            ])
            with mock.patch.object(reviewer_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch("desktop_agent.reviewer.load_memory", return_value={"rules": []}), \
                 mock.patch("desktop_agent.reviewer.save_memory") as mock_save_mem, \
                 mock.patch("desktop_agent.reviewer.update_state"):
                learn_from_review()
                saved_memory = mock_save_mem.call_args[0][0]
                self.assertEqual(len(saved_memory["rules"]), 0)

    def test_skips_invalid_human_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = self._make_review(tmp, [
                {
                    "enabled": True,
                    "name": "some_file.txt",
                    "type": "file",
                    "ai_category": "无法判断",
                    "human_category": "非法分类XYZ",
                    "path": r"C:\Desktop\some_file.txt",
                }
            ])
            with mock.patch.object(reviewer_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch("desktop_agent.reviewer.load_memory", return_value={"rules": []}), \
                 mock.patch("desktop_agent.reviewer.save_memory") as mock_save_mem, \
                 mock.patch("desktop_agent.reviewer.update_state"):
                learn_from_review()
                saved_memory = mock_save_mem.call_args[0][0]
                self.assertEqual(len(saved_memory["rules"]), 0)

    def test_skips_disabled_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = self._make_review(tmp, [
                {
                    "enabled": False,
                    "name": "lecture.pdf",
                    "type": "file",
                    "ai_category": "无法判断",
                    "human_category": "课程资料",
                    "path": r"C:\Desktop\lecture.pdf",
                }
            ])
            with mock.patch.object(reviewer_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch("desktop_agent.reviewer.load_memory", return_value={"rules": []}), \
                 mock.patch("desktop_agent.reviewer.save_memory") as mock_save_mem, \
                 mock.patch("desktop_agent.reviewer.update_state"):
                learn_from_review()
                saved_memory = mock_save_mem.call_args[0][0]
                self.assertEqual(len(saved_memory["rules"]), 0)

    def test_skips_short_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = self._make_review(tmp, [
                {
                    "enabled": True,
                    "name": "ab.txt",
                    "type": "file",
                    "ai_category": "无法判断",
                    "human_category": "课程资料",
                    "path": r"C:\Desktop\ab.txt",
                }
            ])
            with mock.patch.object(reviewer_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch("desktop_agent.reviewer.load_memory", return_value={"rules": []}), \
                 mock.patch("desktop_agent.reviewer.save_memory") as mock_save_mem, \
                 mock.patch("desktop_agent.reviewer.update_state"):
                learn_from_review()
                saved_memory = mock_save_mem.call_args[0][0]
                self.assertEqual(len(saved_memory["rules"]), 0)

    def test_no_duplicate_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing_rules = [{"match": "lecture_notes", "category": "课程资料", "note": "existing"}]
            review_path = self._make_review(tmp, [
                {
                    "enabled": True,
                    "name": "lecture_notes.pdf",
                    "type": "file",
                    "ai_category": "无法判断",
                    "human_category": "课程资料",
                    "path": r"C:\Desktop\lecture_notes.pdf",
                }
            ])
            with mock.patch.object(reviewer_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch("desktop_agent.reviewer.load_memory", return_value={"rules": existing_rules}), \
                 mock.patch("desktop_agent.reviewer.save_memory") as mock_save_mem, \
                 mock.patch("desktop_agent.reviewer.update_state"):
                learn_from_review()
                saved_memory = mock_save_mem.call_args[0][0]
                self.assertEqual(len(saved_memory["rules"]), 1)

    def test_missing_review_prints_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_review = Path(tmp) / "review.json"
            with mock.patch.object(reviewer_module, "REVIEW_FILE", str(missing_review)):
                import io
                from contextlib import redirect_stdout
                out = io.StringIO()
                with redirect_stdout(out):
                    learn_from_review()
                self.assertIn("找不到", out.getvalue())
