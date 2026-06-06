import unittest

from desktop_agent.planner import (
    contains_any,
    item_search_text,
    rule_classify_item,
    hybrid_preclassify_items,
    chunk_list,
)
from desktop_agent.categories import CATEGORIES


def make_item(name, item_type="file", suffix="", content_summary="", folder_summary=None):
    item = {
        "name": name,
        "display_name": name.rsplit(".", 1)[0] if "." in name else name,
        "suffix": suffix,
        "type": item_type,
        "path": f"C:\\Desktop\\{name}",
        "content_summary": content_summary,
    }
    if folder_summary is not None:
        item["folder_summary"] = folder_summary
    return item


class ContainsAnyTests(unittest.TestCase):
    def test_matches_keyword(self):
        self.assertTrue(contains_any("My Resume 2026.pdf", ["resume", "cv"]))

    def test_case_insensitive(self):
        self.assertTrue(contains_any("RESUME.pdf", ["resume"]))

    def test_no_match(self):
        self.assertFalse(contains_any("photo.jpg", ["resume"]))

    def test_empty_keywords(self):
        self.assertFalse(contains_any("anything", []))


class ItemSearchTextTests(unittest.TestCase):
    def test_includes_name_and_suffix(self):
        item = make_item("report.pdf", suffix=".pdf")
        text = item_search_text(item)
        self.assertIn("report", text)
        self.assertIn(".pdf", text)

    def test_includes_folder_summary_sampled_items(self):
        item = make_item("MyProject", item_type="folder", folder_summary={
            "sampled_items": ["main.py", "README.md"],
            "subfolders": [],
            "content_hints": [],
            "extensions": {},
        })
        text = item_search_text(item)
        self.assertIn("main.py", text)

    def test_includes_content_hints(self):
        item = make_item("Project", item_type="folder", folder_summary={
            "sampled_items": [],
            "subfolders": [],
            "content_hints": [{"file": "req.txt", "summary": "openai requests"}],
            "extensions": {},
        })
        text = item_search_text(item)
        self.assertIn("openai", text)


class RuleClassifyShortcutTests(unittest.TestCase):
    def test_steam_shortcut(self):
        item = make_item("Steam.lnk", item_type="shortcut")
        result = rule_classify_item(item)
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "游戏相关")

    def test_vscode_shortcut(self):
        item = make_item("Visual Studio Code.lnk", item_type="shortcut")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "代码项目")

    def test_chrome_shortcut(self):
        item = make_item("Google Chrome.lnk", item_type="shortcut")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "浏览器通讯")

    def test_wechat_shortcut(self):
        item = make_item("微信.lnk", item_type="shortcut")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "浏览器通讯")

    def test_wps_shortcut(self):
        item = make_item("WPS Office.lnk", item_type="shortcut")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "办公学习")

    def test_obs_shortcut(self):
        item = make_item("OBS Studio.lnk", item_type="shortcut")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "影音娱乐")

    def test_onedrive_shortcut(self):
        item = make_item("OneDrive.lnk", item_type="shortcut")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "网盘VPN")

    def test_fire_shortcut_system_tool(self):
        item = make_item("火绒安全.lnk", item_type="shortcut")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "系统工具")

    def test_unknown_shortcut_returns_none(self):
        item = make_item("SomeRandomApp.lnk", item_type="shortcut")
        result = rule_classify_item(item)
        self.assertIsNone(result)


class RuleClassifyFileTests(unittest.TestCase):
    def test_image_by_suffix(self):
        item = make_item("screenshot.png", suffix=".png")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "图片截图")

    def test_video_by_suffix(self):
        item = make_item("myvideo.mp4", suffix=".mp4")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "视频音频")

    def test_video_suffix_beats_course_keyword(self):
        # Regression for Bug-01: "lecture" keyword must NOT override .mp4 suffix
        item = make_item("lecture.mp4", suffix=".mp4")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "视频音频")

    def test_archive_by_suffix(self):
        item = make_item("backup.zip", suffix=".zip")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "压缩包")

    def test_installer_by_suffix(self):
        item = make_item("setup.exe", suffix=".exe")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "安装包")

    def test_code_file_by_suffix(self):
        item = make_item("main.py", suffix=".py")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "代码项目")

    def test_resume_by_name(self):
        item = make_item("My_Resume_2026.pdf", suffix=".pdf")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "简历求职")

    def test_assignment_by_name(self):
        item = make_item("Assignment1_final.docx", suffix=".docx")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "作业报告")

    def test_passport_by_name(self):
        item = make_item("passport_scan.jpg", suffix=".jpg", content_summary="passport")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "证件合同")

    def test_untitled_file_is_temp(self):
        item = make_item("untitled.txt", suffix=".txt")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "临时文件")

    def test_unknown_file_returns_none(self):
        item = make_item("random_data.bin", suffix=".bin")
        result = rule_classify_item(item)
        self.assertIsNone(result)

    def test_chinese_cv_file(self):
        item = make_item("简历_李明.pdf", suffix=".pdf")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "简历求职")


