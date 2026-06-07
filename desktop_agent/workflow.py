from __future__ import annotations

from desktop_agent.executor import apply_plan, dryrun_plan
from desktop_agent.i18n import t
from desktop_agent.reviewer import REVIEW_FILE, create_human_review, learn_from_review
from desktop_agent.scanner import scan_all_sources, scan_desktop
from desktop_agent.planner import preview_plan
from desktop_agent.state import require_file, update_state


# ---------------------------------------------------------------------------
# Legacy single-desktop workflow (backward compat)
# ---------------------------------------------------------------------------

def run_workflow():
    print("=" * 80)
    print(t("workflow_cli.run_header"))
    print("=" * 80)
    print(t("workflow_cli.run_intro"))
    print(t("workflow_cli.run_review_hint"))
    print("=" * 80)

    scan_desktop()
    preview_plan()
    create_human_review()

    update_state("last_review_at", t("workflow_cli.run_state"))

    print("\n" + "=" * 80)
    print(t("workflow_cli.run_done"))
    print(t("workflow_cli.run_next_intro"))
    print(t("workflow_cli.run_next_enabled"))
    print(t("workflow_cli.run_next_category"))
    print("")
    print(t("workflow_cli.run_after_confirm"))
    print(t("workflow_cli.run_after_gui"))
    print(t("workflow_cli.run_after_cli"))
    print("=" * 80)


def continue_workflow():
    print("=" * 80)
    print(t("workflow_cli.continue_header"))
    print("=" * 80)
    print(t("workflow_cli.continue_intro"))
    print(t("workflow_cli.continue_apply_note"))
    print("=" * 80)

    if not require_file(REVIEW_FILE, "python desktop_agent_cli.py review"):
        return

    learn_from_review()
    dryrun_plan()

    print("\n" + "=" * 80)
    print(t("workflow_cli.continue_dryrun_done"))
    print(t("workflow_cli.continue_check_prompt"))
    print(t("workflow_cli.continue_apply_effect"))
    print("=" * 80)

    confirm = input(t("workflow_cli.continue_confirm"))
    if confirm != "YES":
        print(t("workflow_cli.continue_cancelled"))
        update_state("last_dryrun_at", t("workflow_cli.continue_cancelled_state"))
        return

    apply_plan()
    update_state("last_apply_at", t("workflow_cli.continue_apply_state"))
    print("\n" + t("workflow_cli.continue_done"))


# ---------------------------------------------------------------------------
# 3.0 multi-source workflows
# ---------------------------------------------------------------------------

def run_multi_source_workflow(
    source_ids: list[str] | None = None,
    user_intent: str = "",
    silent: bool = False,
):
    """
    Scan all enabled sources (or a subset), classify, create human review.
    Standard interactive path — user will review before execution.
    """
    if not silent:
        print("=" * 80)
        print(t("workflow_cli.multi_run_header", default="多来源整理工作流"))
        print("=" * 80)

    scan_all_sources(source_ids=source_ids, silent=silent)
    preview_plan(user_intent=user_intent)
    create_human_review()
    update_state("last_review_at", t("workflow_cli.run_state"))

    if not silent:
        print("\n" + "=" * 80)
        print(t("workflow_cli.run_done"))
        print(t("workflow_cli.run_after_cli"))
        print("=" * 80)


