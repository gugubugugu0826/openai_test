# desktop_agent/content_summarizer.py

import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree


TEXT_EXTS = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".yaml", ".yml",
    ".py", ".java", ".js", ".ts", ".html", ".css", ".sql",
    ".r", ".rmd", ".xml", ".log", ".ini", ".cfg", ".toml",
}

DOCX_EXTS = {
    ".docx"
}

MAX_TEXT_CHARS = 2500
MAX_SUMMARY_CHARS = 800


def safe_read_text(path: Path, max_chars=MAX_TEXT_CHARS):
    """
    安全读取文本文件前 max_chars 个字符。
    """
    encodings = ["utf-8", "utf-8-sig", "gbk", "latin-1"]

    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="ignore") as f:
                return f.read(max_chars)
        except Exception:
            continue

    return ""


def compact_text(text: str, max_chars=MAX_SUMMARY_CHARS):
    """
    压缩文本，去掉多余空白。
    """
    if not text:
        return ""

    text = text.replace("\r", "\n")
    lines = []

    for line in text.split("\n"):
        line = line.strip()
        if line:
            lines.append(line)

    compact = " | ".join(lines)

    if len(compact) > max_chars:
        compact = compact[:max_chars] + "..."

    return compact


def summarize_text_file(path: Path):
    raw = safe_read_text(path)
    compact = compact_text(raw)

    if not compact:
        return ""

    return f"文本内容预览：{compact}"


def summarize_json_file(path: Path):
    try:
        raw = safe_read_text(path)
        data = json.loads(raw)

        if isinstance(data, dict):
            keys = list(data.keys())[:20]
            return f"JSON 文件，顶层 keys：{keys}"

        if isinstance(data, list):
            return f"JSON 数组，长度约：{len(data)}，前项类型：{type(data[0]).__name__ if data else 'empty'}"

        return f"JSON 内容类型：{type(data).__name__}"

    except Exception:
        return summarize_text_file(path)


def summarize_docx_file(path: Path):
    """
    轻量读取 docx 文本。
    不依赖 python-docx。
    """
    try:
        texts = []

        with zipfile.ZipFile(path) as z:
            if "word/document.xml" not in z.namelist():
                return ""

            xml_content = z.read("word/document.xml")
            root = ElementTree.fromstring(xml_content)

            namespace = {
                "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            }

            for node in root.findall(".//w:t", namespace):
                if node.text:
                    texts.append(node.text)

        content = " ".join(texts)
        content = compact_text(content)

        if not content:
            return ""

        return f"Word 文档内容预览：{content}"

    except Exception:
        return ""


def summarize_code_project_file(path: Path):
    """
    针对常见项目配置文件生成更有用的摘要。
    """
    name = path.name.lower()

    try:
        if name == "package.json":
            raw = safe_read_text(path)
            data = json.loads(raw)

            project_name = data.get("name", "")
            scripts = list(data.get("scripts", {}).keys())[:10]
            deps = list(data.get("dependencies", {}).keys())[:15]
            dev_deps = list(data.get("devDependencies", {}).keys())[:15]

            return (
                f"Node 项目配置。name={project_name}, "
                f"scripts={scripts}, dependencies={deps}, devDependencies={dev_deps}"
            )

        if name == "requirements.txt":
            raw = safe_read_text(path)
            lines = [
                line.strip()
                for line in raw.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            return f"Python requirements，依赖前若干项：{lines[:20]}"

        if name == "pyproject.toml":
            return "Python 项目配置文件 pyproject.toml"

        if name == "pom.xml":
            return "Java Maven 项目配置文件 pom.xml"

        if name == "build.gradle":
            return "Java/Gradle 项目配置文件 build.gradle"

        if name == "README.md".lower():
            return summarize_text_file(path)

    except Exception:
        pass

    return ""


def summarize_file_content(path):
    """
    对单个文件生成轻量内容摘要。
    注意：只读取小部分，不做深度 OCR，不读取大文件全文。
    """
    path = Path(path)

    if not path.exists() or not path.is_file():
        return ""

    suffix = path.suffix.lower()

    try:
        size_mb = path.stat().st_size / 1024 / 1024
        if size_mb > 20:
            return f"文件较大，大小约 {size_mb:.1f} MB，跳过内容读取"
    except Exception:
        pass

    project_summary = summarize_code_project_file(path)
    if project_summary:
        return project_summary

    if suffix == ".json":
        return summarize_json_file(path)

    if suffix in TEXT_EXTS:
        return summarize_text_file(path)

    if suffix in DOCX_EXTS:
        return summarize_docx_file(path)

    if suffix == ".pdf":
        return "PDF 文件。当前轻量模式不读取 PDF 正文，仅根据文件名和路径分类。"

    if suffix in [".ppt", ".pptx"]:
        return "演示文稿文件。当前轻量模式不读取 PPT 正文，仅根据文件名和路径分类。"

    if suffix in [".xls", ".xlsx"]:
        return "表格文件。当前轻量模式不读取 Excel 正文，仅根据文件名和路径分类。"

    return ""


def summarize_folder_content(folder_path, max_items=80, max_content_files=8):
    """
    给桌面第一层文件夹生成摘要。
    只采样内部文件名、子文件夹名、少量关键文件内容。
    """
    folder_path = Path(folder_path)

    if not folder_path.exists() or not folder_path.is_dir():
        return {}

    summary = {
        "folder_name": folder_path.name,
        "sampled_items": [],
        "subfolders": [],
        "extensions": {},
        "key_files": [],
        "content_hints": [],
        "total_sampled": 0
    }

    count = 0
    content_count = 0

    key_names = {
        "readme.md",
        "readme.txt",
        "requirements.txt",
        "package.json",
        "pyproject.toml",
        "pom.xml",
        "build.gradle",
        "report.md",
        "summary.md",
    }

    try:
        for item in folder_path.rglob("*"):
            if count >= max_items:
                break

            try:
                relative = item.relative_to(folder_path)
            except Exception:
                relative = item.name

            name = str(relative)
            summary["sampled_items"].append(name)
            count += 1

            if item.is_dir():
                summary["subfolders"].append(name)
                continue

            suffix = item.suffix.lower()
            if suffix:
                summary["extensions"][suffix] = summary["extensions"].get(suffix, 0) + 1

            lower_name = item.name.lower()

            if lower_name in key_names or item.suffix.lower() in [".md", ".txt", ".py", ".json", ".docx"]:
                if content_count < max_content_files:
                    content_summary = summarize_file_content(item)

                    if content_summary:
                        summary["key_files"].append(name)
                        summary["content_hints"].append({
                            "file": name,
                            "summary": content_summary
                        })
                        content_count += 1

    except Exception as e:
        summary["error"] = str(e)

    summary["total_sampled"] = count
    summary["subfolders"] = summary["subfolders"][:30]

    return summary