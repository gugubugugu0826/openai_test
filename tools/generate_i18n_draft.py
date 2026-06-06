from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
EXTRACT_FILE = PROJECT_DIR / "test_reports" / "latest_i18n_extract.json"
EN_LOCALE_FILE = PROJECT_DIR / "locales" / "en.json"
OUTPUT_FILE = PROJECT_DIR / "test_reports" / "latest_i18n_draft.json"


SYSTEM_PROMPT = """You are translating UI and desktop-app strings from Simplified Chinese to natural, concise English.

Rules:
1. Keep button labels short.
2. Keep terminology consistent:
   - 整理桌面 -> Organize Desktop
   - 整理方案 -> Review Plan
   - 整理记忆 -> Memory Rules
   - 运行日志 -> Logs
   - 无法判断 -> Needs Review
3. Preserve placeholders such as {total}, {enabled}, {checked}, {version}.
4. Return valid JSON only. Keys must stay exactly the same as the input keys.
"""


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_missing_strings():
    extract = load_json(EXTRACT_FILE, {"items": []})
    existing_en = load_json(EN_LOCALE_FILE, {"translations": {}, "categories": {}, "substrings": {}})
    known = {}
    for bucket_name in ("translations", "categories", "substrings"):
        known.update(existing_en.get(bucket_name, {}))

    missing = []
    seen = set()
    for item in extract.get("items", []):
        text = item["text"]
        if item.get("in_locale"):
            continue
        if text in known:
            continue
        if text in seen:
            continue
        seen.add(text)
        missing.append(text)
    return missing


def call_openai_compatible(strings):
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DESKTOP_AGENT_API_KEY")
    api_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    if not api_key:
        return None, "OPENAI_API_KEY or DESKTOP_AGENT_API_KEY is not set."

    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"translations": {text: text for text in strings}},
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ],
    }

    request = urllib.request.Request(
        api_base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read().decode("utf-8")
    data = json.loads(raw)
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return parsed.get("translations", {}), None


def build_placeholder_draft(strings):
    return {text: f"TODO: {text}" for text in strings}


def main():
    parser = argparse.ArgumentParser(description="Generate an English draft for missing i18n strings.")
    parser.add_argument("--api", action="store_true", help="Call the configured OpenAI-compatible API.")
    args = parser.parse_args()

    missing = load_missing_strings()
    if not missing:
        draft = {"mode": "noop", "translations": {}, "message": "No missing strings found."}
        save_json(OUTPUT_FILE, draft)
        print(f"No missing strings. Draft written to: {OUTPUT_FILE}")
        return

    mode = "placeholder"
    translated, error_message = None, "API mode was not requested."
    if args.api:
        mode = "api"
        try:
            translated, error_message = call_openai_compatible(missing)
        except Exception as e:
            translated, error_message = None, str(e)

    if translated is None:
        translated = build_placeholder_draft(missing)
        mode = "placeholder"

    draft = {
        "mode": mode,
        "count": len(translated),
        "error": error_message,
        "translations": translated,
    }
    save_json(OUTPUT_FILE, draft)
    print(f"i18n draft written to: {OUTPUT_FILE}")
    print(f"mode={mode}, strings={len(translated)}")
    if error_message:
        print(error_message)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"generate_i18n_draft failed: {e}")
        sys.exit(1)
