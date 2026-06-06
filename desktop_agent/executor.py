# desktop_agent/executor.py

import shutil
from pathlib import Path

from desktop_agent.categories import SHORTCUT_CATEGORY_FOLDERS, NORMAL_CATEGORY_FOLDERS, CATEGORIES
from desktop_agent.config import load_config
from desktop_agent.storage import save_json, load_json
from desktop_agent.state import now_str, update_state, require_file
from desktop_agent.planner import PLAN_FILE
from desktop_agent.reviewer import REVIEW_FILE


ACTION_LOG_FILE = "desktop_action_log.json"


def get_unique_path(dst: Path):
    if not dst.exists():
        return dst

    original = dst
    counter = 1

    while dst.exists():
        dst = original.with_name(f"{original.stem}_{counter}{original.suffix}")
        counter += 1

    return dst


def load_execution_items():
    review_path = Path(REVIEW_FILE)

    if review_path.exists():
        data = load_json(REVIEW_FILE)
        items = []

        for item in data["items"]:
            if not item.get("enabled", True):
                continue

            category = item.get("human_category") or item.get("ai_category") or "无法判断"

            if category not in CATEGORIES:
                category = "无法判断"

            execution_item = {
                "path": item["path"],
                "name": item["name"],
                "type": item["type"],
                "category": category,
                "human_category": category,
                "reason": item.get("reason", "")
            }

            if item.get("desktop_root"):
                execution_item["desktop_root"] = item.get("desktop_root")

            items.append(execution_item)

        return items, REVIEW_FILE

    plan = load_json(PLAN_FILE)
    return plan["items"], PLAN_FILE


def get_target_path(item):
    src = Path(item["path"])
    item_type = item["type"]

    category = item.get("human_category") or item.get("category") or item.get("ai_category") or "无法判断"

    if item_type == "shortcut":
        folder = SHORTCUT_CATEGORY_FOLDERS.get(category, "99_其他快捷方式")
        return src.parent / folder / src.name

    config = load_config()
    folder = NORMAL_CATEGORY_FOLDERS.get(category, "无法判断")
    return Path(config["normal_target_root"]) / folder / src.name


def dryrun_plan():
    if not Path(REVIEW_FILE).exists() and not Path(PLAN_FILE).exists():
        print("缺少执行来源。请先运行：python desktop_agent_cli.py preview")
        return

    items, source_file = load_execution_items()

    print("=" * 80)
    print("Step 3 - Action Simulation：预演整理计划")
    print("=" * 80)
    print(f"执行来源：{source_file}")

    for item in items:
        src = Path(item["path"])
        dst = get_target_path(item)

        item_type = item.get("type", "file")
        category = item.get("human_category") or item.get("category", "无法判断")
        reason = item.get("reason", "")

        if item_type == "folder":
            action = "复制文件夹" if load_config()["folder_mode"] == "copy" else "移动文件夹"
        else:
            action = "移动"

        if not src.exists():
            print(f"[跳过] 原路径不存在：{src}")
            continue

        print(
            f"[预演-{action}] {src} -> {dst} | "
            f"类型：{item_type} | 分类：{category} | 原因：{reason}"
        )

    print("\n预演完成，没有移动/复制任何文件。")

    update_state("last_dryrun_at", "完成行动预演")


def apply_plan(confirm_callback=None):
    if not Path(REVIEW_FILE).exists() and not Path(PLAN_FILE).exists():
        print("缺少执行来源。请先运行：python desktop_agent_cli.py preview")
        return

    if not Path(REVIEW_FILE).exists():
        print("警告：没有检测到人工审核文件 desktop_human_review.json。")
        print("建议先运行：python desktop_agent_cli.py review")
        if confirm_callback is not None:
            if not confirm_callback():
                print("已取消执行。")
                return
        else:
            confirm = input("仍然继续执行原始计划？输入 YES 继续：")
            if confirm != "YES":
                print("已取消执行。")
                return

    config = load_config()
    items, source_file = load_execution_items()

    action_log = {
        "created_at": now_str(),
        "source_plan": source_file,
        "actions": []
    }

    print("=" * 80)
    print("Step 3 - Action：执行整理计划")
    print("=" * 80)

    for item in items:
        src = Path(item["path"])

        if not src.exists():
            msg = f"[跳过] 原路径不存在：{src}"
            print(msg)
            action_log["actions"].append({
                "status": "skipped",
                "reason": "source_not_exists",
                "src": str(src),
                "dst": "",
                "item": item
            })
            continue

        dst = get_unique_path(get_target_path(item))
        dst.parent.mkdir(parents=True, exist_ok=True)

        item_type = item["type"]

        try:
            if item_type == "folder" and config["folder_mode"] == "copy":
                shutil.copytree(str(src), str(dst), dirs_exist_ok=False, ignore_dangling_symlinks=True)
                status = "copied_folder"
                msg = f"[已复制文件夹] {src} -> {dst}"
            else:
                shutil.move(str(src), str(dst))
                status = "moved"
                msg = f"[已移动] {src} -> {dst}"

            print(msg)
            action_log["actions"].append({
                "status": status,
                "src": str(src),
                "dst": str(dst),
                "item": item
            })

        except Exception as e:
            msg = f"[失败] {src} -> {dst}，原因：{e}"
            print(msg)
            action_log["actions"].append({
                "status": "failed",
                "reason": str(e),
                "src": str(src),
                "dst": str(dst),
                "item": item
            })

    save_json(ACTION_LOG_FILE, action_log)
    print(f"\n执行日志已保存：{ACTION_LOG_FILE}")

    update_state(
        "last_apply_at",
        f"执行整理计划完成，日志：{ACTION_LOG_FILE}"
    )


def undo_last_action():
    if not require_file(ACTION_LOG_FILE, "python desktop_agent_cli.py apply"):
        return

    log = load_json(ACTION_LOG_FILE)
    actions = list(reversed(log["actions"]))

    print("=" * 80)
    print("Step 4 - Undo：撤销上一次整理")
    print("=" * 80)

    undo_log = []

    for action in actions:
        status = action.get("status")
        src = Path(action.get("src", ""))
        dst = Path(action.get("dst", ""))

        if status == "moved":
            if dst.exists():
                try:
                    target = get_unique_path(src)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(target))
                    msg = f"[已撤销移动] {dst} -> {target}"
                except Exception as e:
                    msg = f"[撤销失败] {dst}，原因：{e}"
            else:
                msg = f"[跳过] 目标不存在，无法撤销：{dst}"

        elif status == "copied_folder":
            msg = f"[提示] 文件夹当时是复制，不自动删除 D 盘副本：{dst}"

        else:
            msg = f"[跳过] 状态 {status} 不需要撤销：{dst}"

        print(msg)
        undo_log.append(msg)

    with open("desktop_undo_log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(undo_log))

    print("\n撤销日志已保存：desktop_undo_log.txt")

    update_state("last_undo_at", "撤销操作已完成")
