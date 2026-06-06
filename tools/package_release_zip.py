import zipfile
from pathlib import Path

from desktop_agent.version import APP_EXE_NAME, APP_VERSION


PROJECT_DIR = Path(__file__).resolve().parent.parent
RELEASE_DIR = PROJECT_DIR / f"{APP_EXE_NAME}_{APP_VERSION}"
ZIP_PATH = PROJECT_DIR / f"{APP_EXE_NAME}_{APP_VERSION}.zip"


def main():
    if not RELEASE_DIR.exists() or not RELEASE_DIR.is_dir():
        raise SystemExit(f"找不到发布目录：{RELEASE_DIR}\n请先运行：python build_release.py")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zipf:
        for path in RELEASE_DIR.rglob("*"):
            if path.is_file():
                zipf.write(path, path.relative_to(PROJECT_DIR))

    print(f"发布压缩包已生成：{ZIP_PATH}")


if __name__ == "__main__":
    main()
