# desktop_agent/plan_explainer.py

import json
from pathlib import Path
from datetime import datetime

from desktop_agent.config import load_config
from desktop_agent.storage import load_json, save_json


PLAN_FILE = "desktop_agent_plan.json"
REVIEW_FILE = "desktop_human_review.json"

EXPLANATION_JSON = "desktop_agent_explanation.json"
EXPLANATION_MD = "desktop_agent_explanation.md"


def get_item_category(item):
    return (
        item.get("human_category")
        or item.get("category")
        or item.get("ai_category")
        or "无法判断"
    )


def get_item_enabled(item):
    return item.get("enabled", True)


def load_plan_items():
    """
    优先解释 review 文件。
    如果 review 不存在，则解释 plan 文件。
    """
    if Path(REVIEW_FILE).exists():
        data = load_json(REVIEW_FILE)
        return data.get("items", []), REVIEW_FILE

    if Path(PLAN_FILE).exists():
        data = load_json(PLAN_FILE)
        return data.get("items", []), PLAN_FILE

    return [], "none"


def build_plan_explanation():
    config = load_config()
    provider = config.get("llm_provider", "none")
    target_root = config.get("normal_target_root", "")
    folder_mode = config.get("folder_mode", "")

    items, source_file = load_plan_items()

    total = len(items)
    enabled_items = [item for item in items if get_item_enabled(item)]
    disabled_items = [item for item in items if not get_item_enabled(item)]

    type_counts = {}
    category_counts = {}
    classified_by_counts = {}
    warning_items = []

    for item in enabled_items:
        item_type = item.get("type", "unknown")
        category = get_item_category(item)
        classified_by = item.get("classified_by", "unknown")

        type_counts[item_type] = type_counts.get(item_type, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        classified_by_counts[classified_by] = classified_by_counts.get(classified_by, 0) + 1

        reason = item.get("reason", "")

        if category in ["无法判断", "其他快捷方式"]:
            warning_items.append({
                "name": item.get("name", ""),
                "type": item_type,
                "category": category,
                "reason": reason
            })

        if "失败" in reason or "无法" in reason:
            warning_items.append({
                "name": item.get("name", ""),
                "type": item_type,
                "category": category,
                "reason": reason
            })

    top_categories = sorted(
        category_counts.items(),
        key=lambda x: x[1],
        reverse=True
    )

    explanation = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_file": source_file,
        "provider": provider,
        "target_root": target_root,
        "folder_mode": folder_mode,
        "total_items": total,
        "enabled_items": len(enabled_items),
        "disabled_items": len(disabled_items),
        "type_counts": type_counts,
        "category_counts": category_counts,
        "classified_by_counts": classified_by_counts,
        "top_categories": top_categories[:10],
        "warning_items": warning_items[:30],
        "summary": "",
        "recommendations": []
    }

    summary_lines = []

    summary_lines.append(
        f"本次计划共包含 {total} 个项目，其中启用 {len(enabled_items)} 个，跳过 {len(disabled_items)} 个。"
    )

    if provider == "none":
        summary_lines.append(
            "当前使用普通模式 none：主要依赖 Memory + Rule，模糊项目需要人工审核。"
        )
    elif provider == "ollama":
        summary_lines.append(
            "当前使用本地 AI 模式 ollama：模糊项目会尝试交给本地模型判断。"
        )
    elif provider == "openai_compatible":
        summary_lines.append(
            "当前使用云端 API 模式 openai_compatible：模糊项目会尝试交给云端兼容接口判断。"
        )

    if top_categories:
        top_text = "、".join([f"{cat}({count})" for cat, count in top_categories[:5]])
        summary_lines.append(f"数量最多的分类是：{top_text}。")

    if warning_items:
        summary_lines.append(
            f"存在 {len(warning_items)} 个需要重点人工检查的项目，例如无法判断、其他快捷方式或分类失败项。"
        )
    else:
        summary_lines.append("没有发现明显需要重点关注的异常分类项。")

    explanation["summary"] = "\n".join(summary_lines)

    recommendations = []

    if warning_items:
        recommendations.append("请优先检查“无法判断”和“其他快捷方式”分类。")
        recommendations.append("如果这些项目经常出现，可以在 Human Review 中修改分类，再执行 Learn 让 Agent 记住。")

    if len(enabled_items) >= 200:
        recommendations.append("启用项目数量较多，建议先仔细查看 Dryrun 输出，再 Apply。")

    if folder_mode == "move":
        recommendations.append("当前 folder_mode=move，会移动文件夹。建议普通用户优先使用 copy。")

    if not recommendations:
        recommendations.append("建议继续执行 Dryrun，确认预演结果无误后再 Apply。")

    explanation["recommendations"] = recommendations

    return explanation


def render_markdown(explanation):
    lines = []

    lines.append("# Desktop Agent Plan Explanation")
    lines.append("")
    lines.append(f"- 生成时间：{explanation['created_at']}")
    lines.append(f"- 数据来源：{explanation['source_file']}")
    lines.append(f"- 模型模式：{explanation['provider']}")
    lines.append(f"- 目标目录：{explanation['target_root']}")
    lines.append(f"- 文件夹处理模式：{explanation['folder_mode']}")
    lines.append("")

    lines.append("## 总体解释")
    lines.append("")
    lines.append(explanation["summary"])
    lines.append("")

    lines.append("## 项目数量")
    lines.append("")
    lines.append(f"- 总项目数：{explanation['total_items']}")
    lines.append(f"- 启用项目：{explanation['enabled_items']}")
    lines.append(f"- 跳过项目：{explanation['disabled_items']}")
    lines.append("")

    lines.append("## 类型统计")
    lines.append("")
    for key, value in explanation["type_counts"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")

    lines.append("## 分类统计")
    lines.append("")
    for key, value in sorted(explanation["category_counts"].items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {key}: {value}")
    lines.append("")

    lines.append("## 分类来源统计")
    lines.append("")
    for key, value in explanation["classified_by_counts"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")

    lines.append("## 需要重点检查的项目")
    lines.append("")
    if explanation["warning_items"]:
        for item in explanation["warning_items"]:
            lines.append(
                f"- {item['name']} | type={item['type']} | category={item['category']} | reason={item['reason']}"
            )
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 建议")
    lines.append("")
    for rec in explanation["recommendations"]:
        lines.append(f"- {rec}")
    lines.append("")

    return "\n".join(lines)


def explain_current_plan():
    explanation = build_plan_explanation()

    save_json(EXPLANATION_JSON, explanation)

    md = render_markdown(explanation)

    with open(EXPLANATION_MD, "w", encoding="utf-8") as f:
        f.write(md)

    print("=" * 80)
    print("Agent Plan Explanation：计划解释")
    print("=" * 80)
    print(explanation["summary"])
    print("")
    print("建议：")
    for rec in explanation["recommendations"]:
        print(f"- {rec}")
    print("")
    print(f"解释文件已生成：{EXPLANATION_MD}")
    print("=" * 80)

    return explanation