import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_agent import scanner


class ScannerHelperTests(unittest.TestCase):
    def test_get_scan_roots_with_explicit_path_returns_single_root(self):
        config = {
            "desktop_path": r"C:\demo\Desktop",
            "_desktop_path_was_empty": False,
        }

        roots = scanner.get_scan_roots(config)

        self.assertEqual(roots, [Path(r"C:\demo\Desktop")])

    def test_get_scan_roots_with_empty_desktop_merges_public_desktop(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_desktop = Path(tmp) / "UserDesktop"
            public_desktop = Path(tmp) / "PublicDesktop"
            user_desktop.mkdir()
            public_desktop.mkdir()

            config = {
                "desktop_path": str(user_desktop),
                "_desktop_path_was_empty": True,
            }

            with mock.patch.object(scanner, "get_public_desktop_path", return_value=public_desktop):
                roots = scanner.get_scan_roots(config)

            self.assertEqual(roots, [user_desktop, public_desktop])

    def test_build_base_item_marks_shortcuts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shortcut = root / "App.lnk"
            shortcut.write_text("shortcut", encoding="utf-8")

            item = scanner.build_base_item(shortcut, root)

            self.assertEqual(item["type"], "shortcut")
            self.assertEqual(item["desktop_root"], str(root))