class RuleClassifyFolderTests(unittest.TestCase):
    def test_code_folder_by_name(self):
        item = make_item("openai_test", item_type="folder")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "代码项目")

    def test_code_folder_by_content(self):
        item = make_item("MyProject", item_type="folder", folder_summary={
            "sampled_items": ["requirements.txt", "main.py"],
            "subfolders": [],
            "content_hints": [],
            "extensions": {".py": 5},
        })
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "代码项目")

    def test_course_folder_by_name(self):
        item = make_item("COMP5003", item_type="folder")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "课程资料")

    def test_installer_folder(self):
        item = make_item("win-x64-setup", item_type="folder")
        result = rule_classify_item(item)
        self.assertEqual(result["category"], "安装包")

    def test_unknown_folder_returns_none(self):
        item = make_item("MyRandomFolder", item_type="folder")
        result = rule_classify_item(item)
        self.assertIsNone(result)

    def test_passenger_not_misclassified(self):
        # Regression for Bug-02: removing "ass"/"a1"/"a2" must stop false matches on
        # names like passenger / assistant / classroom (all contain "ass" as substring)
        for name in ["Passenger_Data", "Assistant_Notes", "ClassRoom"]:
            item = make_item(name, item_type="folder")
            result = rule_classify_item(item)
            self.assertIsNone(result, msg=f"{name} should not be classified, got {result}")


class HybridPreclassifyTests(unittest.TestCase):
    def test_rule_items_are_classified(self):
        items = [
            make_item("Steam.lnk", item_type="shortcut"),
            make_item("screenshot.png", suffix=".png"),
        ]
        classified, need_llm = hybrid_preclassify_items(items)
        self.assertEqual(len(classified), 2)
        self.assertEqual(len(need_llm), 0)

    def test_unknown_items_go_to_llm(self):
        items = [make_item("mystery_file.bin", suffix=".bin")]
        classified, need_llm = hybrid_preclassify_items(items)
        self.assertEqual(len(classified), 0)
        self.assertEqual(len(need_llm), 1)

    def test_all_classified_returns(self):
        items = [
            make_item("resume.pdf", suffix=".pdf"),
            make_item("video.mp4", suffix=".mp4"),
        ]
        classified, need_llm = hybrid_preclassify_items(items)
        categories = {r["category"] for r in classified}
        self.assertIn("简历求职", categories)
        self.assertIn("视频音频", categories)

    def test_all_results_have_valid_categories(self):
        items = [
            make_item("Steam.lnk", item_type="shortcut"),
            make_item("final_report.pdf", suffix=".pdf"),
        ]
        classified, _ = hybrid_preclassify_items(items)
        for item in classified:
            self.assertIn(item["category"], CATEGORIES)


class ChunkListTests(unittest.TestCase):
    def test_exact_multiple(self):
        chunks = list(chunk_list([1, 2, 3, 4], 2))
        self.assertEqual(chunks, [[1, 2], [3, 4]])

    def test_remainder_chunk(self):
        chunks = list(chunk_list([1, 2, 3, 4, 5], 2))
        self.assertEqual(chunks, [[1, 2], [3, 4], [5]])

    def test_empty_list(self):
        chunks = list(chunk_list([], 5))
        self.assertEqual(chunks, [])

    def test_size_larger_than_list(self):
        chunks = list(chunk_list([1, 2], 10))
        self.assertEqual(chunks, [[1, 2]])
