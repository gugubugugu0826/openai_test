import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import config as config_module
from desktop_agent.config import load_config


class ConfigLoadTests(unittest.TestCase):
    def test_raises_when_config_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "config.json"
            with mock.patch.object(config_module, "CONFIG_FILE", str(missing)):
                with self.assertRaises(FileNotFoundError):
                    load_config()

    def test_loads_valid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(
                json.dumps({
                    "desktop_path": r"C:\Users\PC\Desktop",
                    "normal_target_root": r"D:\Sorted",
                    "llm_provider": "none",
                }),
                encoding="utf-8",
            )
            with mock.patch.object(config_module, "CONFIG_FILE", str(cfg_path)):
                cfg = load_config()
        self.assertEqual(cfg["desktop_path"], r"C:\Users\PC\Desktop")
        self.assertFalse(cfg["_desktop_path_was_empty"])

    def test_empty_desktop_path_uses_home_and_marks_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(
                json.dumps({"desktop_path": "", "normal_target_root": r"D:\Sorted"}),
                encoding="utf-8",
            )
            with mock.patch.object(config_module, "CONFIG_FILE", str(cfg_path)):
                cfg = load_config()
        self.assertTrue(cfg["_desktop_path_was_empty"])
        self.assertIn("Desktop", cfg["desktop_path"])

    def test_null_desktop_path_treated_as_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(
                json.dumps({"desktop_path": None, "normal_target_root": r"D:\Sorted"}),
                encoding="utf-8",
            )
            with mock.patch.object(config_module, "CONFIG_FILE", str(cfg_path)):
                cfg = load_config()
        self.assertTrue(cfg["_desktop_path_was_empty"])

    def test_whitespace_desktop_path_treated_as_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(
                json.dumps({"desktop_path": "   ", "normal_target_root": r"D:\Sorted"}),
                encoding="utf-8",
            )
            with mock.patch.object(config_module, "CONFIG_FILE", str(cfg_path)):
                cfg = load_config()
        self.assertTrue(cfg["_desktop_path_was_empty"])

    def test_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text("{not valid json}", encoding="utf-8")
            with mock.patch.object(config_module, "CONFIG_FILE", str(cfg_path)):
                with self.assertRaises(Exception):
                    load_config()

    def test_missing_normal_target_root_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(
                json.dumps({"desktop_path": r"C:\Desktop", "llm_provider": "none"}),
                encoding="utf-8",
            )
            with mock.patch.object(config_module, "CONFIG_FILE", str(cfg_path)):
                with self.assertRaises(ValueError) as ctx:
                    load_config()
            self.assertIn("normal_target_root", str(ctx.exception))

    def test_empty_normal_target_root_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(
                json.dumps({"desktop_path": r"C:\Desktop", "normal_target_root": "   "}),
                encoding="utf-8",
            )
            with mock.patch.object(config_module, "CONFIG_FILE", str(cfg_path)):
                with self.assertRaises(ValueError):
                    load_config()
