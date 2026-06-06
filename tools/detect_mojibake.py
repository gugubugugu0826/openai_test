from __future__ import annotations

import ast
import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_DIR / "test_reports" / "latest_mojibake_report.json"
SCAN_DIRS = [
    PROJECT_DIR / "desktop_agent_ui",
    PROJECT_DIR / "desktop_agent",
]


def try_repair_text(text: str):
    candidates = []
    for source_encoding in ("gbk", "cp936"):
        try:
            repaired = text.encode(source_encoding).decode("utf-8")
        except Exception:
            continue
        if repaired != text:
            candidates.append((source_encoding, repaired))
    return candidates


def score_text(text: str) -> int:
    score = 0
    for ch in text:
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF:
            score += 2
        elif ch.isascii() and (ch.isalnum() or ch in " .,:;!?-_()[]{}<>/\\\n\t\"'"):
            score += 1
        else:
            score -= 1
    return score


def collect_file_candidates(path: Path):
    content = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(content, filename=str(path))
    items = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        original = node.value
        repaired_candidates = try_repair_text(original)
        if not repaired_candidates:
            continue

        original_score = score_text(original)
        best = None
        for encoding_name, repaired in repaired_candidates:
            repaired_score = score_text(repaired)
            improvement = repaired_score - original_score
            if improvement <= 0:
                continue
            entry = {
                "line": getattr(node, "lineno", 0),
                "encoding": encoding_name,
                "original": original,
                "repaired": repaired,
                "score_delta": improvement,
            }
            if best is None or entry["score_delta"] > best["score_delta"]:
                best = entry

        if best:
            items.append(best)

    return items


def build_report():
    report = {"summary": {"files": 0, "candidates": 0}, "files": []}

    for base_dir in SCAN_DIRS:
        for path in sorted(base_dir.rglob("*.py")):
            report["summary"]["files"] += 1
            try:
                candidates = collect_file_candidates(path)
            except Exception as e:
                report["files"].append(
                    {
                        "file": str(path.relative_to(PROJECT_DIR)).replace("\\", "/"),
                        "error": str(e),
                        "candidates": [],
                    }
                )
                continue

            if not candidates:
                continue

            report["summary"]["candidates"] += len(candidates)
            report["files"].append(
                {
                    "file": str(path.relative_to(PROJECT_DIR)).replace("\\", "/"),
                    "candidates": candidates,
                }
            )

    return report


def main():
    report = build_report()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"mojibake report written to: {OUTPUT_FILE}")
    print(
        f"files_scanned={report['summary']['files']}, candidates={report['summary']['candidates']}"
    )


if __name__ == "__main__":
    main()
