# desktop_agent_gui.py

import os
import sys
import json
import queue
import shutil
import zipfile
import threading
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime

import customtkinter as ctk


# =====================================================
# App Path
# =====================================================

def get_app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_DIR = get_app_dir()
os.chdir(PROJECT_DIR)

REVIEW_FILE = PROJECT_DIR / "desktop_human_review.json"
CONFIG_FILE = PROJECT_DIR / "config.json"
LOG_DIR = PROJECT_DIR / "logs"
README_FILE = PROJECT_DIR / "README_使用说明.txt"

OBSERVATION_FILE = PROJECT_DIR / "desktop_observation.json"
PLAN_FILE = PROJECT_DIR / "desktop_agent_plan.json"
ACTION_LOG_FILE = PROJECT_DIR / "desktop_action_log.json"
STATE_FILE = PROJECT_DIR / "agent_state.json"
MEMORY_FILE = PROJECT_DIR / "agent_memory.json"

EXPLANATION_MD_FILE = PROJECT_DIR / "desktop_agent_explanation.md"
EXPLANATION_JSON_FILE = PROJECT_DIR / "desktop_agent_explanation.json"


# =====================================================
# Agent Core Imports
# =====================================================

from desktop_agent.categories import CATEGORIES
from desktop_agent.healthcheck import print_healthcheck, run_healthcheck
from desktop_agent.i18n import (
    get_category_display,
    get_category_display_options,
    get_language,
    get_language_by_label,
    get_language_label,
    install_runtime_output_translation,
    is_english,
    patch_customtkinter,
    set_language,
    t,
)
from desktop_agent.scanner import scan_desktop
from desktop_agent.planner import preview_plan
from desktop_agent.reviewer import create_human_review, learn_from_review
from desktop_agent.executor import dryrun_plan, apply_plan, undo_last_action
from desktop_agent.memory import show_memory
from desktop_agent.state import show_state
from desktop_agent.workflow import run_workflow
from desktop_agent.plan_explainer import explain_current_plan
from desktop_agent_ui.utils import get_effective_scan_paths, format_scan_paths
from desktop_agent_ui.dialogs import ModelDownloadMixin
from desktop_agent_ui.pages_dashboard import DashboardPageMixin
from desktop_agent_ui.pages_workflow import WorkflowPageMixin
from desktop_agent_ui.pages_review import ReviewPageMixin
from desktop_agent_ui.pages_config import ConfigPageMixin
from desktop_agent_ui.pages_memory import MemoryPageMixin
from desktop_agent_ui.pages_explanation import ExplanationPageMixin
from desktop_agent_ui.pages_logs import LogsPageMixin
from desktop_agent_ui.pages_help import HelpPageMixin

try:
    from desktop_agent.version import APP_NAME, APP_VERSION
except Exception:
    APP_NAME = "Qwen Desktop Organizer Agent"
    APP_VERSION = "v2.0"

# 关闭程序时用于停止内置 llama-server（避免它占用文件导致目录删不掉）
try:
    from desktop_agent.builtin_llm import stop_builtin_server
except Exception:
    def stop_builtin_server():
        pass

# 给普通用户看的产品名（窗口标题仍用 APP_NAME）
APP_TITLE = "桌面整理助手"

# 模型直链（.gguf）。留空时首次运行只提供“手动选择 / 跳过”。
# 也可在 设置 → 自带 AI 引擎 里填写 builtin_model_url 覆盖此处。
# =====================================================
# UI Palette
# =====================================================

COL_BG          = "#f4f6fa"   # 正文区背景
COL_SIDEBAR     = "#ffffff"   # 侧边栏背景
COL_CARD        = "#ffffff"   # 卡片
COL_ACCENT      = "#2563eb"   # 主色
COL_ACCENT_SOFT = "#eef2ff"   # 选中态浅底
COL_TEXT        = "#111827"
COL_TEXT_MUTED  = "#6b7280"
COL_TEXT_NAV    = "#374151"
COL_HOVER       = "#f1f3f9"
COL_OK          = "#10b981"
COL_OK_SOFT     = "#ecfdf5"
COL_WARN        = "#f59e0b"
COL_WARN_SOFT   = "#fffbeb"
COL_WARN_TEXT   = "#b45309"
COL_DANGER      = "#dc2626"
COL_BORDER      = "#e5e7eb"


