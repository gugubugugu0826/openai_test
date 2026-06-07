from pathlib import Path

from desktop_agent.categories import CATEGORIES
from desktop_agent.i18n import t
from desktop_agent.storage import load_json, save_json


MEMORY_FILE = "agent_memory.json"


def load_memory():
    path = Path(MEMORY_FILE)

    if not path.exists():
        memory = {"rules": []}
        save_json(MEMORY_FILE, memory)
        return memory

    return load_json(MEMORY_FILE)


def save_memory(memory):
    save_json(MEMORY_FILE, memory)


def show_memory():
    memory = load_memory()

    print("=" * 80)
    print(t("memory.header"))
    print("=" * 80)

    rules = memory.get("rules", [])
    if not rules:
        print(t("memory.no_rules"))
        return

    for index, rule in enumerate(rules, start=1):
        print(f"{index}. {t('memory.match_label')}: {rule.get('match')}")
        print(f"   {t('memory.category_label')}: {rule.get('category')}")
        print(f"   {t('memory.note_label')}: {rule.get('note', '')}")
        print()


def memory_classify_item(item):
    memory = load_memory()
    rules = memory.get("rules", [])

    name = item.get("name", "").lower()
    path = item.get("path", "").lower()

    for rule in rules:
        match_text = str(rule.get("match", "")).lower().strip()
        category = rule.get("category")

        if not match_text or category not in CATEGORIES:
            continue

        if match_text in name or match_text in path:
            return {
                "path": item["path"],
                "name": item["name"],
                "type": item["type"],
                "category": category,
                "reason": t(
                    "memory.rule_matched_reason",
                    note=rule.get("note", match_text),
                ),
                "classified_by": "memory",
            }

    return None


def add_memory_rule(match_text, category, note=""):
    if category not in CATEGORIES:
        raise ValueError(t("memory.invalid_category", category=category))

    memory = load_memory()
    if "rules" not in memory:
        memory["rules"] = []

    key = (match_text.lower(), category.lower())

    for rule in memory["rules"]:
        existing_key = (
            str(rule.get("match", "")).lower(),
            str(rule.get("category", "")).lower(),
        )
        if existing_key == key:
            return False

    memory["rules"].append(
        {
            "match": match_text,
            "category": category,
            "note": note,
        }
    )

    save_memory(memory)
    return True
