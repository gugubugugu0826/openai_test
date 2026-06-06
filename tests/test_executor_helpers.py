import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import executor


class ExecutorHelperTests(unittest.TestCase):
    def test_get_unique_path_appends_counter_when_target_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "demo.txt"
            original.write_text("1", encoding="utf-8")

            unique = executor.get_unique_path(original)

            self.assertEqual(unique.name, "demo_1.txt")

    def test_get_target_path_uses_shortcut_root_for_shortcuts(self):
        item = {
            "path": r"C:\Users\Public\Desktop\Test.lnk",
            "type": "shortcut",
            "category": "其他快捷方式",
        }

        target = executor.get_target_path(item)

        self.assertEqual(target.parent.name, "99_其他快捷方式")
        self.assertEqual(target.name, "Test.lnk")

    def test_get_target_path_uses_normal_target_root_for_regular_files(self):
        item = {
            "path": r"C:\Users\PC\Desktop\resume.pdf",
            "type": "file",
            "category": "简历求职",
        }

        with mock.patch.object(executor, "load_config", return_value={"normal_target_root": r"D:\Sorted"}):
            target = executor.get_target_path(item)

        self.assertEqual(target.name, "resume.pdf")
        self.assertTrue(str(target).startswith(r"D:\Sorted"))
