# desktop_agent/config.py

from pathlib import Path
from desktop_agent.storage import load_json


CONFIG_FILE = "config.json"


def load_config():
    path = Path(CONFIG_FILE)

    if not path.exists():
        raise FileNotFoundError(
            f"找不到 {CONFIG_FILE}，请先创建 config.json"
        )

    config = load_json(path)

    desktop_path = config.get("desktop_path") or str(Path.home() / "Desktop")
    config["desktop_path"] = desktop_path

    return config