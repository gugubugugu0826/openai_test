import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import scanner as scanner_module
from desktop_agent.scanner import (
    build_base_item,
    check_scan_path_safety,
    get_scan_roots,
    get_public_desktop_path,
    is_shortcut,
)


class ScanRootsTests(unittest.TestCase):
    def test_explicit_path_returns_single_root_no_public(self):
        config = {"desktop_path": r"C:\Users\PC\TestDesktop", "_desktop_path_was_empty": False}
        roots = get_scan_roots(config)
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0], Path(r"C:\Users\PC\TestDesktop"))

    def test_empty_desktop_excludes_nonexistent_public(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_desktop = Path(tmp) / "UserDesktop"
            user_desktop.mkdir()
            config = {"desktop_path": str(user_desktop), "_desktop_path_was_empty": True}
            non_existent_public = Path(tmp) / "NonExistentPublic"
            with mock.patch.object(scanner_module, "get_public_desktop_path", return_value=non_existent_public):
                roots = get_scan_roots(config)
            self.assertEqual(roots, [user_desktop])

    def test_deduplicates_same_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_desktop = Path(tmp) / "Desktop"
            user_desktop.mkdir()
            public_desktop = user_desktop
            config = {"desktop_path": str(user_desktop), "_desktop_path_was_empty": True}
            with mock.patch.object(scanner_module, "get_public_desktop_path", return_value=public_desktop):
                roots = get_scan_roots(config)
            self.assertEqual(len(roots), 1)


class SafetyGuardTests(unittest.TestCase):
    def test_drive_root_raises(self):
        with self.assertRaises(RuntimeError):
            check_scan_path_safety(Path("C:\\"))

    def test_home_directory_raises(self):
        home = Path.home()
        with self.assertRaises(RuntimeError):
            check_scan_path_safety(home)

    def test_shallow_path_raises(self):
        with self.assertRaises(RuntimeError):
            check_scan_path_safety(Path("C:\\Users"))

    def test_desktop_depth_path_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            deep = Path(tmp) / "a" / "b"
            deep.mkdir(parents=True)
            # Should not raise (depth >= 3)
            try:
                check_scan_path_safety(deep)
            except RuntimeError as e:
                if "过大" in str(e) or "危险" in str(e):
                    self.fail(f"Should not raise for deep path: {e}")


class IsShortcutTests(unittest.TestCase):
    def test_lnk_is_shortcut(self):
        self.assertTrue(is_shortcut(Path("Chrome.lnk")))

    def test_url_is_shortcut(self):
        self.assertTrue(is_shortcut(Path("SomeLink.url")))

    def test_exe_is_not_shortcut(self):
        self.assertFalse(is_shortcut(Path("setup.exe")))

    def test_case_insensitive_lnk(self):
        self.assertTrue(is_shortcut(Path("File.LNK")))


class BuildBaseItemTests(unittest.TestCase):
    def test_file_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "report.pdf"
            f.write_text("pdf", encoding="utf-8")
            item = build_base_item(f, root)
            self.assertEqual(item["type"], "file")
            self.assertEqual(item["name"], "report.pdf")
            self.assertEqual(item["suffix"], ".pdf")

    def test_folder_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "MyProject"
            folder.mkdir()
            item = build_base_item(folder, root)
            self.assertEqual(item["type"], "folder")

    def test_shortcut_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lnk = root / "Chrome.lnk"
            lnk.write_text("lnk", encoding="utf-8")
            item = build_base_item(lnk, root)
            self.assertEqual(item["type"], "shortcut")

    def test_chinese_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "我的简历.pdf"
            f.write_text("简历内容", encoding="utf-8")
            item = build_base_item(f, root)
            self.assertEqual(item["name"], "我的简历.pdf")
            self.assertEqual(item["display_name"], "我的简历")

    def test_desktop_root_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "test.txt"
            f.write_text("x", encoding="utf-8")
            item = build_base_item(f, root)
            self.assertEqual(item["desktop_root"], str(root))


class ScanDesktopTests(unittest.TestCase):
    def test_scan_raises_when_desktop_not_exist(self):
        config = {
            "desktop_path": r"C:\DoesNotExist\Desktop",
            "_desktop_path_was_empty": False,
            "max_internal_items_per_folder": 200,
        }
        with mock.patch.object(scanner_module, "load_config", return_value=config):
            with self.assertRaises(FileNotFoundError):
                scanner_module.scan_desktop()

    def test_scan_saves_observation_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            desktop = Path(tmp) / "Desktop"
            desktop.mkdir()
            (desktop / "note.txt").write_text("hello", encoding="utf-8")

            config = {
                "desktop_path": str(desktop),
                "_desktop_path_was_empty": False,
                "max_internal_items_per_folder": 200,
            }

            obs_path = Path(tmp) / "obs.json"

            with mock.patch.object(scanner_module, "load_config", return_value=config), \
                 mock.patch.object(scanner_module, "OBSERVATION_FILE", str(obs_path)), \
                 mock.patch("desktop_agent.state.save_json"), \
                 mock.patch("desktop_agent.state.load_json", return_value={}), \
                 mock.patch("desktop_agent.state.STATE_FILE", str(Path(tmp) / "state.json")):
                from desktop_agent.storage import save_json as real_save
                with mock.patch("desktop_agent.scanner.save_json") as mock_save, \
                     mock.patch("desktop_agent.scanner.update_state"):
                    scanner_module.scan_desktop()
                    mock_save.assert_called_once()
                    call_args = mock_save.call_args
                    obs_data = call_args[0][1]
                    self.assertEqual(obs_data["items_count"], 1)
                    self.assertEqual(obs_data["items"][0]["name"], "note.txt")

    def test_scan_desktop_merges_public_in_empty_path_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_desktop = Path(tmp) / "UserDesktop"
            public_desktop = Path(tmp) / "PublicDesktop"
            user_desktop.mkdir()
            public_desktop.mkdir()
            (user_desktop / "user_file.txt").write_text("u", encoding="utf-8")
            (public_desktop / "public_shortcut.lnk").write_text("lnk", encoding="utf-8")

            config = {
                "desktop_path": str(user_desktop),
                "_desktop_path_was_empty": True,
                "max_internal_items_per_folder": 200,
            }

            with mock.patch.object(scanner_module, "load_config", return_value=config), \
                 mock.patch.object(scanner_module, "get_public_desktop_path", return_value=public_desktop), \
                 mock.patch("desktop_agent.scanner.save_json") as mock_save, \
                 mock.patch("desktop_agent.scanner.update_state"):
                scanner_module.scan_desktop()
                obs_data = mock_save.call_args[0][1]
                names = [item["name"] for item in obs_data["items"]]
                self.assertIn("user_file.txt", names)
                self.assertIn("public_shortcut.lnk", names)