# 默认演示记忆：让用户第一次打开「整理记忆」就能看到“命中关键词→分类”的样子。
# 这些都是示例规则，用户可随时删除或修改。
DEFAULT_MEMORY = {
    "rules": [
        {"match": "简历", "category": "简历求职", "note": "示例规则：文件名含“简历”→简历求职（可删除）"},
        {"match": "发票", "category": "证件合同", "note": "示例规则：含“发票”→证件合同（可删除）"},
        {"match": "课程", "category": "课程资料", "note": "示例规则：含“课程”→课程资料（可删除）"},
    ]
}


class QueueWriter:
    def __init__(self, output_queue):
        self.output_queue = output_queue

    def write(self, text):
        if text:
            self.output_queue.put(text)

    def flush(self):
        pass


class DesktopAgentGUI(
    ModelDownloadMixin,
    DashboardPageMixin,
    WorkflowPageMixin,
    ReviewPageMixin,
    ConfigPageMixin,
    MemoryPageMixin,
    ExplanationPageMixin,
    LogsPageMixin,
    HelpPageMixin,
):
    # 主导航（普通用户）
    PRIMARY_NAV = [
        ("Home",     "整理桌面"),
        ("Review",   "整理方案"),
        ("Settings", "设置"),
        ("Help",     "帮助"),
    ]
    # 高级导航（折叠在分隔线下方）
    ADVANCED_NAV = [
        ("Explanation", "计划解释"),
        ("Memory",      "整理记忆"),
        ("Logs",        "运行日志"),
        ("Advanced",    "高级操作"),
    ]
    # 每个页面对应的 Unicode 图标
    NAV_ICONS = {
        "Home":        "⌂",
        "Review":      "≡",
        "Settings":    "⚙",
        "Help":        "？",
        "Explanation": "◎",
        "Memory":      "★",
        "Logs":        "☰",
        "Advanced":    "⊞",
    }

    # 环境自检项 → 人话名称
    FRIENDLY_CHECKS = {
        "Config": "配置文件",
        "Desktop Path": "桌面 / 扫描位置",
        "Target Root": "整理目标位置",
        "Model": "AI 模型",
        "Builtin Runtime": "自带 AI 引擎",
        "Modules": "核心组件",
    }
    # 普通用户不需要看到的内部检查项
    HIDDEN_CHECKS = {"Ollama API", "OpenAI-compatible Config"}

    def __init__(self, root):
        self.root = root
        self.ensure_config_exists_for_startup()
        initial_config = self.read_config_safely()
        set_language(initial_config.get("ui_language"))
        patch_customtkinter(ctk)
        install_runtime_output_translation()

        self.root.title(f"{t(APP_TITLE)} {APP_VERSION}")
        self.root.geometry("1320x840")
        self.root.minsize(1180 if is_english() else 1120, 720)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.output_queue = queue.Queue()
        self.running = False
        self._checking = False

        self.guided_modal = None
        self.guided_on_done = None
        self.guided_status_var = None
        self.guided_pb = None
        self._last_output_line = ""

        self.memory_data = {"rules": []}

        # 未保存修改标记（用于切页提醒）
        self.config_dirty = False
        self.review_dirty = False
        self.memory_dirty = False
        self._loading_config = False

        self.current_log_file = None
        self.current_page = None

        self.pages = {}
        self.nav_buttons = {}
        self.nav_indicators = {}

        self.review_items = []
        self.review_filter_var = tk.StringVar(value=t("全部"))
        self.config_vars = {}
        self.dashboard_vars = {}
        self.init_log_file()

        self.build_ui()
        self.poll_output_queue()

        self.append_output("=" * 90 + "\n")
        self.append_output(f"{APP_NAME} {APP_VERSION} started.\n")
        self.append_output(f"App directory: {PROJECT_DIR}\n")
        self.append_output(f"Log file: {self.current_log_file}\n")
        self.append_output("=" * 90 + "\n")

        self.show_page("Home")
        self.update_home_summary()
        self.refresh_home_status()

        self.root.after(300, self.show_first_run_wizard_if_needed)
        self.root.after(1800, self.auto_check_updates_if_needed)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # =====================================================
    # Config Defaults
    # =====================================================

    def get_default_config(self, first_run_completed=True, provider="none"):
        return {
            "first_run_completed": first_run_completed,
            "llm_provider": provider,
            "ui_language": get_language(),

            "model": "qwen2.5-coder:14b",
            "ollama_url": "http://localhost:11434/api/generate",

            "api_base_url": "https://api.openai.com/v1/chat/completions",
            "api_model": "gpt-4.1-mini",
            "api_key": "",

            "builtin_server_host": "127.0.0.1",
            "builtin_server_port": 18080,
            "builtin_server_path": "runtime\\llama-server.exe",
            "builtin_model_path": "models\\qwen-small.gguf",
            "builtin_api_model": "builtin-model",
            "builtin_context_size": 4096,
            "builtin_threads": 8,
            "builtin_model_url": "",

            "desktop_path": "",
            "normal_target_root": "D:\\Desktop_Sorted",
            "folder_mode": "copy",
            "batch_size": 8,
            "max_internal_items_per_folder": 200,

            "update_manifest_url": "",
            "auto_check_updates": True,
        }

    def ensure_config_exists_for_startup(self):
        if CONFIG_FILE.exists():
            return

        default_config = self.get_default_config(
            first_run_completed=False,
            provider="none"
        )

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)

    def read_config_safely(self):
        if not CONFIG_FILE.exists():
            return self.get_default_config()

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            default_config = self.get_default_config()
            if isinstance(data, dict):
                default_config.update(data)
            return default_config
        except Exception:
            return self.get_default_config()

    # =====================================================
    # Builtin Model Helpers
    # =====================================================

    # =====================================================
    # Logs
    # =====================================================

    def init_log_file(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_log_file = LOG_DIR / f"session_{timestamp}.log"

        with open(self.current_log_file, "w", encoding="utf-8") as f:
            f.write(f"{APP_NAME} {APP_VERSION} Log\n")
            f.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Project dir: {PROJECT_DIR}\n")
            f.write("=" * 90 + "\n\n")
        if hasattr(self, "refresh_logs_summary"):
            self.refresh_logs_summary()

    def write_log(self, text):
        if not self.current_log_file:
            return

        try:
            with open(self.current_log_file, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

    def append_output(self, text):
        if hasattr(self, "output_text"):
            self.output_text.insert("end", text)
            self.output_text.see("end")
        self.write_log(text)

    def clear_output(self):
        self.output_text.delete("1.0", "end")
        self.write_log("\n[GUI] Output window cleared.\n")
        if hasattr(self, "log_status_var"):
            self.log_status_var.set(
                "Output cleared. New runtime output will appear below."
                if is_english() else
                "输出窗口已清空。新的运行输出会继续显示在下方。"
            )

    def open_logs_folder(self):
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(f'explorer "{LOG_DIR}"')
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def open_current_log_file(self):
        if not self.current_log_file or not self.current_log_file.exists():
            messagebox.showwarning(
                "没有日志文件" if not is_english() else "No Log File",
                "当前日志文件不存在。" if not is_english() else "The current log file does not exist."
            )
            return

        try:
            os.startfile(str(self.current_log_file))
        except Exception as e:
            messagebox.showerror("错误", str(e))

    # =====================================================
    # UI Base
    # =====================================================

    def build_ui(self):
        self.root.configure(fg_color=COL_BG)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        sidebar_width = 272 if is_english() else 232
        self.sidebar = ctk.CTkFrame(self.root, width=sidebar_width, corner_radius=0, fg_color=COL_SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        self.content = ctk.CTkFrame(self.root, corner_radius=0, fg_color=COL_BG)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.build_sidebar()
        self.build_pages()

    def _add_nav_button(self, page_name, text, row):
        icon = self.NAV_ICONS.get(page_name, "▸")

        wrapper = ctk.CTkFrame(self.sidebar, fg_color="transparent", corner_radius=0)
        wrapper.grid(row=row, column=0, padx=0, pady=1, sticky="ew")
        wrapper.grid_columnconfigure(1, weight=1)

        # 3px 左侧选中高亮条
        indicator = ctk.CTkFrame(wrapper, width=3, height=36, corner_radius=2, fg_color="transparent")
        indicator.grid(row=0, column=0, padx=(6, 0), pady=4, sticky="ns")

        btn = ctk.CTkButton(
            wrapper,
            text=f"  {icon}  {text}",
            height=36,
            corner_radius=8,
            anchor="w",
            fg_color="transparent",
            text_color=COL_TEXT_NAV,
            hover_color=COL_HOVER,
            font=ctk.CTkFont(size=14),
            command=lambda p=page_name: self.nav_to(p),
        )
        btn.grid(row=0, column=1, padx=(2, 10), sticky="ew")

        self.nav_buttons[page_name] = btn
        self.nav_indicators[page_name] = indicator

    def build_sidebar(self):
        self.sidebar.grid_columnconfigure(0, weight=1)
        r = 0

        ctk.CTkLabel(
            self.sidebar,
            text=t(APP_TITLE),
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COL_TEXT,
            anchor="w",
        ).grid(row=r, column=0, padx=18, pady=(22, 2), sticky="w")
        r += 1

        ctk.CTkLabel(
            self.sidebar,
            text=f"Desktop Agent  {APP_VERSION}",
            text_color=COL_TEXT_MUTED,
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).grid(row=r, column=0, padx=18, pady=(0, 8), sticky="w")
        r += 1

        # 主导航与标题之间的分隔线
        ctk.CTkFrame(
            self.sidebar, height=1, fg_color=COL_BORDER, corner_radius=0
        ).grid(row=r, column=0, padx=16, pady=(0, 8), sticky="ew")
        r += 1

        for page_name, text in self.PRIMARY_NAV:
            self._add_nav_button(page_name, text, r)
            r += 1

        # 高级分区分隔线
        ctk.CTkFrame(
            self.sidebar, height=1, fg_color=COL_BORDER, corner_radius=0
        ).grid(row=r, column=0, padx=16, pady=(10, 4), sticky="ew")
        r += 1

        ctk.CTkLabel(
            self.sidebar,
            text=t("高级"),
            text_color="#9ca3af",
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).grid(row=r, column=0, padx=20, pady=(0, 2), sticky="w")
        r += 1

        for page_name, text in self.ADVANCED_NAV:
            self._add_nav_button(page_name, text, r)
            r += 1

        self.sidebar.grid_rowconfigure(r, weight=1)
        r += 1

        self.status_var = tk.StringVar(value=t("就绪"))
        ctk.CTkLabel(
            self.sidebar,
            textvariable=self.status_var,
            text_color=COL_TEXT_MUTED,
            wraplength=230 if is_english() else 190,
            anchor="w",
            font=ctk.CTkFont(size=12),
        ).grid(row=r, column=0, padx=18, pady=(10, 4), sticky="sw")
        r += 1

        # 底部快捷按钮 — 轮廓风格，与侧边栏色调一致
        ctk.CTkButton(
            self.sidebar,
            text="⬡  打开整理目录",
            height=34,
            corner_radius=8,
            fg_color="transparent",
            border_width=1,
            border_color=COL_BORDER,
            text_color=COL_TEXT_NAV,
            hover_color=COL_HOVER,
            command=self.open_target_folder,
        ).grid(row=r, column=0, padx=14, pady=(4, 16), sticky="ew")

    def build_pages(self):
        builders = {
            "Home": self.build_home_page,
            "Review": self.build_review_page,
            "Settings": self.build_config_page,
            "Help": self.build_help_page,
            "Explanation": self.build_explanation_page,
            "Memory": self.build_memory_page,
            "Logs": self.build_logs_page,
            "Advanced": self.build_advanced_page,
        }

        for name in builders:
            frame = ctk.CTkFrame(self.content, fg_color=COL_BG, corner_radius=0)
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(1, weight=1)
            self.pages[name] = frame

        for name, builder in builders.items():
            builder(self.pages[name])

    def page_header(self, parent, title, subtitle):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, padx=24, pady=(22, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=title,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COL_TEXT,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text=subtitle,
            font=ctk.CTkFont(size=14),
            text_color=COL_TEXT_MUTED,
            wraplength=960,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        lang_label = "ENG" if get_language() == "zh" else "中文"
        ctk.CTkButton(
            header,
            text=lang_label,
            width=56,
            height=28,
            corner_radius=8,
            fg_color="transparent",
            border_width=1,
            border_color=COL_BORDER,
            text_color=COL_TEXT_MUTED,
            hover_color=COL_HOVER,
            command=self._toggle_language,
        ).grid(row=0, column=1, rowspan=2, padx=(8, 0), sticky="ne")

        return header

    def _toggle_language(self):
        new_lang = "en" if get_language() == "zh" else "zh"
        set_language(new_lang)
        config = self.read_config_safely()
        config["ui_language"] = new_lang
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self.rebuild_window_for_language(self.current_page or "Home")

    def make_card(self, parent, row, column, title=None, columnspan=1):
        card = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=14)
        card.grid(row=row, column=column, columnspan=columnspan, padx=10, pady=10, sticky="nsew")

        if title:
            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(size=17, weight="bold"),
                text_color=COL_TEXT,
            ).pack(anchor="w", padx=18, pady=(16, 8))

        return card

    def nav_to(self, page_name):
        # 侧边栏导航：离开有未保存修改的页面时先询问保存
        if not self._confirm_leave_current():
            return
        self.show_page(page_name)

    def _confirm_leave_current(self):
        """返回 True 表示可以离开（已处理保存/放弃），False 表示用户取消、留在本页。"""
        cur = self.current_page

        pending = None
        if cur == "Settings" and self.config_dirty:
            pending = ("设置", self.save_config_panel, "config_dirty")
        elif cur == "Review" and self.review_dirty:
            pending = ("整理方案", self.save_review_table, "review_dirty")
        elif cur == "Memory" and self.memory_dirty:
            pending = ("整理记忆", self.save_memory_panel, "memory_dirty")

        if pending is None:
            return True

        label, save_func, flag = pending
        answer = messagebox.askyesnocancel(
            "有未保存的修改",
            f"「{label}」有修改还没保存。\n\n是 = 保存并离开\n否 = 放弃修改并离开\n取消 = 留在本页",
        )

        if answer is None:
            return False  # 取消：留在本页

        if answer:
            ok = save_func(silent=True)
            if not ok:
                return False  # 保存失败（如校验不通过）→ 留在本页让用户修正

        setattr(self, flag, False)
        return True

    def show_page(self, page_name):
        for name, frame in self.pages.items():
            frame.lower()

        self.pages[page_name].lift()
        self.current_page = page_name

        for name, btn in self.nav_buttons.items():
            if name == page_name:
                btn.configure(fg_color=COL_ACCENT_SOFT, text_color=COL_ACCENT,
                              font=ctk.CTkFont(size=14, weight="bold"))
                if name in self.nav_indicators:
                    self.nav_indicators[name].configure(fg_color=COL_ACCENT)
            else:
                btn.configure(fg_color="transparent", text_color=COL_TEXT_NAV,
                              font=ctk.CTkFont(size=14))
                if name in self.nav_indicators:
                    self.nav_indicators[name].configure(fg_color="transparent")

        if page_name == "Home":
            self.update_home_summary()
            self.refresh_home_status()
        elif page_name == "Advanced":
            self.update_dashboard()
        elif page_name == "Memory":
            self.load_memory_panel()
        elif page_name == "Explanation":
            self.load_plan_explanation_panel()
        elif page_name == "Settings":
            self.load_config_panel()

    def get_language_display_options(self):
        return [get_language_label(language) for language in ("zh", "en")]

    def get_current_language_label(self):
        return get_language_label(get_language())

    def get_category_display_options(self, include_all=False):
        options = get_category_display_options(CATEGORIES)
        if include_all:
            return [t("全部")] + options
        return options

    def display_to_category(self, display_value):
        if display_value in ("", None):
            return display_value
        if display_value == t("全部"):
            return "全部"
        for category in CATEGORIES:
            if display_value == get_category_display(category):
                return category
        return display_value

    def category_to_display(self, category):
        if category in ("全部", t("全部")):
            return t("全部")
        return get_category_display(category)

    def rebuild_window_for_language(self, target_page="Settings"):
        self.root.title(f"{t(APP_TITLE)} {APP_VERSION}")
        self.root.minsize(1180 if is_english() else 1120, 720)

        for child in list(self.root.winfo_children()):
            child.destroy()

        self.pages = {}
        self.nav_buttons = {}
        self.nav_indicators = {}
        self.review_items = []
        self.review_check_vars = {}
        self.config_vars = {}
        self.dashboard_vars = {}
        self.review_filter_var = tk.StringVar(value=t("全部"))

        self.build_ui()
        self.show_page(target_page)
        self.update_home_summary()
        self.refresh_home_status()

    # =====================================================
    # Home Page (整理桌面 —— 引导流程 + 友好检查)
    # =====================================================

    def show_about(self):
        config = self.read_config_safely()

        message = (
            f"{APP_NAME} {APP_VERSION}\n\n"
            f"{t('当前模式：')}{config.get('llm_provider')}\n"
            f"{t('目标目录：')}{config.get('normal_target_root')}\n"
            f"{t('folder_mode：')}{config.get('folder_mode')}\n\n"
            f"{t('程序目录：', default='程序目录：')}\n{PROJECT_DIR}\n\n"
            f"{t('当前日志：', default='当前日志：')}\n{self.current_log_file}\n"
        )

        messagebox.showinfo("About / 关于", message)

    def on_close(self):
        # 关闭前：若当前页有未保存修改，先询问保存
        if not self._confirm_leave_current():
            return
        # 停掉本程序启动的内置 llama-server，避免它继续占用 runtime/models 文件，
        # 导致目录无法删除或重新打包。
        try:
            stop_builtin_server()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    root = ctk.CTk()
    DesktopAgentGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
