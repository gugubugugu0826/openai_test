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
    return Path(__file__).resolve().parent


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

from desktop_agent.healthcheck import print_healthcheck, run_healthcheck
from desktop_agent.scanner import scan_desktop
from desktop_agent.planner import preview_plan
from desktop_agent.reviewer import create_human_review, learn_from_review
from desktop_agent.executor import dryrun_plan, apply_plan, undo_last_action
from desktop_agent.memory import show_memory
from desktop_agent.state import show_state
from desktop_agent.workflow import run_workflow
from desktop_agent.plan_explainer import explain_current_plan

try:
    from desktop_agent.version import APP_NAME, APP_VERSION
except Exception:
    APP_NAME = "Qwen Desktop Organizer Agent"
    APP_VERSION = "v1.0"

# 用于内置模型（builtin）的路径解析 / 缺失检测
try:
    from desktop_agent.builtin_llm import get_builtin_config
except Exception:
    get_builtin_config = None

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
MODEL_DOWNLOAD_URL = ""
# 小于该大小视为“模型缺失 / 占位文件”
MODEL_MIN_VALID_BYTES = 20 * 1024 * 1024

# Hugging Face 在中国大陆常无法访问；hf-mirror.com 是可直接替换域名的国内镜像。
HF_HOST = "huggingface.co"
HF_MIRROR_HOST = "hf-mirror.com"


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


CATEGORIES = [
    "课程资料",
    "代码项目",
    "作业报告",
    "简历求职",
    "证件合同",
    "图片截图",
    "视频音频",
    "压缩包",
    "安装包",
    "游戏相关",
    "临时文件",
    "浏览器通讯",
    "办公学习",
    "系统工具",
    "影音娱乐",
    "网盘VPN",
    "其他快捷方式",
    "无法判断",
]


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


