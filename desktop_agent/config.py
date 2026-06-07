from pathlib import Path

from desktop_agent.i18n import t
from desktop_agent.storage import load_json, save_json


CONFIG_FILE = "config.json"

_DEFAULT_SOURCES = [
    {"id": "desktop",   "label": "桌面",   "path": "", "enabled": True,  "scan_mode": "full"},
    {"id": "downloads", "label": "下载",   "path": "", "enabled": False, "scan_mode": "incremental"},
    {"id": "documents", "label": "文档",   "path": "", "enabled": False, "scan_mode": "incremental"},
    {"id": "wechat",    "label": "微信文件", "path": "", "enabled": False, "scan_mode": "incremental"},
]

_DEFAULT_SCHEDULE = {"enabled": False, "frequency": "weekly", "day": "sunday", "hour": 9}


def _migrate_to_sources(config: dict) -> dict:
    """Auto-migrate old single desktop_path format to multi-source format."""
    if "sources" in config:
        return config

    legacy_path = str(config.get("desktop_path") or "").strip()
    sources = [s.copy() for s in _DEFAULT_SOURCES]
    sources[0]["path"] = legacy_path  # desktop source keeps the old path (may be empty → default)

    # Populate default paths for non-desktop sources
    home = Path.home()
    sources[1]["path"] = str(home / "Downloads")
    sources[2]["path"] = str(home / "Documents")

    config["sources"] = sources
    config.setdefault("suggestion_mode", False)
    config.setdefault("schedule", _DEFAULT_SCHEDULE.copy())

    save_json(CONFIG_FILE, config)
    return config


def load_config():
    path = Path(CONFIG_FILE)

    if not path.exists():
        raise FileNotFoundError(t("config.file_missing", path=CONFIG_FILE))

    config = load_json(path)
    config = _migrate_to_sources(config)

    # Derive desktop_path for backward compat — use the desktop source's path
    sources = config.get("sources", [])
    desktop_source = next((s for s in sources if s.get("id") == "desktop"), None)
    configured_path = str((desktop_source or {}).get("path") or "").strip()

    config["_desktop_path_was_empty"] = not configured_path
    config["desktop_path"] = configured_path or str(Path.home() / "Desktop")

    if not str(config.get("normal_target_root") or "").strip():
        raise ValueError(t("config.target_root_missing"))

    return config


def load_sources(config=None):
    """Return the sources list from config."""
    cfg = config or load_config()
    return cfg.get("sources", [])
