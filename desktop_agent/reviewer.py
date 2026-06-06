# desktop_agent/reviewer.py

from pathlib import Path

from desktop_agent.categories import CATEGORIES
from desktop_agent.storage import save_json, load_json
from desktop_agent.state import now_str, update_state
from desktop_agent.memory import load_memory, save_memory
from desktop_agent.planner import PLAN_FILE


REVIEW_FILE = "desktop_human_review.json"


def create_human_review():
    if not Path(PLAN_FILE).exists():
        print(f"找不到 {PLAN_FILE}，请先运行：python desktop_agent_cli.py preview")
        return

    plan = load_json(PLAN_FILE)

    review = {
        "created_at": now_str(),
        "source_plan": PLAN_FILE,
        "instructions": {
            "enabled": "true 表示执行，false 表示跳过",
            "human_category": "你可以手动修改分类；apply 会优先使用 human_category",
            "allowed_categories": CATEGORIES
        },
        "items": []
    }

    for item in plan["items"]:
        ai_category = item.get("category", "无法判断")

        review["items"].append({
            "enabled": True,
            "path": item.get("path"),
            "name": item.get("name"),
            "type": item.get("type"),
            "ai_category": ai_category,
            "human_category": ai_category,
            "reason": item.get("reason", "")
        })

    save_json(REVIEW_FILE, review)

    print("=" * 80)
    print("Step 2.5 - Human Review：生成可人工修改的审核文件")
    print("=" * 80)
    print(f"审核文件已生成：{REVIEW_FILE}")

    update_state(
        "last_review_at",
        f"人工审核文件已生成：{REVIEW_FILE}"
    )


def learn_from_review():
    review_path = Path(REVIEW_FILE)

    if not review_path.exists():
        print(f"找不到 {REVIEW_FILE}，请先运行：python desktop_agent_cli.py review")
        return

    review = load_json(REVIEW_FILE)
    memory = load_memory()

    if "rules" not in memory:
        memory["rules"] = []

    existing_keys = set()

    for rule in memory["rules"]:
        key = (
            str(rule.get("match", "")).lower(),
            str(rule.get("category", "")).lower()
        )
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

        memory["rules"].append({
            "match": match_text,
            "category": human_category,
            "note": f"从人工审核学习：原 AI 分类为 {ai_category}，用户改为 {human_category}；类型 {item_type}"
        })

        existing_keys.add(key)
        learned_count += 1

    save_memory(memory)

    print("=" * 80)
    print("Agent Learning：从人工审核中学习")
    print("=" * 80)
    print(f"新增记忆规则：{learned_count} 条")
    print(f"跳过未变化/重复/无效项：{skipped_count} 条")

    update_state(
        "last_learn_at",
        f"从人工审核学习完成，新增记忆规则：{learned_count} 条"
    )