import locale
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


def run_step(name, command):
    try:
        env = dict(__import__("os").environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        completed = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            capture_output=True,
            env=env,
        )
        stdout = decode_output(completed.stdout)
        stderr = decode_output(completed.stderr)
        return {
            "name": name,
            "command": " ".join(command),
            "returncode": completed.returncode,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
        }
    except Exception as e:
        return {
            "name": name,
            "command": " ".join(command),
            "returncode": 999,
            "stdout": "",
            "stderr": f"测试脚本执行该步骤时自身报错：{e}",
        }


def decode_output(data):
    if data is None:
        return ""
    if isinstance(data, str):
        return data

    encodings = [
        locale.getpreferredencoding(False),
        "utf-8",
        "gbk",
        "cp936",
    ]
    for encoding in encodings:
        if not encoding:
            continue
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def format_block(text):
    text = (text or "").strip()
    return text if text else "(无输出)"


def build_report(results):
    failed = [result for result in results if result["returncode"] != 0]
    passed = len(results) - len(failed)

    lines = []
    lines.append("# 自动化测试报告")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 项目路径：`{PROJECT_DIR}`")
    lines.append(f"- 通过步骤：{passed}")
    lines.append(f"- 失败步骤：{len(failed)}")
    lines.append("")

    lines.append("## 结果汇总")
    lines.append("")
    for result in results:
        status = "PASS" if result["returncode"] == 0 else "FAIL"
        lines.append(f"- `{status}` {result['name']}")
    lines.append("")

    if failed:
        lines.append("## 缺陷清单")
        lines.append("")
        for idx, result in enumerate(failed, start=1):
            lines.append(f"### Bug {idx} - {result['name']}")
            lines.append("")
            lines.append(f"- 失败命令：`{result['command']}`")
            lines.append(f"- 返回码：`{result['returncode']}`")
            lines.append("- 现象：命令执行失败，请查看下方输出。")
            lines.append("- 建议：优先修复该步骤对应的模块，再重新执行本测试脚本。")
            lines.append("")
            lines.append("#### 标准输出")
            lines.append("")
            lines.append("```text")
            lines.append(format_block(result["stdout"]))
            lines.append("```")
            lines.append("")
            lines.append("#### 错误输出")
            lines.append("")
            lines.append("```text")
            lines.append(format_block(result["stderr"]))
            lines.append("```")
            lines.append("")
    else:
        lines.append("## 当前结论")
        lines.append("")
        lines.append("- 这轮自动化基线测试全部通过。")
        lines.append("- 仍建议补做手工测试：GUI 交互、实际文件移动、更新下载、打包后的 exe 运行。")
        lines.append("")

    lines.append("## 每步详细输出")
    lines.append("")
    for result in results:
        status = "PASS" if result["returncode"] == 0 else "FAIL"
        lines.append(f"### {status} - {result['name']}")
        lines.append("")
        lines.append(f"- 命令：`{result['command']}`")
        lines.append("")
        lines.append("#### 标准输出")
        lines.append("")
        lines.append("```text")
        lines.append(format_block(result["stdout"]))
        lines.append("```")
        lines.append("")
        lines.append("#### 错误输出")
        lines.append("")
        lines.append("```text")
        lines.append(format_block(result["stderr"]))
        lines.append("```")
        lines.append("")

    return "\n".join(lines), 1 if failed else 0


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    steps = [
        ("版本一致性检查", [sys.executable, "tools/check_release_consistency.py"]),
        ("编译检查", [sys.executable, "-m", "compileall", "-f", "desktop_agent", "desktop_agent_ui", "desktop_agent_gui.py", "desktop_agent_cli.py"]),
        ("单元测试", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("GUI 构建烟测", [sys.executable, "-c", "import customtkinter as ctk; from desktop_agent_ui.app import DesktopAgentGUI; root=ctk.CTk(); root.withdraw(); app=DesktopAgentGUI(root); print('built'); root.destroy()"]),
        ("CLI 帮助烟测", [sys.executable, "desktop_agent_cli.py", "-h"]),
    ]

    results = [run_step(name, command) for name, command in steps]
    content, exit_code = build_report(results)
    REPORT_FILE.write_text(content, encoding="utf-8")
    safe_print(f"Test report written to: {REPORT_FILE}")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
