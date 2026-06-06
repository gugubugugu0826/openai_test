# desktop_agent/workflow.py

from desktop_agent.scanner import scan_desktop
from desktop_agent.planner import preview_plan
from desktop_agent.reviewer import create_human_review, learn_from_review, REVIEW_FILE
from desktop_agent.executor import dryrun_plan, apply_plan
from desktop_agent.state import update_state, require_file


def run_workflow():
    print("=" * 80)
    print("Agent Workflow：run")
    print("=" * 80)
    print("将自动执行：scan -> preview -> review")
    print("执行完成后，请人工检查 desktop_human_review.json")
    print("=" * 80)

    scan_desktop()
    preview_plan()
    create_human_review()

    update_state(
        "last_review_at",
        "run workflow 完成：scan -> preview -> review"
    )

    print("\n" + "=" * 80)
    print("run 阶段完成。")
    print("下一步请打开 desktop_human_review.json 检查：")
    print("- enabled=false 表示跳过")
    print("- human_category 可以手动修正分类")
    print()
    print("确认后：")
    print("如果使用 GUI，请点击左侧 Continue: learn → dryrun")
    print("如果使用命令行，请运行：python desktop_agent_cli.py continue")
    print("=" * 80)


def continue_workflow():
    print("=" * 80)
    print("Agent Workflow：continue")
    print("=" * 80)
    print("将自动执行：learn -> dryrun")
    print("dryrun 后会询问是否正式 apply")
    print("=" * 80)

    if not require_file(REVIEW_FILE, "python desktop_agent_cli.py review"):
        return

    learn_from_review()
    dryrun_plan()

    print("\n" + "=" * 80)
    print("dryrun 已完成。")
    print("请确认上面的预演结果是否正确。")
    print("正式执行会移动普通文件、移动快捷方式、复制文件夹到 D 盘。")
    print("=" * 80)

    confirm = input("确认正式执行 apply？输入 YES 继续：")

    if confirm != "YES":
        print("已取消正式执行。")
        update_state(
            "last_dryrun_at",
            "continue workflow 已完成 dryrun，但用户取消 apply"
        )
        return

    apply_plan()

    update_state(
        "last_apply_at",
        "continue workflow 完成：learn -> dryrun -> apply"
    )

    print("\ncontinue 阶段完成。")