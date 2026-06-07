import shutil
from pathlib import Path

from desktop_agent.categories import CATEGORIES, NORMAL_CATEGORY_FOLDERS, SHORTCUT_CATEGORY_FOLDERS
from desktop_agent.config import load_config
from desktop_agent.i18n import t
from desktop_agent.planner import PLAN_FILE
from desktop_agent.reviewer import REVIEW_FILE
from desktop_agent.state import now_str, require_file, update_state
from desktop_agent.storage import load_json, save_json


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
                "reason": item.get("reason", ""),
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
        print(t("executor.missing_source"))
        return

    items, source_file = load_execution_items()
    print("=" * 80)
    print(t("executor.dryrun_header"))
    print("=" * 80)
    print(t("executor.source_file", source=source_file))

    for item in items:
        src = Path(item["path"])
        dst = get_target_path(item)
        item_type = item.get("type", "file")
        category = item.get("human_category") or item.get("category", "无法判断")
        reason = item.get("reason", "")

        if item_type == "folder":
            action = t("executor.copy_folder") if load_config()["folder_mode"] == "copy" else t("executor.move_folder")
        else:
            action = t("executor.move_item")

        if not src.exists():
            print(t("executor.skip_missing_source", src=src))
            continue

        print(
            t(
                "executor.dryrun_line",
                action=action,
                src=src,
                dst=dst,
                item_type=item_type,
                category=category,
                reason=reason,
            )
        )

    print("")
    print(t("executor.dryrun_done"))
    update_state("last_dryrun_at", t("executor.dryrun_state"))


def apply_plan(confirm_callback=None):
    if not Path(REVIEW_FILE).exists() and not Path(PLAN_FILE).exists():
        print(t("executor.missing_source"))
        return

    if not Path(REVIEW_FILE).exists():
        print(t("executor.review_missing_warning"))
        print(t("executor.review_missing_suggestion"))
        if confirm_callback is not None:
            if not confirm_callback():
                print(t("executor.execution_cancelled"))
                return
        else:
            confirm = input(t("executor.raw_confirm_prompt"))
            if confirm != "YES":
                print(t("executor.execution_cancelled"))
                return

    config = load_config()
    items, source_file = load_execution_items()
    action_log = {"created_at": now_str(), "source_plan": source_file, "actions": []}

    print("=" * 80)
    print(t("executor.apply_header"))
    print("=" * 80)

    for item in items:
        src = Path(item["path"])

        if not src.exists():
            msg = t("executor.skip_missing_source", src=src)
            print(msg)
            action_log["actions"].append(
                {
                    "status": "skipped",
                    "reason": "source_not_exists",
                    "src": str(src),
                    "dst": "",
                    "item": item,
                }
            )
            continue

        dst = get_unique_path(get_target_path(item))
        dst.parent.mkdir(parents=True, exist_ok=True)
        item_type = item["type"]

        try:
            if item_type == "folder" and config["folder_mode"] == "copy":
                shutil.copytree(str(src), str(dst), dirs_exist_ok=False, ignore_dangling_symlinks=True)
                status = "copied_folder"
                msg = t("executor.copied_folder", src=src, dst=dst)
            else:
                shutil.move(str(src), str(dst))
                status = "moved"
                msg = t("executor.moved_item", src=src, dst=dst)

            print(msg)
            action_log["actions"].append({"status": status, "src": str(src), "dst": str(dst), "item": item})
        except Exception as exc:
            msg = t("executor.apply_failed", src=src, dst=dst, error=exc)
            print(msg)
            action_log["actions"].append(
                {
                    "status": "failed",
                    "reason": str(exc),
                    "src": str(src),
                    "dst": str(dst),
                    "item": item,
                }
            )

    save_json(ACTION_LOG_FILE, action_log)
    print("")
    print(t("executor.action_log_saved", path=ACTION_LOG_FILE))
    update_state("last_apply_at", t("executor.apply_state", path=ACTION_LOG_FILE))


def undo_last_action():
    if not require_file(ACTION_LOG_FILE, "python desktop_agent_cli.py apply"):
        return

    log = load_json(ACTION_LOG_FILE)
    actions = list(reversed(log["actions"]))

    print("=" * 80)
    print(t("executor.undo_header"))
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
                    msg = t("executor.undo_moved", src=dst, dst=target)
                except Exception as exc:
                    msg = t("executor.undo_failed", path=dst, error=exc)
            else:
                msg = t("executor.undo_skip_missing", path=dst)
        elif status == "copied_folder":
            msg = t("executor.undo_copy_notice", path=dst)
        else:
            msg = t("executor.undo_skip_status", status=status, path=dst)

        print(msg)
        undo_log.append(msg)

    undo_file = "desktop_undo_log.txt"
    with open(undo_file, "w", encoding="utf-8") as handle:
        handle.write("\n".join(undo_log))

    print("")
    print(t("executor.undo_log_saved", path=undo_file))
    update_state("last_undo_at", t("executor.undo_state"))
