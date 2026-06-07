from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from desktop_agent.i18n import t


TASK_NAME = "DesktopAgentAutoRun"


def _python_exe() -> str:
    return sys.executable


def _script_path() -> str:
    return str(Path("desktop_agent_cli.py").resolve())


def create_scheduled_task(frequency: str = "weekly", hour: int = 9, day: str = "sunday") -> bool:
    """
    Create a Windows Scheduled Task that runs `python desktop_agent_cli.py auto-run`.

    frequency: "daily" | "weekly"
    hour:      0-23
    day:       day of week name (only used when frequency=="weekly")
    Returns True on success, False on failure.
    """
    python = _python_exe()
    script = _script_path()
    start_time = f"{hour:02d}:00"

    if frequency == "daily":
        schedule_args = ["/SC", "DAILY", "/ST", start_time]
    else:
        day_map = {
            "monday": "MON", "tuesday": "TUE", "wednesday": "WED",
            "thursday": "THU", "friday": "FRI", "saturday": "SAT", "sunday": "SUN",
        }
        sc_day = day_map.get(day.lower(), "SUN")
        schedule_args = ["/SC", "WEEKLY", "/D", sc_day, "/ST", start_time]

    cmd = [
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", f'"{python}" "{script}" auto-run',
        *schedule_args,
        "/F",  # Overwrite if exists
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def delete_scheduled_task() -> bool:
    """Remove the scheduled task. Returns True on success."""
    cmd = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def get_task_status() -> dict:
    """
    Return a dict with task info:
    {exists, next_run, last_run, status}
    """
    cmd = ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="gbk", errors="replace", timeout=30)
        if result.returncode != 0:
            return {"exists": False}

        info: dict = {"exists": True}
        for line in result.stdout.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if "Next Run" in key or "下次运行时间" in key:
                info["next_run"] = value
            elif "Last Run" in key or "上次运行时间" in key:
                info["last_run"] = value
            elif "Status" in key or "状态" in key:
                info["status"] = value
        return info
    except Exception:
        return {"exists": False}


def apply_schedule_from_config(config: dict) -> bool:
    """
    Read schedule settings from config and create/delete the task accordingly.
    Returns True if any action was taken successfully.
    """
    schedule = config.get("schedule", {})
    if not schedule.get("enabled", False):
        status = get_task_status()
        if status.get("exists"):
            return delete_scheduled_task()
        return True  # Nothing to do

    return create_scheduled_task(
        frequency=schedule.get("frequency", "weekly"),
        hour=int(schedule.get("hour", 9)),
        day=schedule.get("day", "sunday"),
    )


def show_schedule() -> None:
    """CLI display of current schedule status."""
    print("=" * 80)
    print(t("scheduler.header", default="计划任务状态"))
    print("=" * 80)
    status = get_task_status()
    if not status.get("exists"):
        print(t("scheduler.not_configured", default="未配置计划任务"))
        print(t("scheduler.hint", default="在 Config 页面 Schedule 区域开启定时整理"))
        return
    print(t("scheduler.next_run", value=status.get("next_run", "N/A"), default=f"下次运行：{status.get('next_run', 'N/A')}"))
    print(t("scheduler.last_run", value=status.get("last_run", "N/A"), default=f"上次运行：{status.get('last_run', 'N/A')}"))
    print(t("scheduler.status", value=status.get("status", "N/A"), default=f"状态：{status.get('status', 'N/A')}"))
