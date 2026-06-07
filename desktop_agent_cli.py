import argparse
import json
from pathlib import Path

from desktop_agent.executor import apply_plan, dryrun_plan, undo_last_action
from desktop_agent.healthcheck import print_healthcheck
from desktop_agent.i18n import (
    get_language,
    install_runtime_output_translation,
    set_language,
    t,
)
from desktop_agent.memory import show_memory
from desktop_agent.pattern_analyzer import show_suggestions
from desktop_agent.planner import preview_plan
from desktop_agent.reviewer import create_human_review, learn_from_review
from desktop_agent.scanner import scan_all_sources, scan_desktop
from desktop_agent.scheduler import show_schedule
from desktop_agent.source_manager import show_sources
from desktop_agent.state import show_state
from desktop_agent.suggestion_queue import show_queue
from desktop_agent.workflow import (
    auto_run_workflow,
    confirm_suggestions,
    continue_workflow,
    run_suggestion_workflow,
    run_workflow,
)


CONFIG_FILE = Path("config.json")


def _init_cli_language():
    language = None
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            if isinstance(config, dict):
                language = config.get("ui_language")
    except Exception:
        language = None

    set_language(language)
    install_runtime_output_translation()


def main():
    _init_cli_language()

    parser = argparse.ArgumentParser(
        description=t("cli.parser_description")
    )

    parser.add_argument(
        "command",
        choices=[
            # --- Legacy commands ---
            "check",
            "scan",
            "preview",
            "review",
            "learn",
            "dryrun",
            "apply",
            "undo",
            "memory",
            "state",
            "run",
            "continue",
            # --- 3.0 new commands ---
            "auto-run",
            "suggestions",
            "confirm",
            "sources",
            "schedule",
            "analyze",
            "multi-scan",
        ],
        help=t("cli.command_help"),
    )

    parser.add_argument(
        "--intent",
        default="",
        help=t("cli.intent_help", default="整理意图（自然语言，可选）"),
    )
    parser.add_argument(
        "--sources",
        default="",
        help=t("cli.sources_help", default="指定来源ID，逗号分隔，留空表示全部启用来源"),
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help=t("cli.silent_help", default="静默模式，减少输出（适合定时任务）"),
    )

    args = parser.parse_args()

    source_ids = [s.strip() for s in args.sources.split(",") if s.strip()] if args.sources else None

    if args.command == "check":
        print_healthcheck()
    elif args.command == "scan":
        scan_desktop()
    elif args.command == "multi-scan":
        scan_all_sources(source_ids=source_ids)
    elif args.command == "preview":
        preview_plan(user_intent=args.intent)
    elif args.command == "review":
        create_human_review()
    elif args.command == "learn":
        learn_from_review()
    elif args.command == "dryrun":
        dryrun_plan()
    elif args.command == "apply":
        apply_plan()
    elif args.command == "undo":
        undo_last_action()
    elif args.command == "memory":
        show_memory()
    elif args.command == "state":
        show_state()
    elif args.command == "run":
        run_workflow()
    elif args.command == "continue":
        continue_workflow()
    # --- 3.0 commands ---
    elif args.command == "auto-run":
        auto_run_workflow(silent=args.silent)
    elif args.command == "suggestions":
        show_queue()
    elif args.command == "confirm":
        confirm_suggestions()
    elif args.command == "sources":
        show_sources()
    elif args.command == "schedule":
        show_schedule()
    elif args.command == "analyze":
        show_suggestions()


if __name__ == "__main__":
    main()
