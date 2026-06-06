import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import memory as memory_module
from desktop_agent.memory import (
    add_memory_rule,
    load_memory,
    save_memory,
    memory_classify_item,
)
from desktop_agent.categories import CATEGORIES


def make_item(name, path=None, item_type="file"):
    return {
        "name": name,
        "path": path or f"C:\\Desktop\\{name}",
        "type": item_type,
    }


class LoadSaveMemoryTests(unittest.TestCase):
    def test_creates_default_memory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_path = Path(tmp) / "memory.json"
            with mock.patch.object(memory_module, "MEMORY_FILE", str(mem_path)):
                mem = load_memory()
            self.assertIn("rules", mem)
            self.assertEqual(mem["rules"], [])
            self.assertTrue(mem_path.exists())

    def test_loads_existing_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_path = Path(tmp) / "memory.json"
            mem_data = {"rules": [{"match": "steam", "category": "游戏相关", "note": ""}]}
            mem_path.write_text(json.dumps(mem_data), encoding="utf-8")
            with mock.patch.object(memory_module, "MEMORY_FILE", str(mem_path)):
                mem = load_memory()
            self.assertEqual(len(mem["rules"]), 1)

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_path = Path(tmp) / "memory.json"
            mem_data = {"rules": [{"match": "resume", "category": "简历求职", "note": "test"}]}
            with mock.patch.object(memory_module, "MEMORY_FILE", str(mem_path)):
                save_memory(mem_data)
                loaded = load_memory()
            self.assertEqual(loaded["rules"][0]["match"], "resume")


class AddMemoryRuleTests(unittest.TestCase):
    def test_adds_valid_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_path = Path(tmp) / "memory.json"
            with mock.patch.object(memory_module, "MEMORY_FILE", str(mem_path)):
                result = add_memory_rule("steam", "游戏相关", "user added")
                self.assertTrue(result)
                mem = load_memory()
                self.assertEqual(len(mem["rules"]), 1)
                self.assertEqual(mem["rules"][0]["match"], "steam")

    def test_rejects_invalid_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_path = Path(tmp) / "memory.json"
            with mock.patch.object(memory_module, "MEMORY_FILE", str(mem_path)):
                with self.assertRaises(ValueError):
                    add_memory_rule("test", "非法分类XYZ", "note")

    def test_no_duplicate_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_path = Path(tmp) / "memory.json"
            with mock.patch.object(memory_module, "MEMORY_FILE", str(mem_path)):
                add_memory_rule("steam", "游戏相关", "first")
                result = add_memory_rule("steam", "游戏相关", "second")
                self.assertFalse(result)
                mem = load_memory()
                self.assertEqual(len(mem["rules"]), 1)

    def test_case_insensitive_duplicate_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_path = Path(tmp) / "memory.json"
            with mock.patch.object(memory_module, "MEMORY_FILE", str(mem_path)):
                add_memory_rule("Steam", "游戏相关", "first")
                result = add_memory_rule("steam", "游戏相关", "second")
                self.assertFalse(result)

    def test_same_match_different_category_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_path = Path(tmp) / "memory.json"
            with mock.patch.object(memory_module, "MEMORY_FILE", str(mem_path)):
                add_memory_rule("app", "系统工具", "first")
                result = add_memory_rule("app", "代码项目", "second")
                self.assertTrue(result)
                mem = load_memory()
                self.assertEqual(len(mem["rules"]), 2)


class MemoryClassifyItemTests(unittest.TestCase):
    def test_matches_by_name(self):
        mem = {"rules": [{"match": "steam", "category": "游戏相关", "note": "rule1"}]}
        with mock.patch.object(memory_module, "load_memory", return_value=mem):
            item = make_item("Steam.lnk", item_type="shortcut")
            result = memory_classify_item(item)
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "游戏相关")
        self.assertEqual(result["classified_by"], "memory")

    def test_matches_by_path(self):
        mem = {"rules": [{"match": "resume", "category": "简历求职", "note": ""}]}
        with mock.patch.object(memory_module, "load_memory", return_value=mem):
            item = make_item("My_CV.pdf", path=r"C:\Desktop\old_resume_folder\My_CV.pdf")
            result = memory_classify_item(item)
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "简历求职")

    def test_no_match_returns_none(self):
        mem = {"rules": [{"match": "steam", "category": "游戏相关", "note": ""}]}
        with mock.patch.object(memory_module, "load_memory", return_value=mem):
            item = make_item("random_file.bin")
            result = memory_classify_item(item)
        self.assertIsNone(result)

    def test_empty_rules_returns_none(self):
        mem = {"rules": []}
        with mock.patch.object(memory_module, "load_memory", return_value=mem):
            result = memory_classify_item(make_item("anything.txt"))
        self.assertIsNone(result)

    def test_invalid_category_in_rule_is_skipped(self):
        mem = {"rules": [{"match": "test", "category": "非法分类XYZ", "note": ""}]}
        with mock.patch.object(memory_module, "load_memory", return_value=mem):
            result = memory_classify_item(make_item("test_file.txt"))
        self.assertIsNone(result)

    def test_empty_match_in_rule_is_skipped(self):
        mem = {"rules": [{"match": "", "category": "课程资料", "note": ""}]}
        with mock.patch.object(memory_module, "load_memory", return_value=mem):
            result = memory_classify_item(make_item("course_material.pdf"))
        self.assertIsNone(result)

    def test_case_insensitive_match(self):
        mem = {"rules": [{"match": "STEAM", "category": "游戏相关", "note": ""}]}
        with mock.patch.object(memory_module, "load_memory", return_value=mem):
            item = make_item("steam.lnk", item_type="shortcut")
            result = memory_classify_item(item)
        self.assertIsNotNone(result)

    def test_first_matching_rule_wins(self):
        mem = {"rules": [
            {"match": "steam", "category": "游戏相关", "note": "first"},
            {"match": "steam", "category": "系统工具", "note": "second"},
        ]}
        with mock.patch.object(memory_module, "load_memory", return_value=mem):
            item = make_item("Steam.lnk", item_type="shortcut")
            result = memory_classify_item(item)
        self.assertEqual(result["category"], "游戏相关")
