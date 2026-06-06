import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import plan_explainer as pe_module
from desktop_agent.plan_explainer import (
    build_plan_explanation,
    get_item_category,
    get_item_enabled,
    render_markdown,
    load_plan_items,
)


SAMPLE_ITEMS = [
    {
        "path": r"C:\Desktop\Steam.lnk",
        "name": "Steam.lnk",
        "type": "shortcut",
        "category": "游戏相关",
        "reason": "rule",
        "classified_by": "rule",
        "enabled": True,
    },
    {
        "path": r"C:\Desktop\resume.pdf",
        "name": "resume.pdf",
        "type": "file",
        "category": "简历求职",
        "reason": "rule",
        "classified_by": "rule",
        "enabled": True,
    },
    {
        "path": r"C:\Desktop\unknown.bin",
        "name": "unknown.bin",
        "type": "file",
        "category": "无法判断",
        "reason": "无法判断分类",
        "classified_by": "provider_failed",
        "enabled": True,
    },
]


class GetItemCategoryTests(unittest.TestCase):
    def test_prefers_human_category(self):
        item = {"human_category": "课程资料", "category": "无法判断", "ai_category": "无法判断"}
        self.assertEqual(get_item_category(item), "课程资料")

    def test_falls_back_to_category(self):
        item = {"human_category": None, "category": "简历求职", "ai_category": ""}
        self.assertEqual(get_item_category(item), "简历求职")

    def test_falls_back_to_ai_category(self):
        item = {"human_category": None, "category": None, "ai_category": "图片截图"}
        self.assertEqual(get_item_category(item), "图片截图")

    def test_returns_default_when_all_empty(self):
        item = {}
        self.assertEqual(get_item_category(item), "无法判断")


class GetItemEnabledTests(unittest.TestCase):
    def test_defaults_to_true(self):
        self.assertTrue(get_item_enabled({}))

    def test_respects_false(self):
        self.assertFalse(get_item_enabled({"enabled": False}))

    def test_respects_true(self):
        self.assertTrue(get_item_enabled({"enabled": True}))


