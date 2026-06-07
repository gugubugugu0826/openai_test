from pathlib import Path

from desktop_agent.i18n import t
from desktop_agent.storage import load_json


CONFIG_FILE = "config.json"


def load_config():
    path = Path(CONFIG_FILE)

    if not path.exists():
        raise FileNotFoundError(
            t("config.file_missing", path=CONFIG_FILE)
        )

    config = load_json(path)

    configured_desktop_path = str(config.get("desktop_path") or "").strip()
    config["_desktop_path_was_empty"] = not configured_desktop_path

    desktop_path = configured_desktop_path or str(Path.home() / "Desktop")
    config["desktop_path"] = desktop_path

    if not str(config.get("normal_target_root") or "").strip():
        raise ValueError(t("config.target_root_missing"))

    return config
