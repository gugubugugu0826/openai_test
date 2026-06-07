from pathlib import Path

from desktop_agent.categories import CATEGORIES
from desktop_agent.i18n import t
from desktop_agent.memory import load_memory, save_memory
from desktop_agent.planner import PLAN_FILE
from desktop_agent.state import now_str, update_state
from desktop_agent.storage import load_json, save_json


REVIEW_FILE = "desktop_human_review.json"


def create_human_review():
    if not Path(PLAN_FILE).exists():
        print(t("reviewer.missing_plan", path=PLAN_FILE))
        return

    plan = load_json(PLAN_FILE)
    review = {
        "created_at": now_str(),
        "source_plan": PLAN_FILE,
        "instructions": {
            "enabled": t("reviewer.instructions_enabled"),
            "human_category": t("reviewer.instructions_human_category"),
            "allowed_categories": CATEGORIES,
        },
        "items": [],
    }

    for item in plan["items"]:
        ai_category = item.get("category", "无法判断")
        review_item = {
            "enabled": True,
            "path": item.get("path"),
            "name": item.get("name"),
            "type": item.get("type"),
            "ai_category": ai_category,
            "human_category": ai_category,
            "reason": item.get("reason", ""),
        }
        if item.get("desktop_root"):
            review_item["desktop_root"] = item.get("desktop_root")
        review["items"].append(review_item)

    save_json(REVIEW_FILE, review)

    print("=" * 80)
    print(t("reviewer.create_header"))
    print("=" * 80)
    print(t("reviewer.review_saved", path=REVIEW_FILE))

    update_state("last_review_at", t("reviewer.state_saved", path=REVIEW_FILE))


def learn_from_review():
    review_path = Path(REVIEW_FILE)
    if not review_path.exists():
        print(t("reviewer.missing_review", path=REVIEW_FILE))
        return

    review = load_json(REVIEW_FILE)
    memory = load_memory()
    if "rules" not in memory:
        memory["rules"] = []

    existing_keys = set()
    for rule in memory["rules"]:
        key = (str(rule.get("match", "")).lower(), str(rule.get("category", "")).lower())
        existing_keys.add(key)

    learned_count = 0
    skipped_count = 0

    for item in review.get("items", []):
        if not item.get("enabled", True):
            continue

        name = item.get("name", "")
        ai_category = item.get("ai_category", "无法判断")
        human_category = item.get("human_category", ai_category)
        item_type = item.get("type", "")

        if not name:
            continue
        if human_category == ai_category:
            skipped_count += 1
            continue
        if human_category not in CATEGORIES:
            skipped_count += 1
            continue

        match_text = Path(name).stem
        if len(match_text.strip()) < 3:
            skipped_count += 1
            continue

        key = (match_text.lower(), human_category.lower())
        if key in existing_keys:
            skipped_count += 1
            continue

        memory["rules"].append(
            {
                "match": match_text,
                "category": human_category,
                "note": t(
                    "reviewer.learn_note",
                    ai_category=ai_category,
                    human_category=human_category,
                    item_type=item_type,
                ),
            }
        )

        existing_keys.add(key)
        learned_count += 1

    save_memory(memory)

    print("=" * 80)
    print(t("reviewer.learn_header"))
    print("=" * 80)
    print(t("reviewer.learn_added", count=learned_count))
    print(t("reviewer.learn_skipped", count=skipped_count))

    update_state("last_learn_at", t("reviewer.learn_state", count=learned_count))
