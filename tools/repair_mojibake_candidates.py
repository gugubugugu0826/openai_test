from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
REPORT_FILE = PROJECT_DIR / "test_reports" / "latest_mojibake_report.json"
OUTPUT_FILE = PROJECT_DIR / "test_reports" / "latest_mojibake_patch_plan.json"


def load_report():
    if not REPORT_FILE.exists():
        raise FileNotFoundError(f"Report not found: {REPORT_FILE}")
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def replace_string_literals(content: str, replacements: dict[int, tuple[str, str]]):
    tree = ast.parse(content)
    segments = []
    cursor = 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        line_no = getattr(node, "lineno", 0)
        if line_no not in replacements:
            continue

        original, repaired = replacements[line_no]
        segment = ast.get_source_segment(content, node)
        if not segment:
            continue
        if node.value != original:
            continue

        start = node.col_offset
        end = node.end_col_offset
        line_start = content.rfind("\n", 0, content.find(segment, cursor)) + 1
        abs_start = line_start + start
        abs_end = line_start + end
        new_literal = repr(repaired)
        segments.append((abs_start, abs_end, new_literal))

    if not segments:
        return content

    segments.sort(key=lambda item: item[0])
    rebuilt = []
    cursor = 0
    for start, end, replacement in segments:
        rebuilt.append(content[cursor:start])
        rebuilt.append(replacement)
        cursor = end
    rebuilt.append(content[cursor:])
    return "".join(rebuilt)


def main():
    parser = argparse.ArgumentParser(description="Apply mojibake repair candidates from the latest report.")
    parser.add_argument("--apply", action="store_true", help="Apply repairs in place.")
    args = parser.parse_args()

    report = load_report()
    patch_plan = []

    for file_entry in report.get("files", []):
        if not file_entry.get("candidates"):
            continue
        path = PROJECT_DIR / file_entry["file"]
        replacements = {
            candidate["line"]: (candidate["original"], candidate["repaired"])
            for candidate in file_entry["candidates"]
        }
        patch_plan.append(
            {
                "file": file_entry["file"],
                "count": len(replacements),
                "lines": sorted(replacements.keys()),
            }
        )
        if not args.apply:
            continue

        content = path.read_text(encoding="utf-8-sig")
        updated = replace_string_literals(content, replacements)
        path.write_text(updated, encoding="utf-8")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"apply": args.apply, "files": patch_plan}, f, ensure_ascii=False, indent=2)

    print(f"mojibake patch plan written to: {OUTPUT_FILE}")
    print(f"files_with_candidates={len(patch_plan)}, apply={args.apply}")


if __name__ == "__main__":
    main()
