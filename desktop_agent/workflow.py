from desktop_agent.executor import apply_plan, dryrun_plan
from desktop_agent.i18n import t
from desktop_agent.reviewer import REVIEW_FILE, create_human_review, learn_from_review
from desktop_agent.scanner import scan_desktop
from desktop_agent.planner import preview_plan
from desktop_agent.state import require_file, update_state


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
