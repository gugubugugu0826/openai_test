from __future__ import annotations

from pathlib import Path

from desktop_agent.config import load_config
from desktop_agent.content_summarizer import summarize_file_content, summarize_folder_content
from desktop_agent.i18n import t
from desktop_agent.incremental_scanner import save_snapshot, scan_incremental_or_full
from desktop_agent.source_manager import Source, get_enabled_sources, validate_source_path
from desktop_agent.state import now_str, update_state
from desktop_agent.storage import save_json


OBSERVATION_FILE = "desktop_observation.json"


def get_public_desktop_path():
    return Path(Path.home().anchor) / "Users" / "Public" / "Desktop"


def get_scan_roots(config=None):
    """
    Return the first-level desktop folders to scan (legacy single-source path).

    Windows Shell shows a merged desktop made from the current user's Desktop
    plus C:\\Users\\Public\\Desktop. When desktop_path is left empty, match that
    Shell view. If the user configures desktop_path explicitly, treat it as a
    custom single-folder scan.
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


def check_scan_path_safety(desktop: Path, source_id: str = "desktop"):
    path = desktop.resolve()
    home = Path.home().resolve()

    dangerous_paths = []
    for drive in ["C:\\", "D:\\", "E:\\", "F:\\"]:
        try:
            dangerous_paths.append(Path(drive).resolve())
        except Exception:
            pass
    dangerous_paths.append(home)

    # Only block home directory for desktop source; allow sub-dirs for other sources
    check_home = (source_id == "desktop")

    for dangerous in dangerous_paths:
        if not check_home and dangerous == home:
            continue
        try:
            if path == dangerous:
                raise RuntimeError(t("scanner.path_too_broad", path=path))
        except RuntimeError:
            raise
        except Exception:
            pass

    if len(path.parts) <= 2:
        raise RuntimeError(t("scanner.path_too_shallow", path=path))


def is_shortcut(path: Path):
    return path.suffix.lower() in [".lnk", ".url"]


def build_base_item(path: Path, desktop_root: Path, source_id: str = "desktop"):
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
        "source_id": source_id,
    }


def _scan_single_root(root: Path, source_id: str, max_internal: int) -> list[dict]:
    """Scan one directory root and return item list."""
    items = []
    for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        try:
            item = build_base_item(path, root, source_id)

            if item["type"] == "file":
                content_summary = summarize_file_content(path)
                item["content_summary"] = content_summary
                if content_summary:
                    print(t("scanner.file_summary", name=path.name))
            elif item["type"] == "folder":
                print(t("scanner.folder_summary", name=path.name))
                folder_summary = summarize_folder_content(path, max_items=max_internal, max_content_files=8)
                item["folder_summary"] = folder_summary
            elif item["type"] == "shortcut":
                item["content_summary"] = ""

            items.append(item)
        except Exception as exc:
            items.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "display_name": path.stem,
                    "suffix": path.suffix.lower(),
                    "type": "unknown",
                    "desktop_root": str(root),
                    "source_id": source_id,
                    "scan_error": str(exc),
                }
            )
    return items


def scan_source(source: Source, max_internal: int = 200, merge_public: bool | None = None) -> list[dict]:
    """
    Scan a single Source and return all top-level items.
    Handles incremental filtering and snapshot saving.
    Desktop source additionally merges with Public Desktop when path is empty.

    merge_public:
        None  → legacy heuristic (merge when id=="desktop" and path is empty)
        True  → always merge Public Desktop
        False → never merge
    """
    root = source.resolved_path

    if not root.exists():
        raise FileNotFoundError(t("scanner.desktop_missing", path=root))
    if not root.is_dir():
        raise NotADirectoryError(t("scanner.path_not_folder", path=root))
    check_scan_path_safety(root, source.id)

    if merge_public is None:
        merge_public = (source.id == "desktop" and not source.path)

    # For desktop source with empty path, also scan Public Desktop
    roots_to_scan: list[Path] = [root]
    if merge_public:
        public = get_public_desktop_path()
        if public.exists() and str(public.resolve()).lower() != str(root.resolve()).lower():
            roots_to_scan.append(public)

    seen_paths: set[str] = set()
    all_items: list[dict] = []

    for scan_root in roots_to_scan:
        for item in _scan_single_root(scan_root, source.id, max_internal):
            try:
                key = str(Path(item["path"]).resolve()).lower()
            except Exception:
                key = item["path"].lower()
            if key in seen_paths:
                continue
            seen_paths.add(key)
            all_items.append(item)

    # Apply incremental filter then save updated snapshot
    to_process = scan_incremental_or_full(source, all_items)
    save_snapshot(source.id, all_items)

    return to_process


def scan_desktop():
    """Legacy single-desktop scan — kept for backward compatibility."""
    config = load_config()
    max_internal = config.get("max_internal_items_per_folder", 200)

    # Build a synthetic desktop Source from the config. Always honor the
    # resolved desktop_path (load_config fills it with Path.home()/Desktop when
    # empty); the empty-path flag only decides whether to merge Public Desktop.
    was_empty = config.get("_desktop_path_was_empty", False)
    from desktop_agent.source_manager import Source as _Source
    desktop_src = _Source(
        id="desktop",
        label="桌面",
        path=config.get("desktop_path", ""),
        enabled=True,
        scan_mode="full",
    )

    print("=" * 80)
    print(t("scanner.header"))
    print("=" * 80)
    print(t("scanner.roots_label"))
    print(f"- {desktop_src.resolved_path}")
    print(t("scanner.mode_description"))
    print("=" * 80)

    items = scan_source(desktop_src, max_internal, merge_public=was_empty)

    observation = {
        "created_at": now_str(),
        "desktop_path": str(desktop_src.resolved_path),
        "desktop_paths": [str(desktop_src.resolved_path)],
        "scan_mode": "merged_desktop_first_level_with_light_content_summary",
        "sources_scanned": ["desktop"],
        "items_count": len(items),
        "items": items,
    }
    save_json(OBSERVATION_FILE, observation)

    print("")
    print(t("scanner.done", count=len(items)))
    print(t("scanner.saved", path=OBSERVATION_FILE))

    update_state(
        "last_scan_at",
        t("scanner.state_done", count=len(items), paths=str(desktop_src.resolved_path)),
    )


def scan_all_sources(source_ids: list[str] | None = None, silent: bool = False) -> dict:
    """
    Scan all enabled sources (or a filtered subset) and return a combined observation.
    Returns the observation dict (also saved to OBSERVATION_FILE).
    """
    config = load_config()
    max_internal = config.get("max_internal_items_per_folder", 200)
    sources = get_enabled_sources(config)

    if source_ids is not None:
        sources = [s for s in sources if s.id in source_ids]

    if not sources:
        print(t("scanner.no_sources_enabled", default="没有启用的整理来源"))
        return {}

    if not silent:
        print("=" * 80)
        print(t("scanner.multi_header", default="多来源扫描"))
        print("=" * 80)

    all_items: list[dict] = []
    sources_scanned: list[str] = []
    seen_global: set[str] = set()

    for source in sources:
        if not silent:
            mode_label = t("scanner.mode_incremental", default="增量") if source.scan_mode == "incremental" else t("scanner.mode_full", default="全量")
            print(f"\n[{source.label}] {source.resolved_path} ({mode_label})")

        if not validate_source_path(str(source.resolved_path)):
            if not silent:
                print(t("scanner.source_invalid", label=source.label, default=f"来源路径无效，跳过: {source.label}"))
            continue

        try:
            items = scan_source(source, max_internal)
            for item in items:
                try:
                    key = str(Path(item["path"]).resolve()).lower()
                except Exception:
                    key = item["path"].lower()
                if key not in seen_global:
                    seen_global.add(key)
                    all_items.append(item)
            sources_scanned.append(source.id)
        except Exception as exc:
            if not silent:
                print(t("scanner.source_error", label=source.label, error=exc, default=f"扫描来源 {source.label} 失败: {exc}"))

    observation = {
        "created_at": now_str(),
        "desktop_path": str(sources[0].resolved_path) if sources else "",
        "desktop_paths": [str(s.resolved_path) for s in sources],
        "scan_mode": "multi_source",
        "sources_scanned": sources_scanned,
        "items_count": len(all_items),
        "items": all_items,
    }
    save_json(OBSERVATION_FILE, observation)

    if not silent:
        print("")
        print(t("scanner.done", count=len(all_items)))
        print(t("scanner.saved", path=OBSERVATION_FILE))

    update_state(
        "last_scan_at",
        t("scanner.state_done", count=len(all_items), paths=", ".join(sources_scanned)),
    )

    return observation
