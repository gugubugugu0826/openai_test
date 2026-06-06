import re
import sys
from pathlib import Path

# Allow running directly (python tools/check_release_consistency.py) or as a module
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from desktop_agent.version import APP_EXE_NAME, APP_VERSION


PROJECT_DIR = Path(__file__).resolve().parent.parent
README_PATH = PROJECT_DIR / "README.md"
BUILD_RELEASE_PATH = PROJECT_DIR / "build_release.py"
APP_UI_PATH = PROJECT_DIR / "desktop_agent_ui" / "app.py"
LOGS_UI_PATH = PROJECT_DIR / "desktop_agent_ui" / "pages_logs.py"


def require(condition, message, failures):
    if not condition:
        failures.append(message)


def safe_print(message):
    text = str(message)
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.buffer.write(text.encode(encoding, errors="replace") + b"\n")


def read_text(path):
    return path.read_text(encoding="utf-8")


def main():
    failures = []

    release_zip = f"{APP_EXE_NAME}_{APP_VERSION}.zip"
    release_dir = f"{APP_EXE_NAME}_{APP_VERSION}"

    readme = read_text(README_PATH)
    build_release = read_text(BUILD_RELEASE_PATH)
    app_ui = read_text(APP_UI_PATH)
    logs_ui = read_text(LOGS_UI_PATH)

    require(release_zip in readme, f"README.md 未包含当前发布 zip 名称：{release_zip}", failures)
    require(release_dir in readme, f"README.md 未包含当前发布目录名称：{release_dir}", failures)
    require(f"version-{APP_VERSION}-blue" in readme, f"README.md 顶部版本徽章未更新到 {APP_VERSION}", failures)

    require('APP_EXE_NAME = "QwenDesktopAgent"' in build_release, "build_release.py fallback APP_EXE_NAME 异常", failures)
    require(f'APP_VERSION = "{APP_VERSION}"' in build_release, f"build_release.py fallback APP_VERSION 未对齐到 {APP_VERSION}", failures)
    require('APP_NAME = APP_EXE_NAME' in build_release, "build_release.py 未从 APP_EXE_NAME 派生 APP_NAME", failures)
    require('VERSION = APP_VERSION' in build_release, "build_release.py 未从 APP_VERSION 派生 VERSION", failures)
    require('RELEASE_DIR = PROJECT_DIR / f"{APP_NAME}_{VERSION}"' in build_release, "build_release.py 发布目录命名规则异常", failures)

    require(f'APP_VERSION = "{APP_VERSION}"' in app_ui, f"desktop_agent_ui/app.py fallback APP_VERSION 未对齐到 {APP_VERSION}", failures)
    require(f'APP_VERSION = "{APP_VERSION}"' in logs_ui, f"desktop_agent_ui/pages_logs.py fallback APP_VERSION 未对齐到 {APP_VERSION}", failures)

    stale_release_refs = sorted(
        {
            match
            for match in re.findall(rf"{re.escape(APP_EXE_NAME)}_v\d+\.\d+(?:\.\d+)?(?:\.zip)?", readme)
            if APP_VERSION not in match and not match.endswith("v2.1.zip")
        }
    )
    if stale_release_refs:
        failures.append("README.md 含疑似过期的发布命名引用：" + ", ".join(stale_release_refs))

    if failures:
        safe_print("版本/README/发布命名一致性检查失败：")
        for item in failures:
            safe_print(f"- {item}")
        raise SystemExit(1)

    safe_print("版本/README/发布命名一致性检查通过。")
    safe_print(f"- APP_EXE_NAME: {APP_EXE_NAME}")
    safe_print(f"- APP_VERSION: {APP_VERSION}")
    safe_print(f"- release_dir: {release_dir}")
    safe_print(f"- release_zip: {release_zip}")


if __name__ == "__main__":
    main()
