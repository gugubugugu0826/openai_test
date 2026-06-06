# desktop_agent/state.py

from datetime import datetime
from pathlib import Path

from desktop_agent.storage import save_json, load_json


STATE_FILE = "agent_state.json"


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def default_state():
    return {
        "last_scan_at": "",
        "last_preview_at": "",
        "last_review_at": "",
        "last_learn_at": "",
        "last_dryrun_at": "",
        "last_apply_at": "",
        "last_undo_at": "",
        "notes": []
    }


def load_state():
    path = Path(STATE_FILE)

    if not path.exists():
        state = default_state()
        save_json(STATE_FILE, state)
        return state

    try:
        return load_json(STATE_FILE)
    except Exception:
        state = default_state()
        save_json(STATE_FILE, state)
        return state


def save_state(state):
    save_json(STATE_FILE, state)


def update_state(key, note=None):
    state = load_state()
    state[key] = now_str()

    if note:
        state.setdefault("notes", [])
        state["notes"].append({
            "time": now_str(),
            "note": note
        })

    save_state(state)


def show_state():
    state = load_state()

    print("=" * 80)
    print("Agent State：当前状态")
    print("=" * 80)

    print(f"last_scan_at:    {state.get('last_scan_at', '')}")
    print(f"last_preview_at: {state.get('last_preview_at', '')}")
    print(f"last_review_at:  {state.get('last_review_at', '')}")
    print(f"last_learn_at:   {state.get('last_learn_at', '')}")
    print(f"last_dryrun_at:  {state.get('last_dryrun_at', '')}")
    print(f"last_apply_at:   {state.get('last_apply_at', '')}")
    print(f"last_undo_at:    {state.get('last_undo_at', '')}")

    notes = state.get("notes", [])

    if notes:
        print("\n最近记录：")
        for note in notes[-5:]:
            print(f"- {note.get('time')}: {note.get('note')}")


def require_file(file_path, hint):
    if not Path(file_path).exists():
        print("=" * 80)
        print("Agent 状态检查失败")
        print("=" * 80)
        print(f"缺少文件：{file_path}")
        print(f"建议先运行：{hint}")
        return False

    return True