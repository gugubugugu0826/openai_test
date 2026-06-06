import hashlib
import json
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from desktop_agent.version import APP_EXE_NAME, APP_VERSION


RELEASE_DIR = PROJECT_DIR / f"{APP_EXE_NAME}_{APP_VERSION}"
ZIP_PATH = PROJECT_DIR / f"{APP_EXE_NAME}_{APP_VERSION}.zip"
JSON_PATH = PROJECT_DIR / "release_manifest.json"
MD_PATH = PROJECT_DIR / "release_manifest.md"


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_key_files():
    candidates = [
        RELEASE_DIR / f"{APP_EXE_NAME}.exe",
        RELEASE_DIR / "config.json",
        RELEASE_DIR / "agent_memory.json",
        RELEASE_DIR / "README_使用说明.txt",
        RELEASE_DIR / "runtime" / "llama-server.exe",
    ]
    files = []
    for path in candidates:
        files.append(
            {
                "path": str(path.relative_to(PROJECT_DIR)) if path.exists() else str(path.relative_to(PROJECT_DIR)),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
            }
        )
    return files


def main():
    if not RELEASE_DIR.exists():
        raise SystemExit(f"找不到发布目录：{RELEASE_DIR}")
    if not ZIP_PATH.exists():
        raise SystemExit(f"找不到发布压缩包：{ZIP_PATH}")

    manifest = {
        "app_name": APP_EXE_NAME,
        "version": APP_VERSION,
        "release_dir": RELEASE_DIR.name,
        "zip_name": ZIP_PATH.name,
        "zip_size_bytes": ZIP_PATH.stat().st_size,
        "zip_sha256": sha256_of(ZIP_PATH),
        "key_files": collect_key_files(),
    }

    JSON_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# {APP_EXE_NAME} {APP_VERSION} Release Manifest",
        "",
        f"- release_dir: `{manifest['release_dir']}`",
        f"- zip_name: `{manifest['zip_name']}`",
        f"- zip_size_bytes: `{manifest['zip_size_bytes']}`",
        f"- zip_sha256: `{manifest['zip_sha256']}`",
        "",
        "## Key Files",
        "",
    ]
    for item in manifest["key_files"]:
        state = "OK" if item["exists"] else "MISSING"
        size_text = str(item["size_bytes"]) if item["size_bytes"] is not None else "-"
        lines.append(f"- `{state}` `{item['path']}` size={size_text}")

    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Release manifest written to: {JSON_PATH}")
    print(f"Release manifest markdown written to: {MD_PATH}")


if __name__ == "__main__":
    main()
