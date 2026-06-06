import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from desktop_agent_ui.theme import *

PROJECT_DIR = Path.cwd()
CONFIG_FILE = Path("config.json")
LOG_DIR = Path("logs")
OBSERVATION_FILE = Path("desktop_observation.json")
PLAN_FILE = Path("desktop_agent_plan.json")
REVIEW_FILE = Path("desktop_human_review.json")
ACTION_LOG_FILE = Path("desktop_action_log.json")
STATE_FILE = Path("agent_state.json")
MEMORY_FILE = Path("agent_memory.json")
EXPLANATION_MD_FILE = Path("desktop_agent_explanation.md")
EXPLANATION_JSON_FILE = Path("desktop_agent_explanation.json")

try:
    from desktop_agent.version import APP_NAME, APP_VERSION
except Exception:
    APP_NAME = "Qwen Desktop Organizer Agent"
    APP_VERSION = "v2.0"


class LogsPageMixin:
    def build_logs_page(self, parent):
        self.page_header(
            parent,
            "运行日志",
            "查看运行输出、打开日志文件、生成错误报告。",
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        summary = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        summary.grid(row=0, column=0, padx=6, pady=(6, 8), sticky="ew")
        summary.grid_columnconfigure(0, weight=1)

        self.log_status_var = ctk.StringVar(value="运行输出会实时显示在下方日志窗口。")
        self.log_file_var = ctk.StringVar(value="当前日志文件：尚未创建")

        ctk.CTkLabel(
            summary,
            text="日志与诊断",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color=COL_TEXT,
        ).grid(row=0, column=0, padx=18, pady=(14, 2), sticky="w")
        ctk.CTkLabel(
            summary,
            textvariable=self.log_status_var,
            font=("Microsoft YaHei UI", 11),
            text_color=COL_TEXT_MUTED,
            wraplength=980,
            justify="left",
        ).grid(row=1, column=0, padx=18, pady=(0, 2), sticky="w")
        ctk.CTkLabel(
            summary,
            textvariable=self.log_file_var,
            font=("Microsoft YaHei UI", 11),
            text_color=COL_TEXT_MUTED,
            wraplength=980,
            justify="left",
        ).grid(row=2, column=0, padx=18, pady=(0, 14), sticky="w")

        actions = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        actions.grid(row=1, column=0, padx=6, pady=6, sticky="ew")
        actions.grid_columnconfigure(0, weight=1)

        action_row = ctk.CTkFrame(actions, fg_color="transparent")
        action_row.grid(row=0, column=0, padx=12, pady=12, sticky="w")

        ctk.CTkButton(
            action_row,
            text="打开 logs 文件夹",
            corner_radius=8,
            width=150,
            command=self.open_logs_folder,
        ).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkButton(
            action_row,
            text="打开当前日志",
            corner_radius=8,
            width=150,
            command=self.open_current_log_file,
        ).grid(row=0, column=1, padx=(0, 10))
        ctk.CTkButton(
            action_row,
            text="生成错误报告包",
            corner_radius=8,
            width=160,
            command=self.create_diagnostic_report,
        ).grid(row=0, column=2, padx=(0, 10))
        ctk.CTkButton(
            action_row,
            text="清空输出窗口",
            corner_radius=8,
            width=150,
            fg_color="#6b7280",
            hover_color="#4b5563",
            command=self.clear_output,
        ).grid(row=0, column=3)

        console_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        console_card.grid(row=2, column=0, padx=6, pady=8, sticky="nsew")
        console_card.grid_rowconfigure(1, weight=1)
        console_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            console_card,
            text="实时输出",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color=COL_TEXT,
        ).grid(row=0, column=0, padx=18, pady=(14, 2), sticky="w")
        ctk.CTkLabel(
            console_card,
            text="这里会显示扫描、生成方案、应用整理和模型运行过程中的输出。",
            font=("Microsoft YaHei UI", 11),
            text_color=COL_TEXT_MUTED,
        ).grid(row=1, column=0, padx=18, pady=(0, 8), sticky="w")

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

    def refresh_logs_summary(self):
        if hasattr(self, "log_status_var"):
            self.log_status_var.set("运行输出会实时显示在下方日志窗口。建议在执行 Apply 前先看一遍关键输出。")
        if hasattr(self, "log_file_var"):
            if getattr(self, "current_log_file", None):
                self.log_file_var.set(f"当前日志文件：{self.current_log_file}")
            else:
                self.log_file_var.set("当前日志文件：尚未创建")

    def sanitize_config_for_report(self, config):
        safe_config = dict(config)

        for key in [
            "api_key",
            "openai_api_key",
            "deepseek_api_key",
            "qwen_api_key",
            "authorization",
            "token",
            "access_token",
        ]:
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

            messagebox.showinfo(
                "错误报告已生成",
                f"错误报告包已生成：\n{report_zip}\n\n里面的 config 已自动隐藏 API Key。",
            )
            subprocess.Popen(f'explorer "{reports_dir}"')
        except Exception as e:
            messagebox.showerror("生成错误报告失败", str(e))

    def open_project_folder(self):
        try:
            subprocess.Popen(f'explorer "{PROJECT_DIR}"')
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def open_target_folder(self):
        try:
            config = self.read_config_safely()
            target_root = config.get("normal_target_root", "").strip()

            if not target_root:
                messagebox.showwarning("目标目录为空", "请先在「设置」里填写整理目标目录。")
                return

            target_path = Path(target_root)

            if not target_path.exists():
                if not messagebox.askyesno("目标目录不存在", f"{target_path}\n\n是否创建？"):
                    return
                target_path.mkdir(parents=True, exist_ok=True)

            subprocess.Popen(f'explorer "{target_path}"')
        except Exception as e:
            messagebox.showerror("打开整理目标目录失败", str(e))
