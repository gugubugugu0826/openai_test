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

IGNORE_TEXT_EXACT = {
    "README_使用说明.txt",
    "99_其他快捷方式",
    "无法",
}

IGNORE_ASSIGN_TARGETS = {
    "DEFAULT_MEMORY",
    "CATEGORIES",
    "SHORTCUT_CATEGORY_FOLDERS",
    "NORMAL_CATEGORY_FOLDERS",
}


def load_locale_strings():
    keys = set()
    for zh_path in sorted(LOCALES_DIR.glob("zh*.json")):
        with open(zh_path, "r", encoding="utf-8") as f:
            data = json.load(f)
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
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    ignored_docstring_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                ignored_docstring_nodes.add(first.value)

    ignored_assignment_values = set()
    ignored_function_bodies = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            target_names = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if target_names & IGNORE_ASSIGN_TARGETS:
                ignored_assignment_values.add(node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in {"build_classification_prompt"}:
                ignored_function_bodies.add(node)

    findings = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if node in ignored_docstring_nodes:
                continue
            if value in IGNORE_TEXT_EXACT:
                continue
            if value and CHINESE_RE.search(value):
                skip = False
                parent = parents.get(node)
                while parent is not None:
                    if parent in ignored_assignment_values:
                        skip = True
                        break
                    if parent in ignored_function_bodies:
                        skip = True
                        break
                    if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == "contains_any":
                        skip = True
                        break
                    parent = parents.get(parent)
                if skip:
                    continue
                findings.append((node.lineno, value))
        elif isinstance(node, ast.JoinedStr):
            for value_node in node.values:
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    value = value_node.value.strip()
                    if value in IGNORE_TEXT_EXACT:
                        continue
                    if value and CHINESE_RE.search(value):
                        skip = False
                        parent = parents.get(node)
                        while parent is not None:
                            if parent in ignored_assignment_values:
                                skip = True
                                break
                            if parent in ignored_function_bodies:
                                skip = True
                                break
                            if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == "contains_any":
                                skip = True
                                break
                            parent = parents.get(parent)
                        if skip:
                            continue
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
