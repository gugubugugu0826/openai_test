import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import executor as executor_module
from desktop_agent.executor import (
    get_unique_path,
    get_target_path,
    load_execution_items,
    apply_plan,
    undo_last_action,
    dryrun_plan,
)


FAKE_CONFIG = {
    "normal_target_root": "",  # will be patched per-test
    "folder_mode": "move",
}


def make_review_item(name, path, category, item_type="file", enabled=True):
    return {
        "enabled": enabled,
        "path": path,
        "name": name,
        "type": item_type,
        "ai_category": category,
        "human_category": category,
        "reason": "test",
    }


class GetUniquePathTests(unittest.TestCase):
    def test_no_conflict_returns_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "newfile.txt"
            self.assertEqual(get_unique_path(dst), dst)

    def test_conflict_appends_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "file.txt"
            dst.write_text("x")
            unique = get_unique_path(dst)
            self.assertEqual(unique.name, "file_1.txt")

    def test_multiple_conflicts_increment_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "file.txt"
            dst.write_text("x")
            (Path(tmp) / "file_1.txt").write_text("x")
            unique = get_unique_path(dst)
            self.assertEqual(unique.name, "file_2.txt")

    def test_no_suffix_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "noext"
            dst.write_text("x")
            unique = get_unique_path(dst)
            self.assertEqual(unique.name, "noext_1")


class GetTargetPathTests(unittest.TestCase):
    def test_shortcut_placed_in_desktop_root(self):
        item = {
            "path": r"C:\Users\Public\Desktop\Steam.lnk",
            "type": "shortcut",
            "category": "游戏相关",
        }
        target = get_target_path(item)
        self.assertEqual(target.parent.name, "01_游戏快捷方式")
        self.assertEqual(target.name, "Steam.lnk")

    def test_unknown_shortcut_goes_to_99(self):
        item = {
            "path": r"C:\Desktop\Mystery.lnk",
            "type": "shortcut",
            "category": "无法判断",
        }
        target = get_target_path(item)
        self.assertEqual(target.parent.name, "99_其他快捷方式")

    def test_normal_file_placed_under_target_root(self):
        item = {
            "path": r"C:\Desktop\resume.pdf",
            "type": "file",
            "category": "简历求职",
        }
        fake_config = {"normal_target_root": r"D:\Sorted", "folder_mode": "move"}
        with mock.patch.object(executor_module, "load_config", return_value=fake_config):
            target = get_target_path(item)
        self.assertIn("简历求职", str(target))
        self.assertTrue(str(target).startswith(r"D:\Sorted"))

    def test_human_category_overrides_ai(self):
        item = {
            "path": r"C:\Desktop\file.pdf",
            "type": "file",
            "ai_category": "无法判断",
            "human_category": "课程资料",
            "category": "无法判断",
        }
        fake_config = {"normal_target_root": r"D:\Sorted", "folder_mode": "move"}
        with mock.patch.object(executor_module, "load_config", return_value=fake_config):
            target = get_target_path(item)
        self.assertIn("课程资料", str(target))