class LoadPlanItemsTests(unittest.TestCase):
    def test_loads_from_review_when_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "review.json"
            review_data = {"items": [{"name": "from_review.pdf"}]}
            review_path.write_text(json.dumps(review_data), encoding="utf-8")

            with mock.patch.object(pe_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch.object(pe_module, "PLAN_FILE", str(tmp) + "/plan.json"):
                items, source = load_plan_items()

            self.assertEqual(items[0]["name"], "from_review.pdf")
            self.assertIn("review", source)

    def test_falls_back_to_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_data = {"items": [{"name": "from_plan.pdf"}]}
            plan_path.write_text(json.dumps(plan_data), encoding="utf-8")
            missing_review = Path(tmp) / "review.json"

            with mock.patch.object(pe_module, "REVIEW_FILE", str(missing_review)), \
                 mock.patch.object(pe_module, "PLAN_FILE", str(plan_path)):
                items, source = load_plan_items()

            self.assertEqual(items[0]["name"], "from_plan.pdf")
            self.assertIn("plan", source)

    def test_returns_empty_when_both_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(pe_module, "REVIEW_FILE", str(tmp) + "/r.json"), \
                 mock.patch.object(pe_module, "PLAN_FILE", str(tmp) + "/p.json"):
                items, source = load_plan_items()
            self.assertEqual(items, [])
            self.assertEqual(source, "none")


class BuildPlanExplanationTests(unittest.TestCase):
    def _make_plan(self, tmp, items=None):
        plan_path = Path(tmp) / "plan.json"
        plan_data = {"items": items or SAMPLE_ITEMS}
        plan_path.write_text(json.dumps(plan_data), encoding="utf-8")
        return plan_path

    def test_counts_total_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._make_plan(tmp)
            fake_config = {"llm_provider": "none", "normal_target_root": r"D:\S", "folder_mode": "move"}
            missing_review = Path(tmp) / "review.json"

            with mock.patch.object(pe_module, "load_config", return_value=fake_config), \
                 mock.patch.object(pe_module, "REVIEW_FILE", str(missing_review)), \
                 mock.patch.object(pe_module, "PLAN_FILE", str(plan_path)):
                result = build_plan_explanation()

            self.assertEqual(result["total_items"], 3)
            self.assertEqual(result["enabled_items"], 3)

    def test_counts_disabled_items(self):
        items_with_disabled = SAMPLE_ITEMS + [
            {
                "path": r"C:\Desktop\skip.txt",
                "name": "skip.txt",
                "type": "file",
                "category": "临时文件",
                "reason": "user disabled",
                "classified_by": "rule",
                "enabled": False,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._make_plan(tmp, items=items_with_disabled)
            fake_config = {"llm_provider": "none", "normal_target_root": r"D:\S", "folder_mode": "move"}
            missing_review = Path(tmp) / "review.json"

            with mock.patch.object(pe_module, "load_config", return_value=fake_config), \
                 mock.patch.object(pe_module, "REVIEW_FILE", str(missing_review)), \
                 mock.patch.object(pe_module, "PLAN_FILE", str(plan_path)):
                result = build_plan_explanation()

            self.assertEqual(result["disabled_items"], 1)
            self.assertEqual(result["enabled_items"], 3)

    def test_warning_items_include_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._make_plan(tmp)
            fake_config = {"llm_provider": "none", "normal_target_root": r"D:\S", "folder_mode": "move"}
            missing_review = Path(tmp) / "review.json"

            with mock.patch.object(pe_module, "load_config", return_value=fake_config), \
                 mock.patch.object(pe_module, "REVIEW_FILE", str(missing_review)), \
                 mock.patch.object(pe_module, "PLAN_FILE", str(plan_path)):
                result = build_plan_explanation()

            warning_names = [w["name"] for w in result["warning_items"]]
            self.assertIn("unknown.bin", warning_names)

    def test_top_categories_sorted_descending(self):
        many_items = [
            {"path": f"C:\\Desktop\\img_{i}.png", "name": f"img_{i}.png",
             "type": "file", "category": "图片截图", "reason": "", "classified_by": "rule", "enabled": True}
            for i in range(5)
        ] + [
            {"path": r"C:\Desktop\resume.pdf", "name": "resume.pdf",
             "type": "file", "category": "简历求职", "reason": "", "classified_by": "rule", "enabled": True}
        ]
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._make_plan(tmp, items=many_items)
            fake_config = {"llm_provider": "none", "normal_target_root": r"D:\S", "folder_mode": "move"}
            missing_review = Path(tmp) / "review.json"

            with mock.patch.object(pe_module, "load_config", return_value=fake_config), \
                 mock.patch.object(pe_module, "REVIEW_FILE", str(missing_review)), \
                 mock.patch.object(pe_module, "PLAN_FILE", str(plan_path)):
                result = build_plan_explanation()

            top = result["top_categories"]
            self.assertEqual(top[0][0], "图片截图")
            self.assertEqual(top[0][1], 5)

    def test_recommendations_include_copy_warning_for_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._make_plan(tmp)
            fake_config = {"llm_provider": "none", "normal_target_root": r"D:\S", "folder_mode": "move"}
            missing_review = Path(tmp) / "review.json"

            with mock.patch.object(pe_module, "load_config", return_value=fake_config), \
                 mock.patch.object(pe_module, "REVIEW_FILE", str(missing_review)), \
                 mock.patch.object(pe_module, "PLAN_FILE", str(plan_path)):
                result = build_plan_explanation()

            recs = " ".join(result["recommendations"])
            self.assertIn("move", recs)

    def test_summary_mentions_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = self._make_plan(tmp)
            fake_config = {"llm_provider": "ollama", "normal_target_root": r"D:\S", "folder_mode": "copy"}
            missing_review = Path(tmp) / "review.json"

            with mock.patch.object(pe_module, "load_config", return_value=fake_config), \
                 mock.patch.object(pe_module, "REVIEW_FILE", str(missing_review)), \
                 mock.patch.object(pe_module, "PLAN_FILE", str(plan_path)):
                result = build_plan_explanation()

            self.assertIn("ollama", result["summary"])


class RenderMarkdownTests(unittest.TestCase):
    def _make_explanation(self):
        return {
            "created_at": "2026-01-01",
            "source_file": "plan.json",
            "provider": "none",
            "target_root": r"D:\Sorted",
            "folder_mode": "move",
            "total_items": 3,
            "enabled_items": 3,
            "disabled_items": 0,
            "type_counts": {"file": 2, "shortcut": 1},
            "category_counts": {"游戏相关": 1, "简历求职": 1, "无法判断": 1},
            "classified_by_counts": {"rule": 2, "provider_failed": 1},
            "top_categories": [("游戏相关", 1)],
            "warning_items": [{"name": "unknown.bin", "type": "file", "category": "无法判断", "reason": "fail"}],
            "summary": "Total 3 items.",
            "recommendations": ["Check unknown items."],
        }

    def test_returns_markdown_string(self):
        exp = self._make_explanation()
        md = render_markdown(exp)
        self.assertIsInstance(md, str)
        self.assertIn("# Desktop Agent Plan Explanation", md)

    def test_includes_category_statistics(self):
        exp = self._make_explanation()
        md = render_markdown(exp)
        self.assertIn("游戏相关", md)
        self.assertIn("简历求职", md)

    def test_includes_warning_items(self):
        exp = self._make_explanation()
        md = render_markdown(exp)
        self.assertIn("unknown.bin", md)

    def test_includes_recommendations(self):
        exp = self._make_explanation()
        md = render_markdown(exp)
        self.assertIn("Check unknown items.", md)

    def test_empty_warning_items_shows_none(self):
        exp = self._make_explanation()
        exp["warning_items"] = []
        md = render_markdown(exp)
        self.assertIn("- 无", md)
