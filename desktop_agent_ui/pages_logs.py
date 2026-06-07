import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from desktop_agent.i18n import t
from desktop_agent_ui.theme import *


PROJECT_DIR = Path.cwd()
CONFIG_FILE = Path("config.json")

try:
    from desktop_agent.version import APP_NAME, APP_VERSION
except Exception:
    APP_NAME = "Qwen Desktop Organizer Agent"
    APP_VERSION = "v2.2"


class LogsPageMixin:
    def build_logs_page(self, parent):
        self.page_header(parent, t("logs.page_title"), t("logs.page_subtitle"))

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        summary = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        summary.grid(row=0, column=0, padx=6, pady=(6, 8), sticky="ew")
        summary.grid_columnconfigure(0, weight=1)

        self.log_status_var = ctk.StringVar(value=t("logs.default_status"))
        self.log_file_var = ctk.StringVar(value=self._default_log_file_text())

        ctk.CTkLabel(summary, text=t("logs.section_title"), font=("Microsoft YaHei UI", 14, "bold"), text_color=COL_TEXT).grid(row=0, column=0, padx=18, pady=(14, 2), sticky="w")
        ctk.CTkLabel(summary, textvariable=self.log_status_var, font=("Microsoft YaHei UI", 11), text_color=COL_TEXT_MUTED, wraplength=980, justify="left").grid(row=1, column=0, padx=18, pady=(0, 2), sticky="w")
        ctk.CTkLabel(summary, textvariable=self.log_file_var, font=("Microsoft YaHei UI", 11), text_color=COL_TEXT_MUTED, wraplength=980, justify="left").grid(row=2, column=0, padx=18, pady=(0, 14), sticky="w")

        actions = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        actions.grid(row=1, column=0, padx=6, pady=6, sticky="ew")
        action_row = ctk.CTkFrame(actions, fg_color="transparent")
        action_row.grid(row=0, column=0, padx=12, pady=12, sticky="w")

        button_specs = [
            (t("logs.open_folder"), self.open_logs_folder, None),
            (t("logs.open_current"), self.open_current_log_file, None),
            (t("logs.create_report"), self.create_diagnostic_report, None),
            (t("logs.clear_output"), self.clear_output, "#6b7280"),
        ]
        for idx, (text, command, color) in enumerate(button_specs):
            kwargs = {"text": text, "corner_radius": 8, "width": 170, "command": command}
            if color:
                kwargs["fg_color"] = color
                kwargs["hover_color"] = "#4b5563"
            ctk.CTkButton(action_row, **kwargs).grid(row=0, column=idx, padx=(0, 10))

        console_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        console_card.grid(row=2, column=0, padx=6, pady=8, sticky="nsew")
        console_card.grid_rowconfigure(2, weight=1)
        console_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(console_card, text=t("logs.live_output_title"), font=("Microsoft YaHei UI", 14, "bold"), text_color=COL_TEXT).grid(row=0, column=0, padx=18, pady=(14, 2), sticky="w")
        ctk.CTkLabel(console_card, text=t("logs.live_output_intro"), font=("Microsoft YaHei UI", 11), text_color=COL_TEXT_MUTED, wraplength=980, justify="left").grid(row=1, column=0, padx=18, pady=(0, 8), sticky="w")

        console_surface = ctk.CTkFrame(console_card, fg_color="#111827", corner_radius=12)
        console_surface.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="nsew")
        console_surface.grid_rowconfigure(0, weight=1)
        console_surface.grid_columnconfigure(0, weight=1)

        self.output_text = ctk.CTkTextbox(
            console_surface,
            font=("Consolas", 12),
            corner_radius=10,
            fg_color="#111827",
            text_color="#e5e7eb",
            border_width=0,
        )
        self.output_text.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")
        self.refresh_logs_summary()

    def _default_log_file_text(self):
        return t("logs.current_log_none")

    def refresh_logs_summary(self):
        if hasattr(self, "log_status_var"):
            self.log_status_var.set(t("logs.default_status"))
        if hasattr(self, "log_file_var"):
            if getattr(self, "current_log_file", None):
                self.log_file_var.set(t("logs.current_log_prefix", path=str(self.current_log_file)))
            else:
                self.log_file_var.set(self._default_log_file_text())

    def sanitize_config_for_report(self, config):
        safe_config = dict(config)
        for key in ["api_key", "openai_api_key", "deepseek_api_key", "qwen_api_key", "authorization", "token", "access_token"]:
            if key in safe_config and safe_config[key]:
                safe_config[key] = "***REDACTED***"
        return safe_config

    def create_diagnostic_report(self):
        try:
            reports_dir = PROJECT_DIR / "diagnostic_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_zip = reports_dir / f"diagnostic_report_{timestamp}.zip"
            temp_dir = reports_dir / f"diagnostic_report_{timestamp}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            (temp_dir / "diagnostic_info.txt").write_text(
                f"{APP_NAME} {APP_VERSION} Diagnostic Report\n"
                f"Created at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Project dir: {PROJECT_DIR}\n"
                f"Current log file: {self.current_log_file}\n"
                f"Python: {sys.version}\n"
                f"Frozen exe: {getattr(sys, 'frozen', False)}\n",
                encoding="utf-8",
            )

            if CONFIG_FILE.exists():
                config = self.read_config_safely()
                safe_config = self.sanitize_config_for_report(config)
                with open(temp_dir / "config_sanitized.json", "w", encoding="utf-8") as f:
                    json.dump(safe_config, f, ensure_ascii=False, indent=2)

            if self.current_log_file and self.current_log_file.exists():
                shutil.copy2(self.current_log_file, temp_dir / self.current_log_file.name)

            runtime_target = temp_dir / "runtime_files"
            runtime_target.mkdir(exist_ok=True)

            for filename in [
                "agent_state.json",
                "desktop_observation.json",
                "desktop_agent_plan.json",
                "desktop_human_review.json",
                "desktop_action_log.json",
                "desktop_undo_log.txt",
                "agent_memory.json",
                "desktop_agent_explanation.md",
                "desktop_agent_explanation.json",
            ]:
                path = PROJECT_DIR / filename
                if path.exists():
                    shutil.copy2(path, runtime_target / filename)

            with zipfile.ZipFile(report_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in temp_dir.rglob("*"):
                    if file_path.is_file():
                        zipf.write(file_path, file_path.relative_to(temp_dir))

            shutil.rmtree(temp_dir, ignore_errors=True)
            messagebox.showinfo(t("logs.report_created_title"), t("logs.report_created_message", path=str(report_zip)))
            subprocess.Popen(f'explorer "{reports_dir}"')
        except Exception as exc:
            messagebox.showerror(t("logs.report_failed_title"), str(exc))

    def open_project_folder(self):
        try:
            subprocess.Popen(f'explorer "{PROJECT_DIR}"')
        except Exception as exc:
            messagebox.showerror(t("common.error_title"), str(exc))

    def open_target_folder(self):
        try:
            config = self.read_config_safely()
            target_root = config.get("normal_target_root", "").strip()
            if not target_root:
                messagebox.showwarning(t("logs.target_missing_title"), t("logs.target_missing_message"))
                return

            target_path = Path(target_root)
            if not target_path.exists():
                if not messagebox.askyesno(t("logs.target_not_found_title"), t("logs.target_not_found_message", path=str(target_path))):
                    return
                target_path.mkdir(parents=True, exist_ok=True)

            subprocess.Popen(f'explorer "{target_path}"')
        except Exception as exc:
            messagebox.showerror(t("logs.target_open_failed_title"), str(exc))
