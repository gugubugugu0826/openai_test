import locale
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_DIR / "test_reports"
REPORT_FILE = REPORT_DIR / "latest_test_report.md"


def safe_print(message):
    text = str(message)
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or locale.getpreferredencoding(False) or "utf-8"
        data = text.encode(encoding, errors="replace")
        sys.stdout.buffer.write(data + b"\n")


def decode_output(data):
    if data is None:
        return ""
    if isinstance(data, str):
        return data

    encodings = [
        "utf-8",
        locale.getpreferredencoding(False),
        "gbk",
        "cp936",
        "cp1252",
    ]
    for encoding in encodings:
        if not encoding:
            continue
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def run_step(name, command):
    try:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        completed = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            capture_output=True,
            env=env,
        )
        return {
            "name": name,
            "command": " ".join(command),
            "returncode": completed.returncode,
            "stdout": decode_output(completed.stdout).strip(),
            "stderr": decode_output(completed.stderr).strip(),
        }
    except Exception as exc:
        return {
            "name": name,
            "command": " ".join(command),
            "returncode": 999,
            "stdout": "",
            "stderr": f"Audit runner crashed while executing this step: {exc}",
        }


def format_block(text):
    text = (text or "").strip()
    return text if text else "(no output)"


def build_report(results):
    failed = [result for result in results if result["returncode"] != 0]
    passed = len(results) - len(failed)

    lines = [
        "# Automated Test Audit",
        "",
        f"- Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Project path: `{PROJECT_DIR}`",
        f"- Passed steps: {passed}",
        f"- Failed steps: {len(failed)}",
        "",
        "## Result Summary",
        "",
    ]

    for result in results:
        status = "PASS" if result["returncode"] == 0 else "FAIL"
        lines.append(f"- `{status}` {result['name']}")
    lines.append("")

    if failed:
        lines.extend(["## Findings", ""])
        for index, result in enumerate(failed, start=1):
            lines.extend(
                [
                    f"### Finding {index} - {result['name']}",
                    "",
                    f"- Command: `{result['command']}`",
                    f"- Exit code: `{result['returncode']}`",
                    "- Behavior: The command failed. See the captured output below.",
                    "- Next action: Fix the related module and run the audit again.",
                    "",
                    "#### Stdout",
                    "",
                    "```text",
                    format_block(result["stdout"]),
                    "```",
                    "",
                    "#### Stderr",
                    "",
                    "```text",
                    format_block(result["stderr"]),
                    "```",
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "## Current Conclusion",
                "",
                "- All baseline automated checks passed in this run.",
                "- Manual checks are still recommended for full GUI interaction, real file moves, update downloads, and packaged `.exe` behavior.",
                "",
            ]
        )

    lines.extend(["## Full Step Output", ""])
    for result in results:
        status = "PASS" if result["returncode"] == 0 else "FAIL"
        lines.extend(
            [
                f"### {status} - {result['name']}",
                "",
                f"- Command: `{result['command']}`",
                "",
                "#### Stdout",
                "",
                "```text",
                format_block(result["stdout"]),
                "```",
                "",
                "#### Stderr",
                "",
                "```text",
                format_block(result["stderr"]),
                "```",
                "",
            ]
        )

    return "\n".join(lines), 1 if failed else 0


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    steps = [
        ("Release consistency check", [sys.executable, "tools/check_release_consistency.py"]),
        ("Compile check", [sys.executable, "-m", "compileall", "-f", "desktop_agent", "desktop_agent_ui", "desktop_agent_gui.py", "desktop_agent_cli.py"]),
        ("Unit tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("GUI build smoke test", [sys.executable, "-c", "import customtkinter as ctk; from desktop_agent_ui.app import DesktopAgentGUI; root=ctk.CTk(); root.withdraw(); app=DesktopAgentGUI(root); print('built'); root.destroy()"]),
        ("CLI help smoke test", [sys.executable, "desktop_agent_cli.py", "-h"]),
    ]

    results = [run_step(name, command) for name, command in steps]
    content, exit_code = build_report(results)
    REPORT_FILE.write_text(content, encoding="utf-8")
    safe_print(f"Test report written to: {REPORT_FILE}")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
