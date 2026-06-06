from __future__ import annotations

import ast
import json
import re
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
LOCALES_DIR = PROJECT_DIR / "locales"
DEFAULT_OUTPUT = PROJECT_DIR / "test_reports" / "latest_i18n_extract.json"
CHINESE_RE = re.compile(r"[\u3400-\u9fff]")

SCAN_DIRS = [
    PROJECT_DIR / "desktop_agent_ui",
    PROJECT_DIR / "desktop_agent",
]

IGNORE_FILES = {
    PROJECT_DIR / "desktop_agent" / "i18n.py",
}


def load_locale_strings():
    zh_path = LOCALES_DIR / "zh.json"
    if not zh_path.exists():
        return set()

    with open(zh_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    keys = set()
    for bucket_name in ("translations", "categories", "substrings"):
        bucket = data.get(bucket_name, {})
        keys.update(bucket.keys())
    return keys


def is_target_file(path: Path) -> bool:
    return path.suffix == ".py" and path not in IGNORE_FILES


def classify_file(path: Path) -> str:
    if "desktop_agent_ui" in path.parts:
        return "ui"
    return "core"


def extract_strings_from_file(path: Path):
    content = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(content, filename=str(path))
    findings = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if value and CHINESE_RE.search(value):
                findings.append((node.lineno, value))
        elif isinstance(node, ast.JoinedStr):
            for value_node in node.values:
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    value = value_node.value.strip()
                    if value and CHINESE_RE.search(value):
                        findings.append((value_node.lineno, value))

    dedup = []
    seen = set()
    for line, value in findings:
        key = (line, value)
        if key not in seen:
            seen.add(key)
            dedup.append((line, value))
    return dedup


def build_report():
    known_strings = load_locale_strings()
    report = {
        "summary": {
            "ui_total": 0,
            "ui_missing": 0,
            "core_total": 0,
            "core_missing": 0,
            "all_total": 0,
            "all_missing": 0,
        },
        "items": [],
        "parse_errors": [],
    }

    for base_dir in SCAN_DIRS:
        for path in sorted(base_dir.rglob("*.py")):
            if not is_target_file(path):
                continue

            file_type = classify_file(path)
            try:
                findings = extract_strings_from_file(path)
            except Exception as e:
                report["parse_errors"].append(
                    {
                        "file": str(path.relative_to(PROJECT_DIR)).replace("\\", "/"),
                        "error": str(e),
                    }
                )
                continue

            for line, value in findings:
                exists_in_locale = value in known_strings
                item = {
                    "file": str(path.relative_to(PROJECT_DIR)).replace("\\", "/"),
                    "line": line,
                    "type": file_type,
                    "text": value,
                    "in_locale": exists_in_locale,
                }
                report["items"].append(item)
                report["summary"][f"{file_type}_total"] += 1
                if not exists_in_locale:
                    report["summary"][f"{file_type}_missing"] += 1

    report["summary"]["all_total"] = report["summary"]["ui_total"] + report["summary"]["core_total"]
    report["summary"]["all_missing"] = report["summary"]["ui_missing"] + report["summary"]["core_missing"]
    return report


def main():
    report = build_report()
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(DEFAULT_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"i18n extract written to: {DEFAULT_OUTPUT}")
    print(
        "UI: {ui_total} total / {ui_missing} missing, Core: {core_total} total / {core_missing} missing".format(
            **report["summary"]
        )
    )


if __name__ == "__main__":
    main()