class DesktopAgentGUI:
    # 主导航（普通用户）
    PRIMARY_NAV = [
        ("Home", "整理桌面"),
        ("Review", "整理方案"),
        ("Settings", "设置"),
        ("Help", "帮助"),
    ]
    # 高级导航（折叠在分隔线下方）
    ADVANCED_NAV = [
        ("Explanation", "计划解释"),
        ("Memory", "整理记忆"),
        ("Logs", "运行日志"),
        ("Advanced", "高级操作"),
    ]

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
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1320x840")
        self.root.minsize(1120, 720)

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

        self.review_items = []
        self.review_filter_var = tk.StringVar(value="全部")
        self.config_vars = {}
        self.dashboard_vars = {}

        self.ensure_config_exists_for_startup()
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
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # =====================================================
    # Config Defaults
    # =====================================================

    def get_default_config(self, first_run_completed=True, provider="none"):
        return {
            "first_run_completed": first_run_completed,
            "llm_provider": provider,

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
                return json.load(f)
        except Exception:
            return self.get_default_config()

    # =====================================================
    # Builtin Model Helpers
    # =====================================================

    def get_model_file_path(self):
        config = self.read_config_safely()
        if get_builtin_config is not None:
            try:
                return Path(get_builtin_config()["model_file"])
            except Exception:
                pass
        model_path = Path(config.get("builtin_model_path", "models\\qwen-small.gguf"))
        if not model_path.is_absolute():
            model_path = PROJECT_DIR / model_path
        return model_path

    def is_model_present(self):
        try:
            p = self.get_model_file_path()
            return p.exists() and p.stat().st_size >= MODEL_MIN_VALID_BYTES
        except Exception:
            return False

    def get_model_url(self):
        config = self.read_config_safely()
        return (config.get("builtin_model_url", "") or MODEL_DOWNLOAD_URL or "").strip()

    def get_model_urls(self):
        """返回有序的下载候选地址：优先用户配置的，再自动补一个 huggingface ↔ hf-mirror 互备。"""
        primary = self.get_model_url()
        urls = []

        def add(u):
            u = (u or "").strip()
            if u and u not in urls:
                urls.append(u)

        add(primary)
        if primary:
            if HF_HOST in primary:
                add(primary.replace(HF_HOST, HF_MIRROR_HOST))  # 官方 → 国内镜像
            elif HF_MIRROR_HOST in primary:
                add(primary.replace(HF_MIRROR_HOST, HF_HOST))  # 镜像 → 官方
        return urls

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

    def open_logs_folder(self):
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(f'explorer "{LOG_DIR}"')
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def open_current_log_file(self):
        if not self.current_log_file or not self.current_log_file.exists():
            messagebox.showwarning("没有日志文件", "当前日志文件不存在。")
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

        self.sidebar = ctk.CTkFrame(self.root, width=232, corner_radius=0, fg_color=COL_SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        self.content = ctk.CTkFrame(self.root, corner_radius=0, fg_color=COL_BG)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.build_sidebar()
        self.build_pages()

    def _add_nav_button(self, page_name, text, row):
        btn = ctk.CTkButton(
            self.sidebar,
            text="    " + text,
            height=38,
            corner_radius=8,
            anchor="w",
            fg_color="transparent",
            text_color=COL_TEXT_NAV,
            hover_color=COL_HOVER,
            font=ctk.CTkFont(size=14),
            command=lambda p=page_name: self.nav_to(p),
        )
        btn.grid(row=row, column=0, padx=12, pady=2, sticky="ew")
        self.nav_buttons[page_name] = btn

    def build_sidebar(self):
        self.sidebar.grid_columnconfigure(0, weight=1)
        r = 0

        ctk.CTkLabel(
            self.sidebar,
            text=APP_TITLE,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COL_TEXT,
            anchor="w",
        ).grid(row=r, column=0, padx=18, pady=(22, 2), sticky="w")
        r += 1

        ctk.CTkLabel(
            self.sidebar,
            text=f"Desktop Agent {APP_VERSION}",
            text_color=COL_TEXT_MUTED,
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).grid(row=r, column=0, padx=18, pady=(0, 14), sticky="w")
        r += 1

        for page_name, text in self.PRIMARY_NAV:
            self._add_nav_button(page_name, text, r)
            r += 1

        ctk.CTkLabel(
            self.sidebar,
            text="高级",
            text_color="#9ca3af",
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).grid(row=r, column=0, padx=20, pady=(16, 2), sticky="w")
        r += 1

        for page_name, text in self.ADVANCED_NAV:
            self._add_nav_button(page_name, text, r)
            r += 1

        self.sidebar.grid_rowconfigure(r, weight=1)
        r += 1

        self.status_var = tk.StringVar(value="就绪")
        ctk.CTkLabel(
            self.sidebar,
            textvariable=self.status_var,
            text_color=COL_TEXT_MUTED,
            wraplength=190,
            anchor="w",
            font=ctk.CTkFont(size=12),
        ).grid(row=r, column=0, padx=18, pady=(10, 4), sticky="sw")
        r += 1

        ctk.CTkButton(
            self.sidebar,
            text="打开整理目录",
            height=36,
            corner_radius=8,
            fg_color=COL_OK,
            hover_color="#059669",
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
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        return header

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
                btn.configure(fg_color=COL_ACCENT_SOFT, text_color=COL_ACCENT)
            else:
                btn.configure(fg_color="transparent", text_color=COL_TEXT_NAV)

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

    # =====================================================
    # Home Page (整理桌面 —— 引导流程 + 友好检查)
    # =====================================================

    def build_home_page(self, parent):
        self.page_header(
            parent,
            "整理桌面",
            "先检查准备情况，确认无误后按 1 → 3 完成整理。",
        )

        body = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        # 状态卡（由 refresh_home_status 动态重建）
        self.home_status_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        self.home_status_card.grid(row=0, column=0, padx=6, pady=(6, 10), sticky="ew")
        self.home_status_card.grid_columnconfigure(0, weight=1)
        self._render_home_status_message("检查中…", "正在检查运行环境，请稍候。", COL_TEXT_MUTED, COL_CARD)

        # 当前设置摘要
        summary = ctk.CTkFrame(body, fg_color="transparent")
        summary.grid(row=1, column=0, padx=0, pady=(0, 4), sticky="ew")
        summary.grid_columnconfigure((0, 1), weight=1)

        self.home_scan_var = tk.StringVar(value="-")
        self.home_target_var = tk.StringVar(value="-")
        self._mini_card(summary, 0, "扫描位置", self.home_scan_var)
        self._mini_card(summary, 1, "整理到", self.home_target_var)

        # 引导三步
        steps = [
            ("1", "扫描并生成整理方案",
             "让 AI 扫描桌面、自动分类，生成一份方案（此步不会移动文件）。",
             "扫描", self.start_scan, COL_ACCENT),
            ("2", "查看并调整方案",
             "检查分类结果，可以手动改分类或跳过个别文件。",
             "查看", self.load_review_table, COL_ACCENT),
            ("3", "确认并开始整理",
             "核对摘要后正式整理。默认复制文件，原文件保留。",
             "整理", self.confirm_apply, COL_DANGER),
        ]
        for i, (num, title, desc, btn_text, cmd, color) in enumerate(steps, start=2):
            self._step_card(body, i, num, title, desc, btn_text, cmd, color)

        footer = ctk.CTkFrame(body, fg_color="transparent")
        footer.grid(row=5, column=0, pady=(8, 4), sticky="w")

        ctk.CTkButton(
            footer, text="重新检查", width=110, height=36, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=COL_BORDER,
            text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
            command=self.refresh_home_status,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            footer, text="打开整理目录", width=130, height=36, corner_radius=8,
            fg_color=COL_OK, hover_color="#059669",
            command=self.open_target_folder,
        ).pack(side="left", padx=6)

    def _mini_card(self, parent, col, label, var):
        card = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=12)
        card.grid(row=0, column=col, padx=6, pady=6, sticky="ew")
        ctk.CTkLabel(
            card, text=label, font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COL_TEXT_MUTED,
        ).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            card, textvariable=var, font=ctk.CTkFont(size=13),
            text_color=COL_TEXT, wraplength=380, justify="left", anchor="w",
        ).pack(anchor="w", padx=14, pady=(0, 12))

    def _step_card(self, parent, row, num, title, desc, btn_text, cmd, color):
        card = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=14)
        card.grid(row=row, column=0, padx=6, pady=6, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text=num, width=34, height=34, corner_radius=17,
            fg_color=color, text_color="white",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=16)

        tf = ctk.CTkFrame(card, fg_color="transparent")
        tf.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(
            tf, text=title, font=ctk.CTkFont(size=15, weight="bold"),
            text_color=COL_TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            tf, text=desc, font=ctk.CTkFont(size=12),
            text_color=COL_TEXT_MUTED, justify="left",
        ).pack(anchor="w", pady=(3, 0))

        ctk.CTkButton(
            card, text=btn_text, width=88, height=36, corner_radius=8,
            fg_color=color, hover_color=color, command=cmd,
        ).grid(row=0, column=2, padx=16, pady=16)

    def update_home_summary(self):
        if not hasattr(self, "home_scan_var"):
            return
        config = self.read_config_safely()
        dp = config.get("desktop_path", "").strip()
        scan = dp if dp else str(Path.home() / "Desktop")
        self.home_scan_var.set(scan)
        self.home_target_var.set(config.get("normal_target_root", "") or "-")

    def start_scan(self):
        self.run_command(
            "run",
            guided=True,
            busy_text="正在扫描桌面并生成整理方案…\n（此步只生成方案，不会移动文件）",
            on_done=self._after_scan_done,
        )

    def _after_scan_done(self):
        count = 0
        if REVIEW_FILE.exists():
            try:
                with open(REVIEW_FILE, "r", encoding="utf-8") as f:
                    count = len(json.load(f).get("items", []))
            except Exception:
                count = 0

        if not REVIEW_FILE.exists():
            messagebox.showwarning("没有生成方案", "扫描似乎没有生成方案，请查看「运行日志」了解原因。")
            self.show_page("Logs")
            return

        self.load_review_table()
        messagebox.showinfo(
            "扫描完成",
            f"已生成整理方案，共 {count} 项。\n\n"
            "请在「整理方案」里检查分类，需要的话改分类或跳过；\n"
            "确认后回到「整理桌面」点 ③ 确认并整理。",
        )

    def _after_apply_done(self):
        self.show_page("Home")
        self.refresh_home_status()
        if messagebox.askyesno("整理完成", "文件已整理完成！\n\n现在打开整理目录查看结果吗？"):
            self.open_target_folder()

    def refresh_home_status(self):
        if not hasattr(self, "home_status_card") or self._checking:
            return
        self._checking = True
        self.status_var.set("检查中…")
        self._render_home_status_message("检查中…", "正在检查运行环境，请稍候。", COL_TEXT_MUTED, "#f9fafb")
        self.update_home_summary()
        threading.Thread(target=self._do_home_check, daemon=True).start()

    def _do_home_check(self):
        try:
            results = run_healthcheck()
        except Exception as e:
            results = [{"name": "Error", "ok": False, "message": str(e)}]
        self.root.after(0, lambda: self._render_home_status(results))

    def _clear(self, frame):
        for w in frame.winfo_children():
            w.destroy()

    def _render_home_status_message(self, title, subtitle, color, bg):
        self.home_status_card.configure(fg_color=bg)
        self._clear(self.home_status_card)
        ctk.CTkLabel(
            self.home_status_card, text=title,
            font=ctk.CTkFont(size=16, weight="bold"), text_color=color,
        ).grid(row=0, column=0, padx=18, pady=(16, 2), sticky="w")
        ctk.CTkLabel(
            self.home_status_card, text=subtitle,
            font=ctk.CTkFont(size=13), text_color=color,
        ).grid(row=1, column=0, padx=18, pady=(0, 16), sticky="w")

    def _render_home_status(self, results):
        self._checking = False
        all_ok = all(r.get("ok") for r in results)
        fails = [r for r in results if not r.get("ok")]

        self._clear(self.home_status_card)

        if all_ok:
            title = "✓  一切就绪，可以开始整理"
            subtitle = "按下方 1 → 3 的步骤即可完成整理。"
            color = COL_OK
            bg = COL_OK_SOFT
        else:
            title = f"需要先解决 {len(fails)} 个问题"
            subtitle = "下面标记 ✗ 的项需要处理，处理后点「重新检查」。"
            color = COL_WARN_TEXT
            bg = COL_WARN_SOFT

        self.home_status_card.configure(fg_color=bg)

        ctk.CTkLabel(
            self.home_status_card, text=title,
            font=ctk.CTkFont(size=16, weight="bold"), text_color=color,
        ).grid(row=0, column=0, padx=18, pady=(16, 2), sticky="w")
        ctk.CTkLabel(
            self.home_status_card, text=subtitle,
            font=ctk.CTkFont(size=13), text_color=color,
            wraplength=620, justify="left",
        ).grid(row=1, column=0, padx=18, pady=(0, 10), sticky="w")

        rrow = 2
        for r in results:
            if r.get("name") in self.HIDDEN_CHECKS:
                continue
            ok = r.get("ok")
            mark = "✓" if ok else "✗"
            mark_color = COL_OK if ok else COL_DANGER
            name = self.FRIENDLY_CHECKS.get(r.get("name"), r.get("name"))

            line = ctk.CTkFrame(self.home_status_card, fg_color="transparent")
            line.grid(row=rrow, column=0, padx=18, pady=2, sticky="w")

            ctk.CTkLabel(
                line, text=mark, text_color=mark_color, width=18,
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(side="left")

            text = name if ok else f"{name}：{r.get('message', '')}"
            ctk.CTkLabel(
                line, text=text,
                text_color=COL_TEXT if ok else "#7c2d12",
                font=ctk.CTkFont(size=13), justify="left", wraplength=560,
            ).pack(side="left", padx=(6, 0))
            rrow += 1

        config = self.read_config_safely()
        if config.get("llm_provider") == "builtin" and not self.is_model_present():
            ctk.CTkButton(
                self.home_status_card, text="获取 AI 模型", height=32, corner_radius=8,
                fg_color=COL_ACCENT, hover_color=COL_ACCENT,
                command=lambda: self.open_model_setup(on_done=self.refresh_home_status),
            ).grid(row=rrow, column=0, padx=18, pady=(8, 0), sticky="w")
            rrow += 1

        ctk.CTkButton(
            self.home_status_card, text="查看完整检查日志", height=30, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=COL_BORDER,
            text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
            command=lambda: self.run_command("check"),
        ).grid(row=rrow, column=0, padx=18, pady=(8, 16), sticky="w")

        self.status_var.set("就绪" if all_ok else f"{len(fails)} 项待处理")

    # =====================================================
    # Advanced Page (高级操作 —— 单步命令 / 文件状态 / 诊断)
    # =====================================================

    def build_advanced_page(self, parent):
        self.page_header(
            parent,
            "高级操作",
            "单步运行各阶段命令、查看中间文件、生成诊断报告。普通使用无需打开本页。",
        )

        body = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        # 文件状态卡
        status_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        status_card.grid(row=0, column=0, padx=6, pady=(6, 10), sticky="ew")
        status_card.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            status_card, text="当前状态", font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COL_TEXT,
        ).grid(row=0, column=0, columnspan=3, padx=16, pady=(14, 6), sticky="w")

        items = [
            ("provider", "当前模式"),
            ("scan_path", "扫描路径"),
            ("target_root", "目标目录"),
            ("folder_mode", "文件夹模式"),
            ("observation", "Observation"),
            ("plan", "Plan"),
            ("review", "Review"),
            ("action_log", "Action Log"),
            ("current_log", "当前日志"),
        ]
        for idx, (key, label) in enumerate(items):
            row = (idx // 3) + 1
            col = idx % 3
            cell = ctk.CTkFrame(status_card, fg_color="transparent")
            cell.grid(row=row, column=col, padx=14, pady=8, sticky="w")
            ctk.CTkLabel(
                cell, text=label, font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COL_TEXT_MUTED,
            ).pack(anchor="w")
            var = tk.StringVar(value="-")
            self.dashboard_vars[key] = var
            ctk.CTkLabel(
                cell, textvariable=var, wraplength=240, justify="left",
                text_color=COL_TEXT, font=ctk.CTkFont(size=12),
            ).pack(anchor="w")

        ctk.CTkButton(
            status_card, text="刷新", width=90, height=32, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=COL_BORDER,
            text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
            command=self.update_dashboard,
        ).grid(row=4, column=0, padx=16, pady=(4, 14), sticky="w")

        # 单步命令卡
        cmd_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        cmd_card.grid(row=1, column=0, padx=6, pady=10, sticky="ew")
        ctk.CTkLabel(
            cmd_card, text="单步命令", font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COL_TEXT,
        ).pack(anchor="w", padx=16, pady=(14, 6))

        grid = ctk.CTkFrame(cmd_card, fg_color="transparent")
        grid.pack(fill="x", padx=10, pady=(0, 14))

        commands = [
            ("环境自检 check", lambda: self.run_command("check"), COL_ACCENT),
            ("扫描 scan", lambda: self.run_command("scan"), COL_ACCENT),
            ("预览 preview", lambda: self.run_command("preview"), COL_ACCENT),
            ("生成审核 review", lambda: self.run_command("review"), COL_ACCENT),
            ("Run 全流程", lambda: self.run_command("run"), COL_ACCENT),
            ("学习 learn", lambda: self.run_command("learn"), "#7c3aed"),
            ("预演 dryrun", lambda: self.run_command("dryrun"), COL_WARN),
            ("Continue 预演", lambda: self.run_command("continue"), COL_WARN),
            ("应用 apply", self.confirm_apply, COL_DANGER),
            ("撤销 undo", self.confirm_undo, COL_DANGER),
            ("预估扫描范围", self.show_scan_scope_estimate, "#0d9488"),
        ]
        for i, (text, cmd, color) in enumerate(commands):
            ctk.CTkButton(
                grid, text=text, width=150, height=36, corner_radius=8,
                fg_color=color, hover_color=color, command=cmd,
            ).grid(row=i // 4, column=i % 4, padx=6, pady=6, sticky="w")

        # 诊断 / 文件卡
        diag_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        diag_card.grid(row=2, column=0, padx=6, pady=10, sticky="ew")
        ctk.CTkLabel(
            diag_card, text="诊断 / 文件", font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COL_TEXT,
        ).pack(anchor="w", padx=16, pady=(14, 6))

        diag_row = ctk.CTkFrame(diag_card, fg_color="transparent")
        diag_row.pack(fill="x", padx=10, pady=(0, 14))
        for text, cmd in [
            ("生成错误报告包", self.create_diagnostic_report),
            ("打开程序目录", self.open_project_folder),
            ("打开 logs 文件夹", self.open_logs_folder),
            ("打开目标目录", self.open_target_folder),
            ("关于", self.show_about),
        ]:
            ctk.CTkButton(
                diag_row, text=text, height=36, corner_radius=8,
                fg_color="transparent", border_width=1, border_color=COL_BORDER,
                text_color=COL_TEXT_NAV, hover_color=COL_HOVER, command=cmd,
            ).pack(side="left", padx=6, pady=4)

        self.update_dashboard()

    def file_status_text(self, path: Path):
        if path.exists():
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                return f"存在\n{mtime}"
            except Exception:
                return "存在"
        return "不存在"

    def update_dashboard(self):
        if not self.dashboard_vars:
            return
        try:
            config = self.read_config_safely()
            desktop_path = config.get("desktop_path", "").strip()

            if not desktop_path:
                scan_path = str(Path.home() / "Desktop")
            else:
                scan_path = desktop_path

            values = {
                "provider": config.get("llm_provider", "unknown"),
                "scan_path": scan_path,
                "target_root": config.get("normal_target_root", ""),
                "folder_mode": config.get("folder_mode", ""),
                "observation": self.file_status_text(OBSERVATION_FILE),
                "plan": self.file_status_text(PLAN_FILE),
                "review": self.file_status_text(REVIEW_FILE),
                "action_log": self.file_status_text(ACTION_LOG_FILE),
                "current_log": str(self.current_log_file.name if self.current_log_file else "-"),
            }

            for key, value in values.items():
                if key in self.dashboard_vars:
                    self.dashboard_vars[key].set(value)
        except Exception as e:
            self.append_output(f"\n[GUI] 状态刷新失败：{e}\n")

    # =====================================================
    # Logs Page
    # =====================================================

    def build_logs_page(self, parent):
        self.page_header(
            parent,
            "运行日志",
            "查看运行输出、打开日志文件、生成错误报告。",
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        actions = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        actions.grid(row=0, column=0, padx=6, pady=6, sticky="ew")

        ctk.CTkButton(actions, text="打开 logs 文件夹", corner_radius=8, command=self.open_logs_folder).pack(side="left", padx=10, pady=12)
        ctk.CTkButton(actions, text="打开当前日志", corner_radius=8, command=self.open_current_log_file).pack(side="left", padx=10, pady=12)
        ctk.CTkButton(actions, text="生成错误报告包", corner_radius=8, command=self.create_diagnostic_report).pack(side="left", padx=10, pady=12)
        ctk.CTkButton(actions, text="清空输出窗口", corner_radius=8, fg_color="#6b7280", hover_color="#4b5563", command=self.clear_output).pack(side="left", padx=10, pady=12)

        self.output_text = ctk.CTkTextbox(
            body,
            font=("Consolas", 12),
            corner_radius=14,
            fg_color="#111827",
            text_color="#e5e7eb",
        )
        self.output_text.grid(row=1, column=0, padx=6, pady=8, sticky="nsew")

    # =====================================================
    # Review Page
    # =====================================================

    def build_review_page(self, parent):
        self.page_header(
            parent,
            "整理方案",
            "查看并调整 AI 的整理计划：用开关启用/跳过，用下拉直接改分类。",
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_rowconfigure(3, weight=1)
        body.grid_columnconfigure(0, weight=1)

        # 操作提示，降低“又是打勾又是保存”的困惑
        hint = ctk.CTkFrame(body, fg_color=COL_ACCENT_SOFT, corner_radius=12)
        hint.grid(row=0, column=0, padx=6, pady=(6, 2), sticky="ew")
        ctk.CTkLabel(
            hint,
            text=("怎么用：①「启用」开关决定这一项要不要整理（关 = 跳过）；"
                  "②「我的分类」下拉直接改归类；③ 改完点上方绿色「保存」。\n"
                  "左侧「选中」勾选框只在“批量改分类”时才需要：勾几项 → 点「勾选项改分类」。"),
            font=ctk.CTkFont(size=12), text_color=COL_ACCENT,
            justify="left", anchor="w",
        ).pack(anchor="w", padx=14, pady=10)

        toolbar = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        toolbar.grid(row=1, column=0, padx=6, pady=6, sticky="ew")

        ctk.CTkButton(toolbar, text="加载", corner_radius=8, command=self.load_review_table).pack(side="left", padx=6, pady=12)
        ctk.CTkButton(toolbar, text="保存", corner_radius=8, fg_color=COL_OK, hover_color="#059669", command=self.save_review_table).pack(side="left", padx=6, pady=12)
        ctk.CTkButton(toolbar, text="全部启用", corner_radius=8, command=self.enable_all_review_items).pack(side="left", padx=6, pady=12)
        ctk.CTkButton(toolbar, text="全部禁用", corner_radius=8, fg_color="#6b7280", hover_color="#4b5563", command=self.disable_all_review_items).pack(side="left", padx=6, pady=12)
        ctk.CTkButton(toolbar, text="勾选全部 / 取消", corner_radius=8, fg_color="transparent", border_width=1, border_color=COL_BORDER, text_color=COL_TEXT_NAV, hover_color=COL_HOVER, command=self.check_all_review_items).pack(side="left", padx=6, pady=12)
        ctk.CTkButton(toolbar, text="勾选项改分类", corner_radius=8, command=self.change_selected_category).pack(side="left", padx=6, pady=12)

        ctk.CTkLabel(toolbar, text="筛选：").pack(side="left", padx=(16, 4))
        self.review_filter_menu = ctk.CTkOptionMenu(
            toolbar,
            values=["全部"] + CATEGORIES,
            variable=self.review_filter_var,
            command=lambda _: self.refresh_review_table(),
            width=150,
        )
        self.review_filter_menu.pack(side="left", padx=6)

        self.review_count_var = tk.StringVar(value="未加载")
        ctk.CTkLabel(toolbar, textvariable=self.review_count_var, text_color=COL_TEXT_MUTED).pack(side="right", padx=12)

        # 固定列头（不随列表滚动）
        header = ctk.CTkFrame(body, fg_color="#eef2f7", corner_radius=10)
        header.grid(row=2, column=0, padx=6, pady=(2, 0), sticky="ew")
        self._review_columns(header)
        titles = ["选中", "启用", "名称", "类型", "AI 判断", "我的分类", "原因"]
        for col, text in enumerate(titles):
            ctk.CTkLabel(
                header, text=text, font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COL_TEXT_NAV, anchor="w",
            ).grid(row=0, column=col, sticky="w", padx=(16 if col == 0 else 8), pady=9)

        # 卡片式行列表（可滚动）
        self.review_list = ctk.CTkScrollableFrame(body, fg_color="transparent")
        self.review_list.grid(row=3, column=0, padx=6, pady=(4, 8), sticky="nsew")
        self.review_list.grid_columnconfigure(0, weight=1)

        self.review_check_vars = {}

    def _review_columns(self, frame):
        # (列号, 拉伸权重, 最小宽度) —— 列头与每一行用相同配置以对齐
        cfg = [(0, 0, 44), (1, 0, 70), (2, 3, 200), (3, 0, 92), (4, 1, 112), (5, 0, 172), (6, 3, 220)]
        for col, weight, minsize in cfg:
            frame.grid_columnconfigure(col, weight=weight, minsize=minsize)

    def _type_pill_style(self, item_type):
        mapping = {
            "folder": ("文件夹", "#e0edff", "#1d4ed8"),
            "file": ("文件", "#eef2f7", "#475569"),
            "shortcut": ("快捷方式", "#f3e8ff", "#7c3aed"),
        }
        return mapping.get(item_type, ("其他", "#eef2f7", "#475569"))

    def _make_review_row(self, index, item, zebra):
        enabled = item.get("enabled", True)
        base_bg = "#f8fafc" if zebra else COL_CARD

        row = ctk.CTkFrame(self.review_list, fg_color=base_bg, corner_radius=8)
        row.pack(fill="x", padx=2, pady=2)
        self._review_columns(row)

        name_color = COL_TEXT if enabled else "#9ca3af"
        muted_color = COL_TEXT_MUTED if enabled else "#cbd5e1"

        # 名称
        name_lbl = ctk.CTkLabel(
            row, text=item.get("name", ""), font=ctk.CTkFont(size=13, weight="bold"),
            text_color=name_color, anchor="w", justify="left", wraplength=320,
        )
        name_lbl.grid(row=0, column=2, padx=8, pady=10, sticky="w")

        # 类型药丸
        ptext, pfg, pcolor = self._type_pill_style(item.get("type", ""))
        pill = ctk.CTkLabel(
            row, text=ptext, corner_radius=8, font=ctk.CTkFont(size=11),
            width=66, height=22,
            fg_color=pfg if enabled else "#f1f5f9",
            text_color=pcolor if enabled else "#cbd5e1",
        )
        pill.grid(row=0, column=3, padx=8, pady=10, sticky="w")

        # AI 判断
        ai_lbl = ctk.CTkLabel(
            row, text=item.get("ai_category", item.get("category", "")),
            text_color=muted_color, anchor="w", font=ctk.CTkFont(size=12),
        )
        ai_lbl.grid(row=0, column=4, padx=8, pady=10, sticky="w")

        # 我的分类（下拉，直接改）
        hvar = tk.StringVar(value=item.get("human_category", item.get("category", "")) or CATEGORIES[0])

        def on_cat(choice, i=index):
            self.review_items[i]["human_category"] = choice
            self.review_dirty = True

        ctk.CTkOptionMenu(
            row, values=CATEGORIES, variable=hvar, command=on_cat, width=160,
        ).grid(row=0, column=5, padx=8, pady=8, sticky="w")

        # 原因
        reason_lbl = ctk.CTkLabel(
            row, text=item.get("reason", ""), text_color=muted_color,
            anchor="w", justify="left", wraplength=360, font=ctk.CTkFont(size=12),
        )
        reason_lbl.grid(row=0, column=6, padx=8, pady=10, sticky="w")

        # 启用开关（就地置灰，不重建，保留勾选状态）
        evar = tk.BooleanVar(value=enabled)

        def recolor():
            en = bool(evar.get())
            nc = COL_TEXT if en else "#9ca3af"
            mc = COL_TEXT_MUTED if en else "#cbd5e1"
            name_lbl.configure(text_color=nc)
            ai_lbl.configure(text_color=mc)
            reason_lbl.configure(text_color=mc)
            if en:
                pill.configure(fg_color=pfg, text_color=pcolor)
            else:
                pill.configure(fg_color="#f1f5f9", text_color="#cbd5e1")

        def on_toggle(i=index):
            self.review_items[i]["enabled"] = bool(evar.get())
            self.review_dirty = True
            recolor()
            self._update_review_count()

        ctk.CTkSwitch(row, text="", width=44, variable=evar, command=on_toggle).grid(
            row=0, column=1, padx=6, pady=10, sticky="w"
        )

        # 选中（批量操作用）
        cvar = tk.BooleanVar(value=False)
        self.review_check_vars[index] = cvar
        ctk.CTkCheckBox(
            row, text="", width=22, variable=cvar,
            command=self._update_review_count,
        ).grid(row=0, column=0, padx=(18, 4), pady=10, sticky="w")

    # =====================================================
    # Memory Page
    # =====================================================

    def build_memory_page(self, parent):
        self.page_header(
            parent,
            "整理记忆",
            "管理整理规则：文件名 / 路径命中关键词时，自动归到指定分类。无需手写 JSON。",
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        toolbar.grid(row=0, column=0, padx=6, pady=6, sticky="ew")

        ctk.CTkButton(toolbar, text="添加规则", corner_radius=8, command=self.add_memory_rule_dialog).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(toolbar, text="编辑选中", corner_radius=8, command=self.edit_selected_memory_rule).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(toolbar, text="删除选中", corner_radius=8, fg_color=COL_DANGER, hover_color="#b91c1c", command=self.delete_selected_memory_rules).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(toolbar, text="保存", corner_radius=8, fg_color=COL_OK, hover_color="#059669", command=self.save_memory_panel).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(toolbar, text="重新加载", corner_radius=8, fg_color="#6b7280", hover_color="#4b5563", command=self.load_memory_panel).pack(side="left", padx=8, pady=12)

        self.memory_count_var = tk.StringVar(value="未加载")
        ctk.CTkLabel(toolbar, textvariable=self.memory_count_var, text_color=COL_TEXT_MUTED).pack(side="right", padx=12)

        table_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        table_card.grid(row=1, column=0, padx=6, pady=8, sticky="nsew")
        table_card.grid_rowconfigure(0, weight=1)
        table_card.grid_columnconfigure(0, weight=1)

        self._setup_ttk_style()

        columns = ("match", "category", "note")
        self.memory_tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="extended")

        headings = {"match": "命中关键词", "category": "归类到", "note": "备注"}
        widths = {"match": 240, "category": 140, "note": 560}
        for col in columns:
            self.memory_tree.heading(col, text=headings[col])
            self.memory_tree.column(col, width=widths[col], anchor="w")

        self.memory_tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        y_scroll = ttk.Scrollbar(table_card, orient="vertical", command=self.memory_tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns", pady=10)
        self.memory_tree.configure(yscrollcommand=y_scroll.set)
        self.memory_tree.bind("<Double-1>", lambda e: self.edit_selected_memory_rule())

        self.load_memory_panel()

    # =====================================================
    # Explanation Page
    # =====================================================

    def build_explanation_page(self, parent):
        self.page_header(
            parent,
            "计划解释",
            "让 AI 自动解释本次整理计划，包括分类统计、风险项和建议。",
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        toolbar.grid(row=0, column=0, padx=6, pady=6, sticky="ew")

        ctk.CTkButton(toolbar, text="生成 / 刷新解释", corner_radius=8, command=self.generate_plan_explanation_gui).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(toolbar, text="打开解释文件", corner_radius=8, command=self.open_plan_explanation_file).pack(side="left", padx=8, pady=12)

        self.explanation_text = ctk.CTkTextbox(
            body,
            font=("Microsoft YaHei UI", 12),
            corner_radius=14,
            fg_color=COL_CARD,
            text_color=COL_TEXT,
        )
        self.explanation_text.grid(row=1, column=0, padx=6, pady=8, sticky="nsew")

    # =====================================================
    # Settings Page (原 Config)
    # =====================================================

    def build_config_page(self, parent):
        self.page_header(
            parent,
            "设置",
            "基本设置在最上面。模型后端等技术项在“高级”分组，普通使用一般不用改。",
        )

        # 操作栏固定在顶部（不随内容滚动），保存随手可点
        parent.grid_rowconfigure(1, weight=0)
        parent.grid_rowconfigure(2, weight=1)

        actions = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=14)
        actions.grid(row=1, column=0, padx=24, pady=(0, 8), sticky="ew")

        ctk.CTkButton(actions, text="保存配置", corner_radius=8, fg_color=COL_OK, hover_color="#059669", command=self.save_config_panel).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(actions, text="加载配置", corner_radius=8, command=self.load_config_panel).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(actions, text="重置默认", corner_radius=8, fg_color="#6b7280", hover_color="#4b5563", command=self.reset_config_to_default).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(actions, text="导出配置", corner_radius=8, command=self.export_config).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(actions, text="导入配置", corner_radius=8, command=self.import_config).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(actions, text="获取 AI 模型", corner_radius=8, fg_color="#0d9488", hover_color="#0f766e", command=lambda: self.open_model_setup(on_done=self.refresh_home_status)).pack(side="left", padx=8, pady=12)

        body = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        body.grid(row=2, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        self.config_vars = {}

        self.build_config_section(
            body,
            row=0,
            title="基本设置",
            fields=[
                ("desktop_path", "扫描路径", "留空表示当前用户桌面"),
                ("normal_target_root", "整理目标目录", "例如 D:\\Desktop_Sorted"),
                ("folder_mode", "文件夹处理模式", "copy 或 move，推荐 copy"),
            ],
        )

        self.build_config_section(
            body,
            row=1,
            title="AI 模式（高级）",
            fields=[
                ("llm_provider", "LLM Provider", "none / ollama / openai_compatible / builtin"),
                ("model", "Ollama 模型", "例如 qwen2.5-coder:14b"),
                ("ollama_url", "Ollama API", "http://localhost:11434/api/generate"),
                ("api_base_url", "云端 API 地址", "OpenAI-compatible chat completions endpoint"),
                ("api_model", "云端模型", "例如 gpt-4.1-mini"),
                ("api_key", "云端 API Key", "推荐使用环境变量 DESKTOP_AGENT_API_KEY"),
            ],
        )

        self.build_config_section(
            body,
            row=2,
            title="自带 AI 引擎 builtin（高级）",
            fields=[
                ("builtin_server_host", "Builtin Host", "默认 127.0.0.1"),
                ("builtin_server_port", "Builtin Port", "默认 18080"),
                ("builtin_server_path", "llama-server 路径", "runtime\\llama-server.exe"),
                ("builtin_model_path", "GGUF 模型路径", "models\\qwen-small.gguf"),
                ("builtin_api_model", "Builtin API Model", "默认 builtin-model"),
                ("builtin_context_size", "上下文长度", "默认 4096"),
                ("builtin_threads", "CPU 线程数", "例如 8"),
                ("builtin_model_url", "模型下载地址", "可选：模型 .gguf 直链，用于首次运行自动下载"),
            ],
        )

        self.build_config_section(
            body,
            row=3,
            title="性能 / 其他（高级）",
            fields=[
                ("batch_size", "每批数量", "例如 8"),
                ("max_internal_items_per_folder", "文件夹内部采样数量", "例如 200"),
                ("first_run_completed", "首次引导已完成", "true 或 false"),
            ],
        )

        self.load_config_panel()

    def build_config_section(self, parent, row, title, fields):
        card = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=14)
        card.grid(row=row, column=0, padx=6, pady=10, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COL_TEXT,
        ).grid(row=0, column=0, columnspan=3, padx=18, pady=(16, 8), sticky="w")

        for i, (key, label, hint) in enumerate(fields, start=1):
            ctk.CTkLabel(
                card,
                text=label,
                width=160,
                anchor="w",
                text_color=COL_TEXT_NAV,
            ).grid(row=i, column=0, padx=18, pady=8, sticky="w")

            var = tk.StringVar()
            self.config_vars[key] = var
            var.trace_add("write", lambda *a: self._on_config_var_write())

            input_frame = ctk.CTkFrame(card, fg_color="transparent")
            input_frame.grid(row=i, column=1, padx=8, pady=8, sticky="ew")
            input_frame.grid_columnconfigure(0, weight=1)

            if key == "llm_provider":
                widget = ctk.CTkOptionMenu(
                    input_frame,
                    variable=var,
                    values=["none", "ollama", "openai_compatible", "builtin"],
                )
                widget.grid(row=0, column=0, sticky="ew")
            elif key == "folder_mode":
                widget = ctk.CTkOptionMenu(
                    input_frame,
                    variable=var,
                    values=["copy", "move"],
                )
                widget.grid(row=0, column=0, sticky="ew")
            elif key == "first_run_completed":
                widget = ctk.CTkOptionMenu(
                    input_frame,
                    variable=var,
                    values=["true", "false"],
                )
                widget.grid(row=0, column=0, sticky="ew")
            else:
                widget = ctk.CTkEntry(input_frame, textvariable=var)
                widget.grid(row=0, column=0, sticky="ew")

                if key == "desktop_path":
                    ctk.CTkButton(
                        input_frame,
                        text="浏览",
                        width=70,
                        command=self.browse_desktop_path,
                    ).grid(row=0, column=1, padx=(8, 0))

                if key == "normal_target_root":
                    ctk.CTkButton(
                        input_frame,
                        text="浏览",
                        width=70,
                        command=self.browse_target_root,
                    ).grid(row=0, column=1, padx=(8, 0))

            ctk.CTkLabel(
                card,
                text=hint,
                text_color=COL_TEXT_MUTED,
                anchor="w",
            ).grid(row=i, column=2, padx=18, pady=8, sticky="w")

    # =====================================================
    # Help Page
    # =====================================================

    def build_help_page(self, parent):
        self.page_header(
            parent,
            "帮助",
            "使用说明、整理流程、安全机制和常见问题。",
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        toolbar.grid(row=0, column=0, padx=6, pady=6, sticky="ew")

        ctk.CTkButton(toolbar, text="打开 README", corner_radius=8, command=self.open_readme_file).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(toolbar, text="复制推荐流程到日志", corner_radius=8, command=self.print_quick_guide_to_log).pack(side="left", padx=8, pady=12)

        self.help_text = ctk.CTkTextbox(
            body,
            font=("Microsoft YaHei UI", 12),
            corner_radius=14,
            fg_color=COL_CARD,
            text_color=COL_TEXT,
        )
        self.help_text.grid(row=1, column=0, padx=6, pady=8, sticky="nsew")
        self.help_text.insert("end", self.get_help_content())
        self.help_text.configure(state="disabled")

    def get_help_content(self):
        return r"""桌面整理助手 使用说明

最简单的用法（在「整理桌面」页面）：
1. 看顶部状态卡，显示“一切就绪”就可以开始。
2. 点 ① 扫描并生成整理方案（不会移动文件）。
3. 点 ② 查看并调整方案，需要的话改分类或跳过。
4. 点 ③ 确认并开始整理，核对摘要后正式整理。

安全机制：
- ① 扫描只生成方案，不会移动任何文件。
- ③ 整理前会显示完整摘要，需要二次确认。
- 文件夹默认 copy（复制），原文件保留。
- 错误报告里的 API Key 会自动隐藏。

模型模式（在「设置 → AI 模式」里切换，普通用户用默认即可）：
- builtin：软件自带 AI，无需安装 Ollama 或 API Key（推荐）。
- none：只按规则分类，速度最快，不使用 AI。
- ollama：本地 Ollama + Qwen。
- openai_compatible：云端 API。

进阶：
- 「高级操作」页可单步运行 check / scan / preview / review / learn / dryrun / apply / undo。
- 「计划解释」页让 AI 解释本次整理计划。
- 「运行日志」页查看完整输出并生成诊断报告。
"""

    def open_readme_file(self):
        if not README_FILE.exists():
            messagebox.showwarning("没有 README", "找不到 README_使用说明.txt。")
            return

        try:
            os.startfile(str(README_FILE))
        except Exception as e:
            messagebox.showerror("打开 README 失败", str(e))

    def print_quick_guide_to_log(self):
        guide = """
推荐流程（在「整理桌面」页面）：
1. 查看状态卡，显示“一切就绪”
2. ① 扫描并生成整理方案
3. ② 查看 / 调整方案
4. ③ 确认并开始整理
5. 打开整理目录查看结果
"""
        self.append_output(guide)

    # =====================================================
    # First Run Wizard (简化引导)
    # =====================================================

    def show_first_run_wizard_if_needed(self):
        config = self.read_config_safely()

        if config.get("first_run_completed", False):
            return

        wizard = ctk.CTkToplevel(self.root)
        wizard.title("欢迎使用")
        wizard.geometry("560x540")
        wizard.transient(self.root)
        wizard.grab_set()

        ctk.CTkLabel(
            wizard,
            text=f"欢迎使用 {APP_TITLE}",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(28, 6))

        ctk.CTkLabel(
            wizard,
            text="它会扫描你的桌面，把文件自动归类整理好。\n下面两件事确认一下就能开始。",
            text_color=COL_TEXT_MUTED,
            justify="center",
        ).pack(pady=(0, 18))

        # 整理目标目录
        box = ctk.CTkFrame(wizard, fg_color=COL_CARD, corner_radius=12)
        box.pack(fill="x", padx=28, pady=8)

        ctk.CTkLabel(
            box, text="整理后的文件放在哪里",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))

        target_var = tk.StringVar(value=config.get("normal_target_root", "") or "D:\\Desktop_Sorted")
        ctk.CTkEntry(row, textvariable=target_var).pack(side="left", fill="x", expand=True)

        def pick_target():
            selected = filedialog.askdirectory(title="选择整理目标目录")
            if selected:
                target_var.set(selected)

        ctk.CTkButton(row, text="浏览", width=70, command=pick_target).pack(side="left", padx=(8, 0))

        # 分类方式（大白话）
        mode_box = ctk.CTkFrame(wizard, fg_color="transparent")
        mode_box.pack(fill="x", padx=28, pady=8)

        mode_var = tk.StringVar(value="builtin")

        for text, value, desc in [
            ("智能分类（推荐）", "builtin", "用软件自带的 AI 判断每个文件该归到哪一类，更准。"),
            ("极速规则分类", "none", "只按文件类型快速归类，不使用 AI，速度最快。"),
        ]:
            card = ctk.CTkFrame(mode_box, fg_color=COL_CARD, corner_radius=12)
            card.pack(fill="x", pady=5)

            ctk.CTkRadioButton(
                card, text=text, variable=mode_var, value=value,
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(anchor="w", padx=16, pady=(12, 2))

            ctk.CTkLabel(
                card, text=desc, text_color=COL_TEXT_MUTED,
                wraplength=460, justify="left",
            ).pack(anchor="w", padx=40, pady=(0, 12))

        def finish():
            self.load_config_panel()
            self.show_page("Home")
            self.update_home_summary()
            self.refresh_home_status()

        def start_using():
            provider = mode_var.get()
            self.update_config_provider(provider, target_var.get().strip() or None)
            wizard.destroy()
            if provider == "builtin" and not self.is_model_present():
                self.open_model_setup(on_done=finish)
            else:
                finish()

        ctk.CTkButton(wizard, text="开始使用", height=40, corner_radius=8, command=start_using).pack(pady=20)

    def update_config_provider(self, provider, target_root=None):
        config = self.read_config_safely()
        default_config = self.get_default_config(True, provider)

        for key, value in default_config.items():
            config.setdefault(key, value)

        config["first_run_completed"] = True
        config["llm_provider"] = provider

        if target_root:
            config["normal_target_root"] = target_root

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        self.append_output(
            f"\n[GUI] 首次设置完成：模式={provider}，目标目录={config.get('normal_target_root')}\n"
        )

    # =====================================================
    # Builtin Model Setup / Download
    # =====================================================

    def open_model_setup(self, on_done=None, allow_skip=True):
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("获取 AI 模型")
        dlg.geometry("540x440")
        dlg.transient(self.root)
        dlg.grab_set()

        ctk.CTkLabel(
            dlg, text="智能分类需要一个 AI 模型文件",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(24, 6), padx=24, anchor="w")

        ctk.CTkLabel(
            dlg,
            text="为了让安装包更小，软件默认不自带模型。\n这个模型可离线运行，只需获取一次。请选择获取方式：",
            text_color=COL_TEXT_MUTED, justify="left",
        ).pack(pady=(0, 16), padx=24, anchor="w")

        def opt(title, desc, cmd, primary=False):
            card = ctk.CTkFrame(dlg, fg_color=COL_CARD, corner_radius=12)
            card.pack(fill="x", padx=24, pady=6)
            card.grid_columnconfigure(0, weight=1)
            tf = ctk.CTkFrame(card, fg_color="transparent")
            tf.grid(row=0, column=0, sticky="w", padx=14, pady=12)
            ctk.CTkLabel(tf, text=title, font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w")
            ctk.CTkLabel(tf, text=desc, text_color=COL_TEXT_MUTED, wraplength=330, justify="left").pack(anchor="w", pady=(2, 0))
            ctk.CTkButton(
                card, text="选择", width=80, height=34, corner_radius=8,
                fg_color=COL_ACCENT if primary else "transparent",
                text_color="white" if primary else COL_TEXT_NAV,
                border_width=0 if primary else 1, border_color=COL_BORDER,
                hover_color=COL_ACCENT if primary else COL_HOVER,
                command=cmd,
            ).grid(row=0, column=1, padx=14, pady=12)

        opt("现在下载（推荐）", "联网自动下载模型并安装到软件目录。",
            lambda: self._start_model_download(dlg, on_done), primary=True)
        opt("我已经有模型文件", "选择本地 .gguf 文件，复制到软件目录。",
            lambda: self._pick_model_file(dlg, on_done))
        if allow_skip:
            opt("暂时跳过（用极速规则分类）",
                "先不使用 AI，按规则快速归类，之后可在「设置」里切回智能分类。",
                lambda: self._skip_model(dlg, on_done))

    def _skip_model(self, dlg, on_done):
        config = self.read_config_safely()
        config["llm_provider"] = "none"
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        try:
            dlg.destroy()
        except Exception:
            pass
        self.load_config_panel()
        if on_done:
            on_done()

    def _pick_model_file(self, dlg, on_done):
        src = filedialog.askopenfilename(
            title="选择模型文件",
            filetypes=[("GGUF 模型", "*.gguf"), ("所有文件", "*.*")],
        )
        if not src:
            return

        target = self.get_model_file_path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("失败", f"无法创建模型目录：{e}")
            return

        try:
            dlg.destroy()
        except Exception:
            pass

        self._run_copy_with_progress(Path(src), target, on_done)

    def _start_model_download(self, dlg, on_done):
        urls = self.get_model_urls()
        if not urls:
            messagebox.showinfo(
                "需要先设置下载地址",
                "还没有配置模型下载地址。\n\n"
                "请在「设置 → 自带 AI 引擎」里填写“模型下载地址 (builtin_model_url)”，"
                "或改用“我已经有模型文件”手动选择。",
                parent=dlg,
            )
            return

        target = self.get_model_file_path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("失败", f"无法创建模型目录：{e}", parent=dlg)
            return

        try:
            dlg.destroy()
        except Exception:
            pass

        self._run_download_with_progress(urls, target, on_done)

    def _make_transfer_modal(self, title):
        modal = ctk.CTkToplevel(self.root)
        modal.title("请稍候")
        modal.geometry("460x200")
        modal.transient(self.root)
        modal.resizable(False, False)
        try:
            modal.grab_set()
        except Exception:
            pass

        ctk.CTkLabel(modal, text=title, font=ctk.CTkFont(size=16, weight="bold")).pack(padx=22, pady=(22, 12), anchor="w")
        pb = ctk.CTkProgressBar(modal, width=416)
        pb.set(0)
        pb.pack(padx=22, pady=(0, 10))
        status = tk.StringVar(value="准备中…")
        ctk.CTkLabel(modal, textvariable=status, text_color=COL_TEXT_MUTED).pack(padx=22, pady=(0, 10), anchor="w")
        cancel_btn = ctk.CTkButton(modal, text="取消", height=32, corner_radius=8, fg_color="#6b7280", hover_color="#4b5563")
        cancel_btn.pack(padx=22, pady=(0, 14), anchor="e")
        return {"modal": modal, "pb": pb, "status": status, "cancel_btn": cancel_btn}

    def _update_transfer(self, modal, done, total):
        try:
            if total > 0:
                modal["pb"].set(min(done / total, 1.0))
                modal["status"].set(f"{done / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB")
            else:
                modal["status"].set(f"已处理 {done / 1024 / 1024:.1f} MB")
        except Exception:
            pass

    def _finish_transfer(self, modal, ok, on_done, err=None):
        try:
            modal["modal"].grab_release()
        except Exception:
            pass
        try:
            modal["modal"].destroy()
        except Exception:
            pass

        if ok:
            config = self.read_config_safely()
            config["llm_provider"] = "builtin"
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self.load_config_panel()
            messagebox.showinfo("完成", "AI 模型已就位，智能分类已启用。")
        else:
            messagebox.showerror(
                "未完成",
                f"模型获取未完成：{err}\n\n"
                "可稍后在「整理桌面」或「设置」里重试，或先用极速规则分类。",
            )

        if on_done:
            on_done()

    def _run_copy_with_progress(self, src, target, on_done):
        modal = self._make_transfer_modal("正在复制模型文件…")
        state = {"cancel": False}
        modal["cancel_btn"].configure(command=lambda: state.update(cancel=True))

        part = target.parent / (target.name + ".part")

        def worker():
            try:
                total = src.stat().st_size or 1
                done = 0
                with open(src, "rb") as fin, open(part, "wb") as fout:
                    while True:
                        if state["cancel"]:
                            raise RuntimeError("已取消")
                        chunk = fin.read(1024 * 1024)
                        if not chunk:
                            break
                        fout.write(chunk)
                        done += len(chunk)
                        self.root.after(0, lambda d=done, t=total: self._update_transfer(modal, d, t))
                if target.exists():
                    target.unlink()
                part.rename(target)
                self.root.after(0, lambda: self._finish_transfer(modal, True, on_done))
            except Exception as e:
                try:
                    if part.exists():
                        part.unlink()
                except Exception:
                    pass
                self.root.after(0, lambda msg=str(e): self._finish_transfer(modal, False, on_done, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _run_download_with_progress(self, urls, target, on_done):
        if isinstance(urls, str):
            urls = [urls]

        modal = self._make_transfer_modal("正在下载模型…")
        state = {"cancel": False}
        modal["cancel_btn"].configure(command=lambda: state.update(cancel=True))

        part = target.parent / (target.name + ".part")

        def set_indeterminate(on):
            try:
                if on:
                    modal["pb"].configure(mode="indeterminate")
                    modal["pb"].start()
                else:
                    modal["pb"].stop()
                    modal["pb"].configure(mode="determinate")
                    modal["pb"].set(0)
            except Exception:
                pass

        def set_status(text):
            try:
                modal["status"].set(text)
            except Exception:
                pass

        def worker():
            import requests
            errors = []
            total_sources = len(urls)

            for idx, url in enumerate(urls, start=1):
                if state["cancel"]:
                    errors.append("已取消")
                    break

                self.root.after(0, lambda i=idx, n=total_sources: set_status(f"正在连接下载源 {i}/{n} …"))
                self.root.after(0, lambda: set_indeterminate(True))

                try:
                    # 连接超时 20s（失败则快速切换下一个源），读取超时 60s
                    with requests.get(url, stream=True, timeout=(20, 60)) as resp:
                        resp.raise_for_status()
                        total = int(resp.headers.get("Content-Length", 0)) or 0
                        done = 0
                        got_first = False

                        with open(part, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=1024 * 256):
                                if state["cancel"]:
                                    raise RuntimeError("已取消")
                                if not chunk:
                                    continue
                                if not got_first:
                                    got_first = True
                                    if total > 0:
                                        self.root.after(0, lambda: set_indeterminate(False))
                                f.write(chunk)
                                done += len(chunk)
                                self.root.after(0, lambda d=done, t=total: self._update_transfer(modal, d, t))

                    if target.exists():
                        target.unlink()
                    part.rename(target)
                    self.root.after(0, lambda: self._finish_transfer(modal, True, on_done))
                    return  # 成功，结束
                except Exception as e:
                    errors.append(f"源{idx}：{e}")
                    try:
                        if part.exists():
                            part.unlink()
                    except Exception:
                        pass
                    if state["cancel"]:
                        break
                    continue  # 试下一个源

            msg = "；".join(errors[-2:]) if errors else "未知错误"
            self.root.after(0, lambda m=msg: self._finish_transfer(modal, False, on_done, m))

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # Command Runner
    # =====================================================

    def get_command_handler(self, command):
        handlers = {
            "check": print_healthcheck,
            "scan": scan_desktop,
            "preview": preview_plan,
            "review": create_human_review,
            "learn": learn_from_review,
            "dryrun": dryrun_plan,
            "apply": apply_plan,
            "undo": undo_last_action,
            "memory": show_memory,
            "state": show_state,
            "run": run_workflow,
        }
        return handlers.get(command)

    def run_command(self, command, guided=False, on_done=None, busy_text=None):
        if self.running:
            messagebox.showwarning("正在运行", "当前已有任务在运行，请等待完成。")
            return

        if command in ["scan", "run"]:
            if not self.confirm_scan_safety():
                return

        if command != "continue" and self.get_command_handler(command) is None:
            messagebox.showerror("错误", f"未知命令：{command}")
            return

        self.running = True
        self.status_var.set(f"运行中：{command}")
        self.guided_on_done = on_done

        if guided:
            self._open_progress_modal(busy_text or "正在处理…")
        else:
            self.show_page("Logs")

        header = (
            f"\n{'=' * 90}\n"
            f"Running Agent command: {command}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'=' * 90}\n"
        )
        self.append_output(header)

        thread = threading.Thread(
            target=self.worker_run_command,
            args=(command,),
            daemon=True,
        )
        thread.start()

    def worker_run_command(self, command):
        try:
            writer = QueueWriter(self.output_queue)

            with redirect_stdout(writer), redirect_stderr(writer):
                if command == "continue":
                    print("=" * 80)
                    print("GUI Continue Workflow")
                    print("=" * 80)
                    print("将执行：learn -> dryrun")
                    print("注意：GUI 版 continue 不会自动 apply。")
                    print("=" * 80)

                    learn_from_review()
                    dryrun_plan()

                    print("\nGUI continue 阶段完成。")
                    print("确认预演无误后，请点击 Apply 正式执行。")
                else:
                    handler = self.get_command_handler(command)
                    handler()

            self.output_queue.put("\n[Process finished with code 0]\n")
        except Exception as e:
            self.output_queue.put(f"\n[GUI Error] {e}\n")
            self.output_queue.put("\n[Process finished with code 1]\n")
        finally:
            self.output_queue.put("__TASK_DONE__")

    def poll_output_queue(self):
        try:
            while True:
                msg = self.output_queue.get_nowait()

                if msg == "__TASK_DONE__":
                    self.running = False
                    self.status_var.set("就绪")
                    on_done = self.guided_on_done
                    self.guided_on_done = None
                    self._close_progress_modal()
                    self.update_home_summary()
                    self.update_dashboard()
                    self.load_plan_explanation_panel()
                    if on_done:
                        try:
                            on_done()
                        except Exception as e:
                            messagebox.showerror("操作失败", str(e))
                    else:
                        self.refresh_home_status()
                    continue

                self.append_output(msg)

                # 引导弹窗里实时显示“最新一行”，不再把用户甩进黑色终端
                if self.guided_status_var is not None:
                    line = msg.strip()
                    if line:
                        self._last_output_line = line[-120:]
                        try:
                            self.guided_status_var.set(self._last_output_line)
                        except Exception:
                            pass
        except queue.Empty:
            pass

        self.root.after(100, self.poll_output_queue)

    # =====================================================
    # Guided Progress Modal
    # =====================================================

    def _open_progress_modal(self, busy_text):
        self._close_progress_modal()

        modal = ctk.CTkToplevel(self.root)
        modal.title("请稍候")
        modal.geometry("440x210")
        modal.transient(self.root)
        modal.resizable(False, False)
        try:
            modal.grab_set()
        except Exception:
            pass

        self.root.update_idletasks()
        try:
            x = self.root.winfo_rootx() + (self.root.winfo_width() - 440) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - 210) // 2
            modal.geometry(f"440x210+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass

        ctk.CTkLabel(
            modal, text=busy_text, font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COL_TEXT, wraplength=400, justify="left",
        ).pack(padx=22, pady=(24, 12), anchor="w")

        pb = ctk.CTkProgressBar(modal, width=396, mode="indeterminate")
        pb.pack(padx=22, pady=(0, 12))
        pb.start()
        self.guided_pb = pb

        self.guided_status_var = tk.StringVar(value="正在准备…")
        ctk.CTkLabel(
            modal, textvariable=self.guided_status_var, font=ctk.CTkFont(size=12),
            text_color=COL_TEXT_MUTED, wraplength=400, justify="left", anchor="w",
        ).pack(padx=22, pady=(0, 10), anchor="w", fill="x")

        ctk.CTkButton(
            modal, text="转到后台（查看详细日志）", height=34, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=COL_BORDER,
            text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
            command=self._detach_guided,
        ).pack(padx=22, pady=(0, 16), anchor="e")

        self.guided_modal = modal

    def _close_progress_modal(self):
        if self.guided_pb is not None:
            try:
                self.guided_pb.stop()
            except Exception:
                pass
            self.guided_pb = None
        if self.guided_modal is not None:
            try:
                self.guided_modal.grab_release()
            except Exception:
                pass
            try:
                self.guided_modal.destroy()
            except Exception:
                pass
            self.guided_modal = None
        self.guided_status_var = None

    def _detach_guided(self):
        # 用户选择“转到后台”：关弹窗、取消自动跳转，任务继续，输出在「运行日志」里
        self.guided_on_done = None
        self._close_progress_modal()
        self.show_page("Logs")

    # =====================================================
    # Scan Safety
    # =====================================================

    def estimate_scan_scope(self):
        try:
            config = self.read_config_safely()
            desktop_path = config.get("desktop_path", "").strip()

            if not desktop_path:
                scan_path = Path.home() / "Desktop"
            else:
                scan_path = Path(desktop_path)

            if not scan_path.exists() or not scan_path.is_dir():
                return {
                    "ok": False,
                    "path": str(scan_path),
                    "message": "扫描路径不存在或不是文件夹",
                }

            total = folders = files = shortcuts = others = 0

            for item in scan_path.iterdir():
                total += 1
                if item.is_dir():
                    folders += 1
                elif item.is_file():
                    files += 1
                    if item.suffix.lower() in [".lnk", ".url"]:
                        shortcuts += 1
                else:
                    others += 1

            return {
                "ok": True,
                "path": str(scan_path),
                "total": total,
                "folders": folders,
                "files": files,
                "shortcuts": shortcuts,
                "others": others,
            }
        except Exception as e:
            return {
                "ok": False,
                "path": "",
                "message": str(e),
            }

    def confirm_scan_safety(self):
        scope = self.estimate_scan_scope()

        if not scope:
            return True

        if not scope.get("ok"):
            return messagebox.askyesno(
                "扫描路径检查失败",
                f"无法预估扫描范围：{scope.get('message')}\n\n仍然继续吗？"
            )

        self.append_output(
            "\n[GUI] 扫描范围预估：\n"
            f"路径：{scope['path']}\n"
            f"第一层项目：{scope['total']} 个\n"
            f"文件夹：{scope['folders']} 个\n"
            f"文件：{scope['files']} 个\n"
            f"快捷方式：{scope['shortcuts']} 个\n"
            f"其他：{scope['others']} 个\n"
        )

        if scope["total"] >= 300:
            return messagebox.askyesno(
                "扫描项目较多",
                f"当前扫描路径第一层项目较多：{scope['total']} 个。\n\n"
                f"路径：{scope['path']}\n\n"
                "这可能需要较长时间。\n\n仍然继续吗？"
            )

        return True

    def show_scan_scope_estimate(self):
        scope = self.estimate_scan_scope()

        if not scope or not scope.get("ok"):
            messagebox.showerror("预估失败", str(scope))
            return

        message = (
            f"扫描路径：\n{scope['path']}\n\n"
            f"第一层项目：{scope['total']} 个\n"
            f"文件夹：{scope['folders']} 个\n"
            f"文件：{scope['files']} 个\n"
            f"快捷方式：{scope['shortcuts']} 个\n"
            f"其他：{scope['others']} 个"
        )

        messagebox.showinfo("扫描范围预估", message)
        self.append_output("\n[GUI] " + message.replace("\n", "\n") + "\n")

    # =====================================================
    # Apply Summary / Confirm
    # =====================================================

    def load_items_for_apply_summary(self):
        if REVIEW_FILE.exists():
            try:
                with open(REVIEW_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("items", []), "desktop_human_review.json"
            except Exception:
                pass

        if PLAN_FILE.exists():
            try:
                with open(PLAN_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("items", []), "desktop_agent_plan.json"
            except Exception:
                pass

        return [], "无"

    def build_apply_summary(self):
        config = self.read_config_safely()
        target_root = config.get("normal_target_root", "")
        folder_mode = config.get("folder_mode", "")

        items, source = self.load_items_for_apply_summary()

        enabled_items = [item for item in items if item.get("enabled", True)]
        skipped_items = [item for item in items if not item.get("enabled", True)]

        type_counts = {"file": 0, "folder": 0, "shortcut": 0, "other": 0}
        category_counts = {}

        for item in enabled_items:
            item_type = item.get("type", "other")
            if item_type not in type_counts:
                item_type = "other"
            type_counts[item_type] += 1

            category = item.get("human_category") or item.get("category") or item.get("ai_category") or "无法判断"
            category_counts[category] = category_counts.get(category, 0) + 1

        category_text = "\n".join(
            [f"- {cat}: {count}" for cat, count in sorted(category_counts.items())]
        ) or "- 无"

        summary = (
            "即将执行整理（Apply）。\n\n"
            f"数据来源：{source}\n"
            f"整理目标目录：{target_root}\n"
            f"folder_mode：{folder_mode}\n\n"
            f"启用项目：{len(enabled_items)}\n"
            f"跳过项目：{len(skipped_items)}\n"
            f"普通文件：{type_counts['file']}\n"
            f"文件夹：{type_counts['folder']}\n"
            f"快捷方式：{type_counts['shortcut']}\n"
            f"其他类型：{type_counts['other']}\n\n"
            f"分类摘要：\n{category_text}\n\n"
            "确认后会正式整理文件。"
        )

        return {
            "summary": summary,
            "enabled_count": len(enabled_items),
        }

    def confirm_apply(self):
        summary_data = self.build_apply_summary()
        enabled_count = summary_data["enabled_count"]
        summary = summary_data["summary"]

        if enabled_count == 0:
            if not messagebox.askyesno("没有启用项目", "当前没有启用项目，仍然尝试 Apply 吗？"):
                return

        if enabled_count >= 200:
            if not messagebox.askyesno(
                "大量项目执行警告",
                f"当前启用项目数量为 {enabled_count} 个。\n\n是否继续查看最终执行摘要？"
            ):
                return

        if messagebox.askyesno("整理二次确认", summary):
            self.append_output("\n[GUI] 用户确认 Apply。执行摘要：\n")
            self.append_output(summary + "\n")
            self.run_command(
                "apply",
                guided=True,
                busy_text="正在整理文件…\n请稍候，不要关闭程序。",
                on_done=self._after_apply_done,
            )
        else:
            self.append_output("\n[GUI] 用户取消 Apply。\n")

    def confirm_undo(self):
        if messagebox.askyesno(
            "确认撤销",
            "Undo 会根据上一次 action log 尝试撤销被移动的项目。\n\n确认撤销吗？"
        ):
            self.run_command("undo")

    # =====================================================
    # Review Logic
    # =====================================================

    def load_review_table(self):
        if not REVIEW_FILE.exists():
            messagebox.showwarning("还没有整理方案", "请先在「整理桌面」点 ① 扫描并生成整理方案。")
            return

        try:
            with open(REVIEW_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return

        self.review_items = data.get("items", [])
        self.review_filter_var.set("全部")
        self.review_dirty = False
        self.refresh_review_table()
        self.show_page("Review")
        self.append_output(f"\n[GUI] 已加载整理方案：{len(self.review_items)} 项\n")

    def refresh_review_table(self):
        if not hasattr(self, "review_list"):
            return

        for w in self.review_list.winfo_children():
            w.destroy()
        self.review_check_vars = {}

        current_filter = self.review_filter_var.get()
        zebra = False
        shown = 0

        for index, item in enumerate(self.review_items):
            human_category = item.get("human_category", "")
            if current_filter != "全部" and human_category != current_filter:
                continue
            self._make_review_row(index, item, zebra)
            zebra = not zebra
            shown += 1

        if shown == 0:
            ctk.CTkLabel(
                self.review_list,
                text="没有可显示的项目。点上方「加载」，或先到「整理桌面」扫描生成方案。",
                text_color=COL_TEXT_MUTED,
            ).pack(pady=30)

        self._update_review_count()

    def _update_review_count(self):
        total = len(self.review_items)
        enabled = sum(1 for it in self.review_items if it.get("enabled", True))
        checked = sum(1 for v in self.review_check_vars.values() if v.get())
        self.review_count_var.set(f"共 {total} 项 · 启用 {enabled} · 勾选 {checked}")

    def save_review_table(self, silent=False):
        if not self.review_items:
            if not silent:
                messagebox.showwarning("没有数据", "当前没有加载整理方案。")
            return False

        try:
            with open(REVIEW_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            data["items"] = self.review_items

            with open(REVIEW_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.review_dirty = False
            self.append_output("\n[GUI] 整理方案已保存。\n")
            if not silent:
                messagebox.showinfo("保存成功", "整理方案已保存。")
            return True
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return False

    def enable_all_review_items(self):
        if not self.review_items:
            return
        for item in self.review_items:
            item["enabled"] = True
        self.review_dirty = True
        self.refresh_review_table()

    def disable_all_review_items(self):
        if not self.review_items:
            return
        if not messagebox.askyesno("确认全部禁用", "确认把所有项目都设为“跳过（禁用）”吗？"):
            return
        for item in self.review_items:
            item["enabled"] = False
        self.review_dirty = True
        self.refresh_review_table()

    def check_all_review_items(self):
        if not self.review_check_vars:
            return
        all_checked = all(v.get() for v in self.review_check_vars.values())
        for v in self.review_check_vars.values():
            v.set(not all_checked)
        self._update_review_count()

    def get_selected_review_indices(self):
        return sorted(i for i, v in self.review_check_vars.items() if v.get())

    def change_selected_category(self):
        indices = self.get_selected_review_indices()
        if not indices:
            messagebox.showwarning("未勾选", "请先在左侧勾选要修改的行（可点「勾选全部 / 取消」）。")
            return

        editor = ctk.CTkToplevel(self.root)
        editor.title("批量修改分类")
        editor.geometry("360x190")
        editor.transient(self.root)
        editor.grab_set()

        ctk.CTkLabel(
            editor,
            text=f"将勾选的 {len(indices)} 个项目改为：",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(pady=16)

        category_var = tk.StringVar(value=CATEGORIES[0])
        ctk.CTkOptionMenu(editor, variable=category_var, values=CATEGORIES, width=260).pack(pady=8)

        def apply_category():
            new_category = category_var.get()
            for index in indices:
                if 0 <= index < len(self.review_items):
                    self.review_items[index]["human_category"] = new_category
            self.review_dirty = True
            self.refresh_review_table()
            editor.destroy()

        ctk.CTkButton(editor, text="应用", command=apply_category).pack(pady=14)

    def _setup_ttk_style(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Treeview",
            background="#ffffff",
            foreground="#111827",
            rowheight=30,
            fieldbackground="#ffffff",
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background="#f3f4f6",
            foreground="#111827",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map("Treeview", background=[("selected", "#dbeafe")])

    # =====================================================
    # Memory Logic
    # =====================================================

    def load_memory_panel(self):
        if not hasattr(self, "memory_tree"):
            return

        try:
            if not MEMORY_FILE.exists():
                with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_MEMORY, f, ensure_ascii=False, indent=2)

            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                data = {"rules": []}
            data.setdefault("rules", [])
            if not isinstance(data["rules"], list):
                data["rules"] = []

            self.memory_data = data
            self.memory_dirty = False
            self.refresh_memory_table()
        except Exception as e:
            messagebox.showerror("加载记忆失败", str(e))

    def refresh_memory_table(self):
        if not hasattr(self, "memory_tree"):
            return

        for row in self.memory_tree.get_children():
            self.memory_tree.delete(row)

        rules = self.memory_data.get("rules", [])
        for index, rule in enumerate(rules):
            self.memory_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    rule.get("match", ""),
                    rule.get("category", ""),
                    rule.get("note", ""),
                ),
            )

        self.memory_count_var.set(f"共 {len(rules)} 条规则")

    def get_selected_memory_indices(self):
        indices = []
        for row_id in self.memory_tree.selection():
            try:
                indices.append(int(row_id))
            except Exception:
                pass
        return sorted(indices)

    def add_memory_rule_dialog(self):
        self._open_memory_rule_editor(None)

    def edit_selected_memory_rule(self):
        indices = self.get_selected_memory_indices()
        if not indices:
            messagebox.showwarning("未选择", "请先选择一条规则。")
            return
        self._open_memory_rule_editor(indices[0])

    def _open_memory_rule_editor(self, index):
        is_new = index is None
        rule = {} if is_new else self.memory_data["rules"][index]

        editor = ctk.CTkToplevel(self.root)
        editor.title("添加规则" if is_new else "编辑规则")
        editor.geometry("470x360")
        editor.transient(self.root)
        editor.grab_set()

        ctk.CTkLabel(editor, text="命中关键词（出现在文件名或路径里）", anchor="w").pack(fill="x", padx=24, pady=(20, 4))
        match_var = tk.StringVar(value=rule.get("match", ""))
        ctk.CTkEntry(editor, textvariable=match_var).pack(fill="x", padx=24)

        ctk.CTkLabel(editor, text="归类到", anchor="w").pack(fill="x", padx=24, pady=(14, 4))
        cat_default = rule.get("category", CATEGORIES[0])
        if cat_default not in CATEGORIES:
            cat_default = CATEGORIES[0]
        cat_var = tk.StringVar(value=cat_default)
        ctk.CTkOptionMenu(editor, variable=cat_var, values=CATEGORIES).pack(fill="x", padx=24)

        ctk.CTkLabel(editor, text="备注（可选）", anchor="w").pack(fill="x", padx=24, pady=(14, 4))
        note_var = tk.StringVar(value=rule.get("note", ""))
        ctk.CTkEntry(editor, textvariable=note_var).pack(fill="x", padx=24)

        def save():
            match_text = match_var.get().strip()
            if not match_text:
                messagebox.showwarning("缺少关键词", "请填写命中关键词。", parent=editor)
                return
            new_rule = {
                "match": match_text,
                "category": cat_var.get(),
                "note": note_var.get().strip(),
            }
            if is_new:
                self.memory_data["rules"].append(new_rule)
            else:
                self.memory_data["rules"][index] = new_rule
            self.memory_dirty = True
            self.refresh_memory_table()
            editor.destroy()

        ctk.CTkButton(editor, text="保存", command=save).pack(pady=24)

    def delete_selected_memory_rules(self):
        indices = self.get_selected_memory_indices()
        if not indices:
            messagebox.showwarning("未选择", "请先选择要删除的规则。")
            return
        if not messagebox.askyesno("确认删除", f"确认删除选中的 {len(indices)} 条规则吗？"):
            return
        for i in reversed(indices):
            if 0 <= i < len(self.memory_data["rules"]):
                del self.memory_data["rules"][i]
        self.memory_dirty = True
        self.refresh_memory_table()

    def save_memory_panel(self, silent=False):
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.memory_data, f, ensure_ascii=False, indent=2)
            self.memory_dirty = False
            if not silent:
                messagebox.showinfo("保存成功", "整理记忆已保存。")
            return True
        except Exception as e:
            messagebox.showerror("保存记忆失败", str(e))
            return False

    # =====================================================
    # Explanation Logic
    # =====================================================

    def load_plan_explanation_panel(self):
        if not hasattr(self, "explanation_text"):
            return

        self.explanation_text.delete("1.0", "end")

        if EXPLANATION_MD_FILE.exists():
            try:
                content = EXPLANATION_MD_FILE.read_text(encoding="utf-8")
                self.explanation_text.insert("end", content)
            except Exception as e:
                self.explanation_text.insert("end", f"读取解释文件失败：{e}")
        else:
            self.explanation_text.insert(
                "end",
                "还没有生成计划解释。\n\n请先在「整理桌面」生成方案，或点击“生成 / 刷新解释”。",
            )

    def generate_plan_explanation_gui(self):
        try:
            writer = QueueWriter(self.output_queue)
            with redirect_stdout(writer), redirect_stderr(writer):
                explain_current_plan()

            self.load_plan_explanation_panel()
            self.show_page("Explanation")
        except Exception as e:
            messagebox.showerror("生成计划解释失败", str(e))

    def open_plan_explanation_file(self):
        if not EXPLANATION_MD_FILE.exists():
            messagebox.showwarning("没有解释文件", "请先生成计划解释。")
            return

        try:
            os.startfile(str(EXPLANATION_MD_FILE))
        except Exception as e:
            messagebox.showerror("打开解释文件失败", str(e))

    # =====================================================
    # Config Logic
    # =====================================================

    def browse_desktop_path(self):
        initial_dir = self.config_vars.get("desktop_path").get().strip() if self.config_vars.get("desktop_path") else ""

        if not initial_dir:
            initial_dir = str(Path.home() / "Desktop")

        selected = filedialog.askdirectory(
            title="选择要扫描的桌面或文件夹",
            initialdir=initial_dir if Path(initial_dir).exists() else str(Path.home()),
        )

        if selected:
            self.config_vars["desktop_path"].set(selected)

    def browse_target_root(self):
        initial_dir = self.config_vars.get("normal_target_root").get().strip() if self.config_vars.get("normal_target_root") else ""

        if not initial_dir:
            initial_dir = "D:\\Desktop_Sorted"

        selected = filedialog.askdirectory(
            title="选择整理目标目录",
            initialdir=initial_dir if Path(initial_dir).exists() else str(Path.home()),
        )

        if selected:
            self.config_vars["normal_target_root"].set(selected)

    def load_config_panel(self):
        if not hasattr(self, "config_vars") or not self.config_vars:
            return

        config = self.read_config_safely()

        self._loading_config = True
        for key, var in self.config_vars.items():
            value = config.get(key, "")
            if isinstance(value, bool):
                value = "true" if value else "false"
            var.set(str(value))
        self._loading_config = False
        self.config_dirty = False

    def _on_config_var_write(self):
        if not self._loading_config:
            self.config_dirty = True

    def save_config_panel(self, silent=False):
        try:
            config = {}

            first_run_text = self.config_vars["first_run_completed"].get().strip().lower()
            config["first_run_completed"] = first_run_text == "true"

            config["llm_provider"] = self.config_vars["llm_provider"].get().strip() or "none"
            config["model"] = self.config_vars["model"].get().strip()
            config["ollama_url"] = self.config_vars["ollama_url"].get().strip()

            config["api_base_url"] = self.config_vars["api_base_url"].get().strip()
            config["api_model"] = self.config_vars["api_model"].get().strip()
            config["api_key"] = self.config_vars["api_key"].get().strip()
            config["builtin_server_host"] = self.config_vars["builtin_server_host"].get().strip() or "127.0.0.1"
            config["builtin_server_port"] = int(self.config_vars["builtin_server_port"].get().strip())
            config["builtin_server_path"] = self.config_vars["builtin_server_path"].get().strip() or "runtime\\llama-server.exe"
            config["builtin_model_path"] = self.config_vars["builtin_model_path"].get().strip() or "models\\qwen-small.gguf"
            config["builtin_api_model"] = self.config_vars["builtin_api_model"].get().strip() or "builtin-model"
            config["builtin_context_size"] = int(self.config_vars["builtin_context_size"].get().strip())
            config["builtin_threads"] = int(self.config_vars["builtin_threads"].get().strip())
            config["builtin_model_url"] = self.config_vars["builtin_model_url"].get().strip()

            config["desktop_path"] = self.config_vars["desktop_path"].get().strip()
            config["normal_target_root"] = self.config_vars["normal_target_root"].get().strip()
            config["folder_mode"] = self.config_vars["folder_mode"].get().strip() or "copy"

            config["batch_size"] = int(self.config_vars["batch_size"].get().strip())
            config["max_internal_items_per_folder"] = int(
                self.config_vars["max_internal_items_per_folder"].get().strip()
            )

            if first_run_text not in ["true", "false"]:
                raise ValueError("first_run_completed 只能是 true 或 false")

            if config["llm_provider"] not in ["none", "ollama", "openai_compatible", "builtin"]:
                raise ValueError("llm_provider 只能是 none、ollama、openai_compatible 或 builtin")

            if config["folder_mode"] not in ["copy", "move"]:
                raise ValueError("folder_mode 只能是 copy 或 move")

            if config["batch_size"] <= 0:
                raise ValueError("batch_size 必须大于 0")

            if config["max_internal_items_per_folder"] <= 0:
                raise ValueError("max_internal_items_per_folder 必须大于 0")

            if config["builtin_server_port"] <= 0:
                raise ValueError("builtin_server_port 必须大于 0")

            if config["builtin_context_size"] <= 0:
                raise ValueError("builtin_context_size 必须大于 0")

            if config["builtin_threads"] <= 0:
                raise ValueError("builtin_threads 必须大于 0")

            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            self.config_dirty = False
            self.update_home_summary()
            self.update_dashboard()
            if not silent:
                messagebox.showinfo("保存成功", "设置已保存。建议回到「整理桌面」点“重新检查”。")
            return True
        except Exception as e:
            messagebox.showerror("保存设置失败", str(e))
            return False

    def reset_config_to_default(self):
        if not messagebox.askyesno(
            "确认重置配置",
            "这会把 config.json 重置为默认配置。\n\n默认模式为 none，API Key 会被清空。\n\n确认继续吗？",
        ):
            return

        default_config = self.get_default_config(True, "none")

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)

        self.load_config_panel()
        self.update_home_summary()
        self.update_dashboard()

    def export_config(self):
        target_path = filedialog.asksaveasfilename(
            title="导出配置",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialfile="config_backup.json",
        )

        if not target_path:
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as src:
                data = json.load(src)

            with open(target_path, "w", encoding="utf-8") as dst:
                json.dump(data, dst, ensure_ascii=False, indent=2)

            messagebox.showinfo("导出成功", f"配置已导出到：\n{target_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def import_config(self):
        source_path = filedialog.askopenfilename(
            title="导入配置",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )

        if not source_path:
            return

        try:
            with open(source_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            default_config = self.get_default_config(True, "none")
            for key, value in default_config.items():
                config.setdefault(key, value)

            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            self.load_config_panel()
            self.update_home_summary()
            self.update_dashboard()
            messagebox.showinfo("导入成功", "配置已导入。建议回到「整理桌面」点“重新检查”。")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    # =====================================================
    # Diagnostics
    # =====================================================

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

    # =====================================================
    # About / Utils
    # =====================================================

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

    def show_about(self):
        config = self.read_config_safely()

        message = (
            f"{APP_NAME} {APP_VERSION}\n\n"
            f"当前模式：{config.get('llm_provider')}\n"
            f"目标目录：{config.get('normal_target_root')}\n"
            f"folder_mode：{config.get('folder_mode')}\n\n"
            f"程序目录：\n{PROJECT_DIR}\n\n"
            f"当前日志：\n{self.current_log_file}\n"
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