class LoadExecutionItemsTests(unittest.TestCase):
    def test_loads_from_review_file_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "review.json"
            review_data = {
                "items": [
                    {
                        "enabled": True,
                        "path": r"C:\Desktop\file.pdf",
                        "name": "file.pdf",
                        "type": "file",
                        "ai_category": "图片截图",
                        "human_category": "简历求职",
                        "reason": "changed",
                    }
                ]
            }
            review_path.write_text(json.dumps(review_data), encoding="utf-8")

            with mock.patch.object(executor_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch.object(executor_module, "PLAN_FILE", str(tmp) + "/plan.json"):
                items, source = load_execution_items()

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["category"], "简历求职")
            self.assertIn("review", source)

    def test_disabled_items_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "review.json"
            review_data = {
                "items": [
                    {
                        "enabled": False,
                        "path": r"C:\Desktop\file.pdf",
                        "name": "file.pdf",
                        "type": "file",
                        "ai_category": "图片截图",
                        "human_category": "图片截图",
                        "reason": "",
                    },
                    {
                        "enabled": True,
                        "path": r"C:\Desktop\file2.pdf",
                        "name": "file2.pdf",
                        "type": "file",
                        "ai_category": "简历求职",
                        "human_category": "简历求职",
                        "reason": "",
                    }
                ]
            }
            review_path.write_text(json.dumps(review_data), encoding="utf-8")

            with mock.patch.object(executor_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch.object(executor_module, "PLAN_FILE", str(tmp) + "/plan.json"):
                items, _ = load_execution_items()

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["name"], "file2.pdf")

    def test_invalid_category_falls_back_to_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "review.json"
            review_data = {
                "items": [
                    {
                        "enabled": True,
                        "path": r"C:\Desktop\file.pdf",
                        "name": "file.pdf",
                        "type": "file",
                        "ai_category": "非法分类XYZ",
                        "human_category": "非法分类XYZ",
                        "reason": "",
                    }
                ]
            }
            review_path.write_text(json.dumps(review_data), encoding="utf-8")

            with mock.patch.object(executor_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch.object(executor_module, "PLAN_FILE", str(tmp) + "/plan.json"):
                items, _ = load_execution_items()

            self.assertEqual(items[0]["category"], "无法判断")


class ApplyPlanTests(unittest.TestCase):
    def _make_env(self, tmp):
        src = Path(tmp) / "Desktop"
        src.mkdir()
        dst_root = Path(tmp) / "Sorted"
        dst_root.mkdir()

        file1 = src / "resume.pdf"
        file1.write_text("resume content", encoding="utf-8")

        review_path = Path(tmp) / "review.json"
        review_data = {
            "items": [
                {
                    "enabled": True,
                    "path": str(file1),
                    "name": "resume.pdf",
                    "type": "file",
                    "ai_category": "简历求职",
                    "human_category": "简历求职",
                    "reason": "test",
                }
            ]
        }
        review_path.write_text(json.dumps(review_data), encoding="utf-8")

        return src, dst_root, review_path

    def test_apply_moves_file_to_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst_root, review_path = self._make_env(tmp)
            log_path = Path(tmp) / "action_log.json"
            fake_config = {
                "normal_target_root": str(dst_root),
                "folder_mode": "move",
            }

            with mock.patch.object(executor_module, "load_config", return_value=fake_config), \
                 mock.patch.object(executor_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch.object(executor_module, "PLAN_FILE", str(tmp) + "/plan.json"), \
                 mock.patch.object(executor_module, "ACTION_LOG_FILE", str(log_path)), \
                 mock.patch("desktop_agent.executor.update_state"):
                apply_plan()

            moved_file = dst_root / "简历求职" / "resume.pdf"
            self.assertTrue(moved_file.exists())
            original = src / "resume.pdf"
            self.assertFalse(original.exists())

    def test_apply_skips_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst_root = Path(tmp) / "Sorted"
            dst_root.mkdir()
            review_path = Path(tmp) / "review.json"
            review_data = {
                "items": [
                    {
                        "enabled": True,
                        "path": str(Path(tmp) / "nonexistent.txt"),
                        "name": "nonexistent.txt",
                        "type": "file",
                        "ai_category": "临时文件",
                        "human_category": "临时文件",
                        "reason": "test",
                    }
                ]
            }
            review_path.write_text(json.dumps(review_data), encoding="utf-8")
            log_path = Path(tmp) / "action_log.json"
            fake_config = {"normal_target_root": str(dst_root), "folder_mode": "move"}

            with mock.patch.object(executor_module, "load_config", return_value=fake_config), \
                 mock.patch.object(executor_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch.object(executor_module, "PLAN_FILE", str(tmp) + "/plan.json"), \
                 mock.patch.object(executor_module, "ACTION_LOG_FILE", str(log_path)), \
                 mock.patch("desktop_agent.executor.update_state"):
                apply_plan()

            log = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(log["actions"][0]["status"], "skipped")

    def test_apply_resolves_name_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "Desktop"
            src.mkdir()
            dst_root = Path(tmp) / "Sorted"
            (dst_root / "简历求职").mkdir(parents=True)
            existing = dst_root / "简历求职" / "resume.pdf"
            existing.write_text("old content")

            src_file = src / "resume.pdf"
            src_file.write_text("new content")

            review_path = Path(tmp) / "review.json"
            review_data = {
                "items": [
                    {
                        "enabled": True,
                        "path": str(src_file),
                        "name": "resume.pdf",
                        "type": "file",
                        "ai_category": "简历求职",
                        "human_category": "简历求职",
                        "reason": "",
                    }
                ]
            }
            review_path.write_text(json.dumps(review_data), encoding="utf-8")
            log_path = Path(tmp) / "action_log.json"
            fake_config = {"normal_target_root": str(dst_root), "folder_mode": "move"}

            with mock.patch.object(executor_module, "load_config", return_value=fake_config), \
                 mock.patch.object(executor_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch.object(executor_module, "PLAN_FILE", str(tmp) + "/plan.json"), \
                 mock.patch.object(executor_module, "ACTION_LOG_FILE", str(log_path)), \
                 mock.patch("desktop_agent.executor.update_state"):
                apply_plan()

            self.assertTrue(existing.exists())
            renamed = dst_root / "简历求职" / "resume_1.pdf"
            self.assertTrue(renamed.exists())


class UndoLastActionTests(unittest.TestCase):
    def test_undo_restores_moved_file(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            original_dir = Path(tmp) / "Desktop"
            original_dir.mkdir()
            target_dir = Path(tmp) / "Sorted" / "简历求职"
            target_dir.mkdir(parents=True)

            moved_file = target_dir / "resume.pdf"
            moved_file.write_text("content")

            log_path = Path(tmp) / "action_log.json"
            log_data = {
                "created_at": "2026-01-01",
                "source_plan": "plan.json",
                "actions": [
                    {
                        "status": "moved",
                        "src": str(original_dir / "resume.pdf"),
                        "dst": str(moved_file),
                        "item": {},
                    }
                ]
            }
            log_path.write_text(json.dumps(log_data), encoding="utf-8")

            orig_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                with mock.patch.object(executor_module, "ACTION_LOG_FILE", str(log_path)), \
                     mock.patch("desktop_agent.executor.update_state"):
                    undo_last_action()
            finally:
                os.chdir(orig_cwd)

            restored = original_dir / "resume.pdf"
            self.assertTrue(restored.exists())

    def test_undo_missing_log_prints_hint(self, ):
        with tempfile.TemporaryDirectory() as tmp:
            missing_log = Path(tmp) / "action_log.json"
            with mock.patch.object(executor_module, "ACTION_LOG_FILE", str(missing_log)):
                # Should not raise, just print and return
                with mock.patch("desktop_agent.state.require_file", return_value=False):
                    undo_last_action()


class DryrunPlanTests(unittest.TestCase):
    def test_dryrun_without_any_plan_prints_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_review = Path(tmp) / "review.json"
            missing_plan = Path(tmp) / "plan.json"
            with mock.patch.object(executor_module, "REVIEW_FILE", str(missing_review)), \
                 mock.patch.object(executor_module, "PLAN_FILE", str(missing_plan)):
                import io
                from contextlib import redirect_stdout
                out = io.StringIO()
                with redirect_stdout(out):
                    dryrun_plan()
                self.assertIn("缺少执行来源", out.getvalue())

    def test_dryrun_shows_plan_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_file = Path(tmp) / "screenshot.png"
            src_file.write_text("img")

            review_path = Path(tmp) / "review.json"
            review_data = {
                "items": [
                    {
                        "enabled": True,
                        "path": str(src_file),
                        "name": "screenshot.png",
                        "type": "file",
                        "ai_category": "图片截图",
                        "human_category": "图片截图",
                        "reason": "image suffix",
                    }
                ]
            }
            review_path.write_text(json.dumps(review_data), encoding="utf-8")
            fake_config = {"normal_target_root": str(tmp), "folder_mode": "move"}

            import io
            from contextlib import redirect_stdout
            out = io.StringIO()

            with mock.patch.object(executor_module, "REVIEW_FILE", str(review_path)), \
                 mock.patch.object(executor_module, "PLAN_FILE", str(tmp) + "/plan.json"), \
                 mock.patch.object(executor_module, "load_config", return_value=fake_config), \
                 mock.patch("desktop_agent.executor.update_state"):
                with redirect_stdout(out):
                    dryrun_plan()

            self.assertIn("screenshot.png", out.getvalue())
            self.assertIn("预演", out.getvalue())
