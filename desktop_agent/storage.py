import json
from pathlib import Path

from desktop_agent.i18n import t


def save_json(path, data):
    path = Path(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path):
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(t("storage.file_missing", path=path))

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def json_exists(path):
    return Path(path).exists()
