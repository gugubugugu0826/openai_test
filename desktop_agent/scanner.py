# desktop_agent/scanner.py

from pathlib import Path

from desktop_agent.config import load_config
from desktop_agent.storage import save_json
from desktop_agent.state import now_str, update_state
from desktop_agent.content_summarizer import summarize_file_content, summarize_folder_content


OBSERVATION_FILE = "desktop_observation.json"


def get_public_desktop_path():
    return Path(Path.home().anchor) / "Users" / "Public" / "Desktop"


def get_scan_roots(config=None):
    """
    Return the first-level desktop folders to scan.

    Windows Shell shows a merged desktop made from the current user's Desktop
    plus C:\\Users\\Public\\Desktop. When desktop_path is left empty, match that
    Shell view. If the user configures desktop_path explicitly, treat it as a
    custom single-folder scan for testing or narrow cleanup.
    """
    config = config or load_config()

    if not config.get("_desktop_path_was_empty", False):
        return [Path(config["desktop_path"])]

    roots = [Path(config["desktop_path"])]
    public_desktop = get_public_desktop_path()

    if public_desktop.exists():
        roots.append(public_desktop)

    unique_roots = []
    seen = set()

    for root in roots:
        try:
            key = str(root.resolve()).lower()
        except Exception:
            key = str(root).lower()

        if key in seen:
            continue

        seen.add(key)
        unique_roots.append(root)

    return unique_roots


def check_scan_path_safety(desktop: Path):
    """
    Guard against scanning very broad paths such as drive roots or the user home.
    """
    path = desktop.resolve()
    home = Path.home().resolve()

    dangerous_paths = []

    for drive in ["C:\\", "D:\\", "E:\\", "F:\\"]:
        try:
            dangerous_paths.append(Path(drive).resolve())
        except Exception:
            pass

    dangerous_paths.append(home)

    for dangerous in dangerous_paths:
        try:
            if path == dangerous:
                raise RuntimeError(
                    f"扫描路径过大或过危险：{path}\n"
                    "请在 config.json 中设置 desktop_path 为桌面、测试文件夹或更小范围目录。"
                )
        except RuntimeError:
            raise
        except Exception:
            pass

    if len(path.parts) <= 2:
        raise RuntimeError(
            f"扫描路径层级过浅，可能过大：{path}\n"
            "请设置为更具体的文件夹。"
        )


def is_shortcut(path: Path):
    return path.suffix.lower() in [".lnk", ".url"]


def build_base_item(path: Path, desktop_root: Path):
    item_type = "file"

    if path.is_dir():
        item_type = "folder"
    elif is_shortcut(path):
        item_type = "shortcut"

    return {
        "path": str(path),
        "name": path.name,
        "display_name": path.stem,
        "suffix": path.suffix.lower(),
        "type": item_type,
        "desktop_root": str(desktop_root),
    }


def scan_desktop():
    config = load_config()

    desktop_roots = get_scan_roots(config)
    max_internal = config.get("max_internal_items_per_folder", 200)

    for desktop in desktop_roots:
        if not desktop.exists():
            raise FileNotFoundError(f"桌面路径不存在：{desktop}")

        if not desktop.is_dir():
            raise NotADirectoryError(f"扫描路径不是文件夹：{desktop}")

        check_scan_path_safety(desktop)

    print("=" * 80)
    print("步骤 1 - 感知：扫描桌面")
    print("=" * 80)
    print("扫描目录：")
    for desktop in desktop_roots:
        print(f"- {desktop}")
    print("扫描方式：只扫描第一层项目；文件夹内部仅生成摘要，不单独分类内部文件。")
    print("=" * 80)

    items = []
    seen_paths = set()

    for desktop in desktop_roots:
        for path in sorted(desktop.iterdir(), key=lambda p: p.name.lower()):
            try:
                try:
                    path_key = str(path.resolve()).lower()
                except Exception:
                    path_key = str(path).lower()

                if path_key in seen_paths:
                    continue

                seen_paths.add(path_key)
                item = build_base_item(path, desktop)

                if item["type"] == "file":
                    content_summary = summarize_file_content(path)
                    item["content_summary"] = content_summary

                    if content_summary:
                        print(f"读取文件内容摘要：{path.name}")

                elif item["type"] == "folder":
                    print(f"读取文件夹摘要：{path.name}")
                    folder_summary = summarize_folder_content(
                        path,
                        max_items=max_internal,
                        max_content_files=8
                    )
                    item["folder_summary"] = folder_summary

                elif item["type"] == "shortcut":
                    item["content_summary"] = ""

                items.append(item)

            except Exception as e:
                items.append({
                    "path": str(path),
                    "name": path.name,
                    "display_name": path.stem,
                    "suffix": path.suffix.lower(),
                    "type": "unknown",
                    "desktop_root": str(desktop),
                    "scan_error": str(e)
                })

    observation = {
        "created_at": now_str(),
        "desktop_path": str(desktop_roots[0]) if desktop_roots else "",
        "desktop_paths": [str(root) for root in desktop_roots],
        "scan_mode": "merged_desktop_first_level_with_light_content_summary",
        "items_count": len(items),
        "items": items
    }

    save_json(OBSERVATION_FILE, observation)

    print("")
    print(f"扫描完成：{len(items)} 个桌面第一层项目")
    print(f"观察结果已保存：{OBSERVATION_FILE}")

    update_state(
        "last_scan_at",
        f"扫描完成：{len(items)} 个第一层项目，路径："
        f"{', '.join(str(root) for root in desktop_roots)}"
    )
