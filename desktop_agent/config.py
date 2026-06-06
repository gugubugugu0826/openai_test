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

    configured_desktop_path = str(config.get("desktop_path") or "").strip()
    config["_desktop_path_was_empty"] = not configured_desktop_path

    desktop_path = configured_desktop_path or str(Path.home() / "Desktop")
    config["desktop_path"] = desktop_path

    if not str(config.get("normal_target_root") or "").strip():
        raise ValueError(
            "config.json 缺少必要字段：normal_target_root\n"
            "请在 GUI 设置页或 config.json 中填写目标整理目录后重试。"
        )

    return config
