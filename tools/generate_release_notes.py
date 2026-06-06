import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from desktop_agent.version import APP_EXE_NAME, APP_VERSION


REPORT_PATH = PROJECT_DIR / "test_reports" / "latest_test_report.md"
OUTPUT_PATH = PROJECT_DIR / "release_notes.md"


def parse_test_summary():
    if not REPORT_PATH.exists():
        return {
            "passed_steps": "未知",
            "failed_steps": "未知",
            "summary_lines": ["- 未找到测试报告，请检查 CI 产物。"],
        }

    content = REPORT_PATH.read_text(encoding="utf-8")
    passed_match = re.search(r"- 通过步骤：(.+)", content)
    failed_match = re.search(r"- 失败步骤：(.+)", content)
    summary_lines = []
    in_summary = False
    for line in content.splitlines():
        if line.strip() == "## 结果汇总":
            in_summary = True
            continue
        if in_summary:
            if line.startswith("## "):
                break
            if line.strip().startswith("- `"):
                summary_lines.append(line.strip())

    return {
        "passed_steps": passed_match.group(1).strip() if passed_match else "未知",
        "failed_steps": failed_match.group(1).strip() if failed_match else "未知",
        "summary_lines": summary_lines or ["- 未解析到测试摘要。"],
    }


def run_git_command(args):
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except Exception:
        return ""


def build_changelog_lines():
    previous_tag = run_git_command(["describe", "--tags", "--abbrev=0", "HEAD^"])
    if previous_tag:
        log_text = run_git_command(["log", "--oneline", f"{previous_tag}..HEAD"])
    else:
        log_text = run_git_command(["log", "--oneline", "-n", "10"])

    if not log_text:
        return ["- 未获取到最近提交记录。"]

    lines = []
    for raw in log_text.splitlines():
        parts = raw.strip().split(" ", 1)
        if len(parts) == 2:
            commit_sha, message = parts
            lines.append(f"- `{commit_sha}` {message}")
        else:
            lines.append(f"- {raw.strip()}")
    return lines[:12]


def main():
    summary = parse_test_summary()
    changelog_lines = build_changelog_lines()
    zip_name = f"{APP_EXE_NAME}_{APP_VERSION}.zip"
    release_dir = f"{APP_EXE_NAME}_{APP_VERSION}"

    lines = [
        f"# {APP_EXE_NAME} {APP_VERSION}",
        "",
        f"- 构建时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"- 发布目录：`{release_dir}`",
        f"- 发布压缩包：`{zip_name}`",
        f"- 测试通过步骤：`{summary['passed_steps']}`",
        f"- 测试失败步骤：`{summary['failed_steps']}`",
        "",
        "## 自动化测试摘要",
        "",
        *summary["summary_lines"],
        "",
        "## 本次变更摘要",
        "",
        *changelog_lines,
        "",
        "## 附件",
        "",
        f"- `{zip_name}`",
        "- `test_reports/latest_test_report.md`",
        "- `release_notes.md`",
        "- `release_manifest.json`",
        "- `release_manifest.md`",
        "",
        "## 使用方式",
        "",
        "1. 下载 zip 并解压。",
        f"2. 双击 `{APP_EXE_NAME}.exe`。",
        "3. 首次运行按引导选择整理目录和分类模式。",
    ]

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Release notes written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
