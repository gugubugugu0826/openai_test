from datetime import datetime
from pathlib import Path

from desktop_agent.config import load_config
from desktop_agent.i18n import get_category_display, t
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
        if category in ["无法判断", "其他快捷方式"] or "failed" in reason.lower() or "无法" in reason:
            warning_items.append(
                {
                    "name": item.get("name", ""),
                    "type": item_type,
                    "category": category,
                    "reason": reason,
                }
            )

    top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)

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
        "recommendations": [],
    }

    summary_lines = [
        t("explainer.summary_counts", total=total, enabled=len(enabled_items), disabled=len(disabled_items))
    ]

    if provider == "none":
        summary_lines.append(t("explainer.summary_provider_none"))
    elif provider == "ollama":
        summary_lines.append(t("explainer.summary_provider_ollama"))
    elif provider == "openai_compatible":
        summary_lines.append(t("explainer.summary_provider_openai"))
    elif provider == "builtin":
        summary_lines.append(t("explainer.summary_provider_builtin"))

    if top_categories:
        top_text = ", ".join([f"{get_category_display(cat)}({count})" for cat, count in top_categories[:5]])
        summary_lines.append(t("explainer.summary_top_categories", categories=top_text))

    if warning_items:
        summary_lines.append(t("explainer.summary_warning_items", count=len(warning_items)))
    else:
        summary_lines.append(t("explainer.summary_no_warnings"))

    explanation["summary"] = "\n".join(summary_lines)

    recommendations = []
    if warning_items:
        recommendations.append(t("explainer.rec_review_categories"))
        recommendations.append(t("explainer.rec_learn_after_review"))
    if len(enabled_items) >= 200:
        recommendations.append(t("explainer.rec_many_enabled"))
    if folder_mode == "move":
        recommendations.append(t("explainer.rec_move_mode"))
    if not recommendations:
        recommendations.append(t("explainer.rec_default"))

    explanation["recommendations"] = recommendations
    return explanation


def render_markdown(explanation):
    lines = [
        "# Desktop Agent Plan Explanation",
        "",
        f"- {t('explainer.md_created_at')}: {explanation['created_at']}",
        f"- {t('explainer.md_source')}: {explanation['source_file']}",
        f"- {t('explainer.md_provider')}: {explanation['provider']}",
        f"- {t('explainer.md_target_root')}: {explanation['target_root']}",
        f"- {t('explainer.md_folder_mode')}: {explanation['folder_mode']}",
        "",
        f"## {t('explainer.md_summary_title')}",
        "",
        explanation["summary"],
        "",
        f"## {t('explainer.md_counts_title')}",
        "",
        f"- {t('explainer.md_total')}: {explanation['total_items']}",
        f"- {t('explainer.md_enabled')}: {explanation['enabled_items']}",
        f"- {t('explainer.md_disabled')}: {explanation['disabled_items']}",
        "",
        f"## {t('explainer.md_type_stats_title')}",
        "",
    ]

    for key, value in explanation["type_counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", f"## {t('explainer.md_category_stats_title')}", ""])

    for key, value in sorted(explanation["category_counts"].items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {get_category_display(key)}: {value}")
    lines.extend(["", f"## {t('explainer.md_source_stats_title')}", ""])

    for key, value in explanation["classified_by_counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", f"## {t('explainer.md_warning_title')}", ""])

    if explanation["warning_items"]:
        for item in explanation["warning_items"]:
            lines.append(
                f"- {item['name']} | type={item['type']} | category={get_category_display(item['category'])} | reason={item['reason']}"
            )
    else:
        lines.append(f"- {t('explainer.md_none')}")

    lines.extend(["", f"## {t('explainer.md_recommendations_title')}", ""])
    for rec in explanation["recommendations"]:
        lines.append(f"- {rec}")
    lines.append("")
    return "\n".join(lines)


def explain_current_plan():
    explanation = build_plan_explanation()
    save_json(EXPLANATION_JSON, explanation)

    md = render_markdown(explanation)
    with open(EXPLANATION_MD, "w", encoding="utf-8") as handle:
        handle.write(md)

    print("=" * 80)
    print(t("explainer.console_header"))
    print("=" * 80)
    print(explanation["summary"])
    print("")
    print(t("explainer.console_recommendations"))
    for rec in explanation["recommendations"]:
        print(f"- {rec}")
    print("")
    print(t("explainer.console_written", path=EXPLANATION_MD))
    print("=" * 80)
    return explanation
