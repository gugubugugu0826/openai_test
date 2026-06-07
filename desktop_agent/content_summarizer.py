import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from desktop_agent.i18n import t


TEXT_EXTS = {
    ".txt",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".java",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".sql",
    ".r",
    ".rmd",
    ".xml",
    ".log",
    ".ini",
    ".cfg",
    ".toml",
}

DOCX_EXTS = {".docx"}

MAX_TEXT_CHARS = 2500
MAX_SUMMARY_CHARS = 800


def safe_read_text(path: Path, max_chars=MAX_TEXT_CHARS):
    encodings = ["utf-8", "utf-8-sig", "gbk", "latin-1"]

    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="ignore") as f:
                return f.read(max_chars)
        except Exception:
            continue

    return ""


def compact_text(text: str, max_chars=MAX_SUMMARY_CHARS):
    if not text:
        return ""

    text = text.replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    compact = " | ".join(lines)

    if len(compact) > max_chars:
        compact = compact[:max_chars] + "..."

    return compact


def summarize_text_file(path: Path):
    raw = safe_read_text(path)
    compact = compact_text(raw)
    if not compact:
        return ""
    return t("summarizer.text_preview", content=compact)


def summarize_json_file(path: Path):
    try:
        raw = safe_read_text(path)
        data = json.loads(raw)

        if isinstance(data, dict):
            keys = list(data.keys())[:20]
            return t("summarizer.json_object", keys=keys)

        if isinstance(data, list):
            first_type = type(data[0]).__name__ if data else "empty"
            return t("summarizer.json_array", length=len(data), first_type=first_type)

        return t("summarizer.json_type", type_name=type(data).__name__)
    except Exception:
        return summarize_text_file(path)


def summarize_docx_file(path: Path):
    try:
        texts = []

        with zipfile.ZipFile(path) as z:
            if "word/document.xml" not in z.namelist():
                return ""

            xml_content = z.read("word/document.xml")
            root = ElementTree.fromstring(xml_content)
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

            for node in root.findall(".//w:t", namespace):
                if node.text:
                    texts.append(node.text)

        content = compact_text(" ".join(texts))
        if not content:
            return ""

        return t("summarizer.docx_preview", content=content)
    except Exception:
        return ""


def summarize_code_project_file(path: Path):
    name = path.name.lower()

    try:
        if name == "package.json":
            raw = safe_read_text(path)
            data = json.loads(raw)
            project_name = data.get("name", "")
            scripts = list(data.get("scripts", {}).keys())[:10]
            deps = list(data.get("dependencies", {}).keys())[:15]
            dev_deps = list(data.get("devDependencies", {}).keys())[:15]
            return t(
                "summarizer.package_json",
                project_name=project_name,
                scripts=scripts,
                deps=deps,
                dev_deps=dev_deps,
            )

        if name == "requirements.txt":
            raw = safe_read_text(path)
            lines = [
                line.strip()
                for line in raw.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            return t("summarizer.requirements", items=lines[:20])

        if name == "pyproject.toml":
            return t("summarizer.pyproject")

        if name == "pom.xml":
            return t("summarizer.pom")

        if name == "build.gradle":
            return t("summarizer.gradle")

        if name == "readme.md":
            return summarize_text_file(path)
    except Exception:
        pass

    return ""


def summarize_file_content(path):
    path = Path(path)
    if not path.exists() or not path.is_file():
        return ""

    suffix = path.suffix.lower()

    try:
        size_mb = path.stat().st_size / 1024 / 1024
        if size_mb > 20:
            return t("summarizer.large_file_skip", size_mb=f"{size_mb:.1f}")
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
        return t("summarizer.pdf_note")

    if suffix in [".ppt", ".pptx"]:
        return t("summarizer.ppt_note")

    if suffix in [".xls", ".xlsx"]:
        return t("summarizer.excel_note")

    return ""


def summarize_folder_content(folder_path, max_items=80, max_content_files=8):
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
        "total_sampled": 0,
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
                        summary["content_hints"].append({"file": name, "summary": content_summary})
                        content_count += 1
    except Exception as exc:
        summary["error"] = str(exc)

    summary["total_sampled"] = count
    summary["subfolders"] = summary["subfolders"][:30]
    return summary
