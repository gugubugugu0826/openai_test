# desktop_agent/updater.py

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from desktop_agent.version import APP_VERSION


DEFAULT_UPDATE_DIR = "updates"


def parse_version(version):
    text = str(version or "").strip().lower()
    text = text.lstrip("v")
    numbers = [int(part) for part in re.findall(r"\d+", text)]

    while len(numbers) < 3:
        numbers.append(0)

    return tuple(numbers[:3])


def is_newer_version(remote_version, current_version=APP_VERSION):
    return parse_version(remote_version) > parse_version(current_version)


def fetch_update_manifest(manifest_url, timeout=20):
    manifest_url = str(manifest_url or "").strip()

    if not manifest_url:
        raise ValueError("请先在设置里填写更新清单地址 update_manifest_url")

    response = requests.get(manifest_url, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, dict):
        raise ValueError("更新清单格式错误：根节点必须是 JSON 对象")

    if data.get("tag_name") and isinstance(data.get("assets"), list):
        data = normalize_github_release_manifest(data)

    version = str(data.get("version", "")).strip()
    package_url = (
        data.get("package_url")
        or data.get("download_url")
        or data.get("url")
        or ""
    )
    package_url = str(package_url).strip()

    if not version:
        raise ValueError("更新清单缺少 version")

    if not package_url:
        raise ValueError("更新清单缺少 package_url")

    data["version"] = version
    data["package_url"] = package_url
    return data


def normalize_github_release_manifest(data):
    assets = data.get("assets") or []
    zip_assets = [
        asset
        for asset in assets
        if str(asset.get("name", "")).lower().endswith(".zip")
        and asset.get("browser_download_url")
    ]

    if not zip_assets:
        raise ValueError("GitHub Release 里没有找到 .zip 更新包")

    asset = zip_assets[0]
    digest = str(asset.get("digest") or "").strip()
    sha256 = digest.removeprefix("sha256:") if digest.startswith("sha256:") else ""

    return {
        "version": str(data.get("tag_name", "")).strip(),
        "package_url": str(asset.get("browser_download_url", "")).strip(),
        "package_name": str(asset.get("name", "")).strip(),
        "sha256": sha256,
        "notes": str(data.get("body") or "").strip(),
        "source": "github_releases_latest",
    }


def get_package_filename(manifest):
    filename = str(manifest.get("package_name") or "").strip()

    if filename:
        return filename

    parsed = urlparse(manifest["package_url"])
    filename = Path(parsed.path).name

    if filename:
        return filename

    return f"QwenDesktopAgent_{manifest['version']}.zip"


def download_update_package(manifest, target_dir, progress_callback=None, cancel_flag=None):
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / get_package_filename(manifest)
    part = target.with_name(target.name + ".part")
    sha256_expected = str(manifest.get("sha256") or "").strip().lower()
    hasher = hashlib.sha256()

    with requests.get(manifest["package_url"], stream=True, timeout=(20, 60)) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", 0)) or 0
        done = 0

        with open(part, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if cancel_flag and cancel_flag.get("cancel"):
                    raise RuntimeError("已取消下载")

                if not chunk:
                    continue

                f.write(chunk)
                hasher.update(chunk)
                done += len(chunk)

                if progress_callback:
                    progress_callback(done, total)

    sha256_actual = hasher.hexdigest()

    if sha256_expected and sha256_actual != sha256_expected:
        try:
            part.unlink(missing_ok=True)
        except Exception:
            pass
        raise ValueError(
            "更新包校验失败：sha256 不一致\n"
            f"期望：{sha256_expected}\n"
            f"实际：{sha256_actual}"
        )

    if target.exists():
        target.unlink()

    part.rename(target)
    return target, sha256_actual


def check_for_update(manifest_url, current_version=APP_VERSION):
    manifest = fetch_update_manifest(manifest_url)
    manifest["current_version"] = current_version
    manifest["has_update"] = is_newer_version(manifest["version"], current_version)
    return manifest
