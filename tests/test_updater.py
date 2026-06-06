import unittest

from desktop_agent.updater import (
    get_package_filename,
    is_newer_version,
    normalize_github_release_manifest,
    parse_version,
)


class UpdaterTests(unittest.TestCase):
    def test_parse_version_extracts_numbers(self):
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("release-2026.06"), (2026, 6, 0))

    def test_is_newer_version_compares_semantic_versions(self):
        self.assertTrue(is_newer_version("v1.1", "v1.0"))
        self.assertFalse(is_newer_version("v1.0", "v1.0"))
        self.assertFalse(is_newer_version("v0.9", "v1.0"))

    def test_normalize_github_release_manifest_extracts_zip_asset(self):
        manifest = normalize_github_release_manifest(
            {
                "tag_name": "v1.2",
                "body": "更新说明",
                "assets": [
                    {
                        "name": "QwenDesktopAgent_v1.2.zip",
                        "browser_download_url": "https://example.com/QwenDesktopAgent_v1.2.zip",
                        "digest": "sha256:abc123",
                    }
                ],
            }
        )

        self.assertEqual(manifest["version"], "v1.2")
        self.assertEqual(manifest["package_name"], "QwenDesktopAgent_v1.2.zip")
        self.assertEqual(manifest["package_url"], "https://example.com/QwenDesktopAgent_v1.2.zip")
        self.assertEqual(manifest["sha256"], "abc123")

    def test_get_package_filename_prefers_manifest_name(self):
        filename = get_package_filename(
            {
                "package_name": "QwenDesktopAgent_v1.3.zip",
                "package_url": "https://example.com/ignored.zip",
            }
        )
        self.assertEqual(filename, "QwenDesktopAgent_v1.3.zip")
