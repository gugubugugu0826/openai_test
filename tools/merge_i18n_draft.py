from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
DRAFT_FILE = PROJECT_DIR / "test_reports" / "latest_i18n_draft.json"
EN_LOCALE_FILE = PROJECT_DIR / "locales" / "en.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Merge generated i18n draft strings into locales/en.json.")
    parser.add_argument("--include-todo", action="store_true", help="Also merge TODO placeholder entries.")
    args = parser.parse_args()

    draft = load_json(DRAFT_FILE, {"translations": {}})
    locale = load_json(EN_LOCALE_FILE, {"translations": {}, "categories": {}, "substrings": {}})

    merged = 0
    skipped = 0

    for source_text, translated_text in draft.get("translations", {}).items():
        if not args.include_todo and translated_text.startswith("TODO: "):
            skipped += 1
            continue
        if source_text in locale["translations"] and locale["translations"][source_text] == translated_text:
            continue
        locale["translations"][source_text] = translated_text
        merged += 1

    save_json(EN_LOCALE_FILE, locale)
    print(f"merged={merged}, skipped={skipped}, locale={EN_LOCALE_FILE}")


if __name__ == "__main__":
    main()