def run_suggestion_workflow(
    source_ids: list[str] | None = None,
    user_intent: str = "",
    silent: bool = False,
) -> int:
    """
    Scan + classify → write results into suggestion queue (no file moves).
    Returns number of suggestions added.
    """
    from desktop_agent.suggestion_queue import SuggestionItem, append_suggestions
    from desktop_agent.planner import preview_plan
    from desktop_agent.scanner import OBSERVATION_FILE
    from desktop_agent.storage import load_json
    from desktop_agent.state import now_str
    from pathlib import Path

    if not silent:
        print("=" * 80)
        print(t("workflow_cli.suggestion_run_header", default="建议模式：扫描并累积建议"))
        print("=" * 80)

    scan_all_sources(source_ids=source_ids, silent=silent)
    preview_plan(user_intent=user_intent)

    # Load the plan and convert to suggestion items
    plan_path = Path("desktop_agent_plan.json")
    if not plan_path.exists():
        if not silent:
            print(t("workflow_cli.suggestion_no_plan", default="未找到分类计划，跳过建议写入"))
        return 0

    plan = load_json(plan_path)
    scanned_at = now_str()

    new_suggestions: list[SuggestionItem] = []
    for item in plan.get("items", []):
        category = item.get("category", "无法判断")
        classified_by = item.get("classified_by", "unknown")

        confidence = "high"
        if classified_by in ("no_llm", "provider_failed"):
            confidence = "low"
        elif classified_by in ("memory",):
            confidence = "high"
        elif category in ("无法判断", "其他快捷方式"):
            confidence = "low"
        elif classified_by.startswith("rule"):
            confidence = "high"
        else:
            confidence = "medium"

        new_suggestions.append(SuggestionItem(
            source_id=item.get("source_id", "desktop"),
            path=item.get("path", ""),
            name=item.get("name", ""),
            suggested_category=category,
            confidence=confidence,
            reason=item.get("reason", ""),
            scanned_at=scanned_at,
        ))

    queue = append_suggestions(new_suggestions)
    added = len(new_suggestions)

    update_state("last_preview_at", t("workflow_cli.suggestion_state_done", count=added, default=f"建议模式：已添加 {added} 条建议到队列"))

    if not silent:
        print(t("workflow_cli.suggestion_added", count=added, total=queue.pending_count, default=f"已添加 {added} 条新建议，队列共 {queue.pending_count} 条待处理"))

    return added


def confirm_suggestions(
    selected_paths: list[str] | None = None,
    confirm_callback=None,
    learn: bool = True,
) -> None:
    """
    Execute confirmed items from the suggestion queue.
    selected_paths=None means all enabled items.
    """
    from desktop_agent.suggestion_queue import (
        clear_queue,
        plan_items_from_queue,
        validate_queue,
    )
    from desktop_agent.storage import save_json
    from desktop_agent.executor import apply_plan
    import json

    validate_queue()
    plan_items = plan_items_from_queue(selected_paths)

    if not plan_items:
        print(t("workflow_cli.confirm_empty", default="没有可执行的建议项"))
        return

    # Write plan items to a temporary review file so executor can pick them up
    from desktop_agent.reviewer import REVIEW_FILE
    from desktop_agent.categories import CATEGORIES
    from desktop_agent.state import now_str as _now

    review = {
        "created_at": _now(),
        "source_plan": "suggestion_queue.json",
        "instructions": {},
        "items": [
            {
                "enabled": True,
                "path": p["path"],
                "name": p["name"],
                "type": p["type"],
                "ai_category": p["category"],
                "human_category": p["category"],
                "reason": p.get("reason", ""),
                "source_id": p.get("source_id", "desktop"),
            }
            for p in plan_items
        ],
    }
    save_json(REVIEW_FILE, review)

    apply_plan(confirm_callback=confirm_callback)

    update_state("last_apply_at", t("workflow_cli.confirm_apply_state", default="建议确认执行完成"))

    # Clear executed items from queue (keep items not in selected_paths)
    if selected_paths is None:
        clear_queue()
    else:
        from desktop_agent.suggestion_queue import load_queue, save_queue
        queue = load_queue()
        queue.items = [i for i in queue.items if i.path not in set(selected_paths)]
        save_queue(queue)

    if learn:
        try:
            learn_from_review()
        except Exception:
            pass


def auto_run_workflow(silent: bool = True) -> None:
    """
    Entry point for scheduled/background runs.
    Reads suggestion_mode from config to decide whether to write queue or apply directly.
    """
    from desktop_agent.config import load_config
    config = load_config()
    suggestion_mode = config.get("suggestion_mode", False)

    if suggestion_mode:
        run_suggestion_workflow(silent=silent)
    else:
        run_multi_source_workflow(silent=silent)
