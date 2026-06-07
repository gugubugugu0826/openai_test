import subprocess
import unittest
from unittest import mock

from desktop_agent import scheduler as sched
from desktop_agent.scheduler import (
    TASK_NAME,
    apply_schedule_from_config,
    create_scheduled_task,
    delete_scheduled_task,
    get_task_status,
)


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class CreateScheduledTaskTests(unittest.TestCase):
    def test_weekly_builds_weekly_args(self):
        with mock.patch.object(sched.subprocess, "run", return_value=_completed(0)) as m:
            ok = create_scheduled_task(frequency="weekly", hour=9, day="sunday")
        self.assertTrue(ok)
        cmd = m.call_args[0][0]
        self.assertIn("/SC", cmd)
        self.assertIn("WEEKLY", cmd)
        self.assertIn("SUN", cmd)
        self.assertIn("09:00", cmd)
        self.assertIn(TASK_NAME, cmd)

    def test_daily_builds_daily_args(self):
        with mock.patch.object(sched.subprocess, "run", return_value=_completed(0)) as m:
            ok = create_scheduled_task(frequency="daily", hour=22)
        self.assertTrue(ok)
        cmd = m.call_args[0][0]
        self.assertIn("DAILY", cmd)
        self.assertIn("22:00", cmd)
        self.assertNotIn("WEEKLY", cmd)

    def test_nonzero_returncode_means_failure(self):
        with mock.patch.object(sched.subprocess, "run", return_value=_completed(1)):
            self.assertFalse(create_scheduled_task())

    def test_exception_is_caught_and_returns_false(self):
        with mock.patch.object(sched.subprocess, "run", side_effect=OSError("denied")):
            self.assertFalse(create_scheduled_task())

    def test_unknown_day_defaults_to_sunday(self):
        with mock.patch.object(sched.subprocess, "run", return_value=_completed(0)) as m:
            create_scheduled_task(frequency="weekly", day="notaday")
        cmd = m.call_args[0][0]
        self.assertIn("SUN", cmd)


class DeleteScheduledTaskTests(unittest.TestCase):
    def test_delete_success(self):
        with mock.patch.object(sched.subprocess, "run", return_value=_completed(0)) as m:
            self.assertTrue(delete_scheduled_task())
        cmd = m.call_args[0][0]
        self.assertIn("/Delete", cmd)
        self.assertIn(TASK_NAME, cmd)

    def test_delete_exception_returns_false(self):
        with mock.patch.object(sched.subprocess, "run", side_effect=OSError):
            self.assertFalse(delete_scheduled_task())


class GetTaskStatusTests(unittest.TestCase):
    def test_not_exist_when_query_fails(self):
        with mock.patch.object(sched.subprocess, "run", return_value=_completed(1)):
            self.assertEqual(get_task_status(), {"exists": False})

    def test_parses_status_fields(self):
        stdout = (
            "Folder: \\\n"
            "HostName:    PC\n"
            "TaskName:    \\DesktopAgentAutoRun\n"
            "Next Run Time:   2026/6/14 9:00:00\n"
            "Last Run Time:   2026/6/7 9:00:00\n"
            "Status:          Ready\n"
        )
        with mock.patch.object(sched.subprocess, "run", return_value=_completed(0, stdout=stdout)):
            info = get_task_status()
        self.assertTrue(info["exists"])
        self.assertIn("2026/6/14", info["next_run"])
        self.assertIn("2026/6/7", info["last_run"])
        self.assertEqual(info["status"], "Ready")

    def test_exception_returns_not_exist(self):
        with mock.patch.object(sched.subprocess, "run", side_effect=OSError):
            self.assertEqual(get_task_status(), {"exists": False})


class ApplyScheduleFromConfigTests(unittest.TestCase):
    def test_disabled_with_no_existing_task_is_noop(self):
        with mock.patch.object(sched, "get_task_status", return_value={"exists": False}):
            self.assertTrue(apply_schedule_from_config({"schedule": {"enabled": False}}))

    def test_disabled_with_existing_task_deletes(self):
        with mock.patch.object(sched, "get_task_status", return_value={"exists": True}), \
             mock.patch.object(sched, "delete_scheduled_task", return_value=True) as md:
            self.assertTrue(apply_schedule_from_config({"schedule": {"enabled": False}}))
            md.assert_called_once()

    def test_enabled_creates_task_with_config_values(self):
        with mock.patch.object(sched, "create_scheduled_task", return_value=True) as mc:
            apply_schedule_from_config({"schedule": {"enabled": True, "frequency": "daily", "hour": 7, "day": "monday"}})
        mc.assert_called_once_with(frequency="daily", hour=7, day="monday")

    def test_missing_schedule_key_treated_as_disabled(self):
        with mock.patch.object(sched, "get_task_status", return_value={"exists": False}):
            self.assertTrue(apply_schedule_from_config({}))


if __name__ == "__main__":
    unittest.main()
