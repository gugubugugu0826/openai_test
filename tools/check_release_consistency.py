import re
import sys
from pathlib import Path

# Allow running directly (python tools/check_release_consistency.py) or as a module.
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from desktop_agent.version import APP_EXE_NAME, APP_VERSION


README_PATH = PROJECT_DIR / "README.md"
BUILD_RELEASE_PATH = PROJECT_DIR / "build_release.py"
APP_UI_PATH = PROJECT_DIR / "desktop_agent_ui" / "app.py"
LOGS_UI_PATH = PROJECT_DIR / "desktop_agent_ui" / "pages_logs.py"
CI_WORKFLOW_PATH = PROJECT_DIR / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW_PATH = PROJECT_DIR / ".github" / "workflows" / "release.yml"


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
    ci_workflow = read_text(CI_WORKFLOW_PATH)
    release_workflow = read_text(RELEASE_WORKFLOW_PATH)

    require(release_zip in readme, f"README.md does not mention the current release zip name: {release_zip}", failures)
    require(release_dir in readme, f"README.md does not mention the current release directory name: {release_dir}", failures)
    require(f"version-{APP_VERSION}-blue" in readme, f"README.md badge is not updated to {APP_VERSION}", failures)

    require('APP_EXE_NAME = "QwenDesktopAgent"' in build_release, "build_release.py fallback APP_EXE_NAME is unexpected", failures)
    require(f'APP_VERSION = "{APP_VERSION}"' in build_release, f"build_release.py fallback APP_VERSION is not aligned to {APP_VERSION}", failures)
    require('APP_NAME = APP_EXE_NAME' in build_release, "build_release.py does not derive APP_NAME from APP_EXE_NAME", failures)
    require('VERSION = APP_VERSION' in build_release, "build_release.py does not derive VERSION from APP_VERSION", failures)
    require('RELEASE_DIR = PROJECT_DIR / f"{APP_NAME}_{VERSION}"' in build_release, "build_release.py release directory naming rule is unexpected", failures)

    require(f'APP_VERSION = "{APP_VERSION}"' in app_ui, f"desktop_agent_ui/app.py fallback APP_VERSION is not aligned to {APP_VERSION}", failures)
    require(f'APP_VERSION = "{APP_VERSION}"' in logs_ui, f"desktop_agent_ui/pages_logs.py fallback APP_VERSION is not aligned to {APP_VERSION}", failures)

    require("actions/checkout@v5" in ci_workflow, "ci.yml is not upgraded to actions/checkout@v5", failures)
    require("actions/setup-python@v6" in ci_workflow, "ci.yml is not upgraded to actions/setup-python@v6", failures)
    require("actions/upload-artifact@v5" in ci_workflow, "ci.yml is not upgraded to actions/upload-artifact@v5", failures)
    require("runs-on: windows-2025" in ci_workflow, "ci.yml is not pinned to windows-2025", failures)

    require("actions/checkout@v5" in release_workflow, "release.yml is not upgraded to actions/checkout@v5", failures)
    require("actions/setup-python@v6" in release_workflow, "release.yml is not upgraded to actions/setup-python@v6", failures)
    require("actions/upload-artifact@v5" in release_workflow, "release.yml is not upgraded to actions/upload-artifact@v5", failures)
    require("runs-on: windows-2025" in release_workflow, "release.yml is not pinned to windows-2025", failures)
    require("python tools/check_release_tag.py" in release_workflow, "release.yml is missing the tag/version validation step", failures)
    require("python tools/generate_release_notes.py" in release_workflow, "release.yml is missing the release notes generation step", failures)
    require("python tools/generate_release_manifest.py" in release_workflow, "release.yml is missing the release manifest generation step", failures)
    require("body_path: release_notes.md" in release_workflow, "release.yml does not attach release_notes.md to the GitHub Release", failures)
    require("release_manifest.json" in release_workflow, "release.yml does not attach release_manifest.json", failures)
    require("release_manifest.md" in release_workflow, "release.yml does not attach release_manifest.md", failures)
    require("GITHUB_STEP_SUMMARY" in release_workflow, "release.yml does not write to the workflow summary", failures)

    stale_release_refs = sorted(
        {
            match
            for match in re.findall(rf"{re.escape(APP_EXE_NAME)}_v\d+\.\d+(?:\.\d+)?(?:\.zip)?", readme)
            if APP_VERSION not in match
        }
    )
    if stale_release_refs:
        failures.append("README.md contains stale release references: " + ", ".join(stale_release_refs))

    if failures:
        safe_print("Release consistency check failed:")
        for item in failures:
            safe_print(f"- {item}")
        raise SystemExit(1)

    safe_print("Release consistency check passed.")
    safe_print(f"- APP_EXE_NAME: {APP_EXE_NAME}")
    safe_print(f"- APP_VERSION: {APP_VERSION}")
    safe_print(f"- release_dir: {release_dir}")
    safe_print(f"- release_zip: {release_zip}")


if __name__ == "__main__":
    main()
