# desktop_agent_cli.py

import argparse

from desktop_agent.healthcheck import print_healthcheck
from desktop_agent.scanner import scan_desktop
from desktop_agent.planner import preview_plan
from desktop_agent.reviewer import create_human_review, learn_from_review
from desktop_agent.executor import dryrun_plan, apply_plan, undo_last_action
from desktop_agent.memory import show_memory
from desktop_agent.state import show_state
from desktop_agent.workflow import run_workflow, continue_workflow


def main():
    parser = argparse.ArgumentParser(description="Qwen Desktop Organizer Agent")

    parser.add_argument(
        "command",
        choices=[
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
            "continue"
        ],
        help=(
            "scan=扫描, preview=生成计划, review=人工审核文件, "
            "learn=学习, dryrun=预演, apply=执行, undo=撤销, "
            "memory=查看记忆, state=查看状态, run=自动执行到人工审核, "
            "continue=人工审核后继续执行"
        )
    )

    args = parser.parse_args()

    if args.command == "check":
        print_healthcheck()
    elif args.command == "scan":
        scan_desktop()
    elif args.command == "preview":
        preview_plan()
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


if __name__ == "__main__":
    main()