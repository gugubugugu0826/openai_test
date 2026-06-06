import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from desktop_agent.healthcheck import run_healthcheck
from desktop_agent_ui.theme import *
from desktop_agent_ui.utils import get_effective_scan_paths, format_scan_paths

OBSERVATION_FILE = Path("desktop_observation.json")
REVIEW_FILE      = Path("desktop_human_review.json")
ACTION_LOG_FILE  = Path("desktop_action_log.json")


class DashboardPageMixin:
    def build_home_page(self, parent):
        self.page_header(
            parent,
            "整理桌面",
            "先检查准备情况，确认无误后按 1 → 3 完成整理。",
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
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

        # 引导三步 — (序号, 标题, 描述, 按钮文字, 回调, 主色, hover色, 完成判断文件)
        self._step_badge_vars = [tk.StringVar(value=""), tk.StringVar(value=""), tk.StringVar(value="")]
        steps = [
            ("1", "扫描并生成整理方案",
             "让 AI 扫描桌面、自动分类，生成一份方案（此步不会移动文件）。",
             "扫描", self.start_scan, COL_ACCENT, "#1d4ed8"),
            ("2", "查看并调整方案",
             "检查分类结果，可以手动改分类或跳过个别文件。",
             "查看", self.load_review_table, COL_ACCENT, "#1d4ed8"),
            ("3", "确认并开始整理",
             "核对摘要后正式整理。默认复制文件，原文件保留。",
             "整理", self.confirm_apply, COL_DANGER, "#b91c1c"),
        ]
        for i, (num, title, desc, btn_text, cmd, color, hover_color) in enumerate(steps, start=2):
            self._step_card(body, i, num, title, desc, btn_text, cmd, color, hover_color, self._step_badge_vars[i - 2])

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

    def _step_card(self, parent, row, num, title, desc, btn_text, cmd,
                   color, hover_color=None, badge_var=None):
        card = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=14)
        card.grid(row=row, column=0, padx=6, pady=6, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text=num, width=34, height=34, corner_radius=17,
            fg_color=color, text_color="white",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=10)

        tf = ctk.CTkFrame(card, fg_color="transparent")
        tf.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=8)
        ctk.CTkLabel(
            tf, text=title, font=ctk.CTkFont(size=15, weight="bold"),
            text_color=COL_TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            tf, text=desc, font=ctk.CTkFont(size=12),
            text_color=COL_TEXT_MUTED, justify="left",
        ).pack(anchor="w", pady=(2, 0))
        if badge_var is not None:
            ctk.CTkLabel(
                tf, textvariable=badge_var,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=COL_OK,
            ).pack(anchor="w", pady=(3, 0))

        ctk.CTkButton(
            card, text=btn_text, width=88, height=36, corner_radius=8,
            fg_color=color, hover_color=hover_color or color, command=cmd,
        ).grid(row=0, column=2, padx=14, pady=10)

    def update_home_summary(self):
        if not hasattr(self, "home_scan_var"):
            return
        config = self.read_config_safely()
        dp = config.get("desktop_path", "").strip()
        scan = format_scan_paths(get_effective_scan_paths(dp))
        self.home_scan_var.set(scan)
        self.home_target_var.set(config.get("normal_target_root", "") or "-")

        if hasattr(self, "_step_badge_vars"):
            step_files  = [OBSERVATION_FILE, REVIEW_FILE, ACTION_LOG_FILE]
            step_labels = ["✓ 已扫描", "✓ 已生成方案", "✓ 已整理"]
            for var, f, label in zip(self._step_badge_vars, step_files, step_labels):
                var.set(label if f.exists() else "")

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
        self.show_page("Review")

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
        fails = [r for r in results if not r.get("ok") and r.get("name") not in self.HIDDEN_CHECKS]

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
        ).grid(row=0, column=0, padx=18, pady=(12, 2), sticky="w")
        ctk.CTkLabel(
            self.home_status_card, text=subtitle,
            font=ctk.CTkFont(size=13), text_color=color,
            wraplength=620, justify="left",
        ).grid(row=1, column=0, padx=18, pady=(0, 8), sticky="w")

        rrow = 2

        # Only show failed items to keep the card compact
        for r in fails:
            name = self.FRIENDLY_CHECKS.get(r.get("name"), r.get("name"))
            line = ctk.CTkFrame(self.home_status_card, fg_color="transparent")
            line.grid(row=rrow, column=0, padx=18, pady=2, sticky="w")
            ctk.CTkLabel(
                line, text="✗", text_color=COL_DANGER, width=18,
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(side="left")
            ctk.CTkLabel(
                line, text=f"{name}：{r.get('message', '')}",
                text_color="#7c2d12",
                font=ctk.CTkFont(size=13), justify="left", wraplength=560,
            ).pack(side="left", padx=(6, 0))
            rrow += 1

        config = self.read_config_safely()
        if config.get("llm_provider") == "builtin" and not self.is_model_present():
            ctk.CTkButton(
                self.home_status_card, text="获取 AI 模型", height=32, corner_radius=8,
                fg_color=COL_ACCENT, hover_color=COL_ACCENT,
                command=lambda: self.open_model_setup(on_done=self.refresh_home_status),
            ).grid(row=rrow, column=0, padx=18, pady=(6, 0), sticky="w")
            rrow += 1

        ctk.CTkButton(
            self.home_status_card, text="查看完整检查日志", height=28, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=COL_BORDER,
            text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
            command=lambda: self.run_command("check"),
        ).grid(row=rrow, column=0, padx=18, pady=(6, 12), sticky="w")

        self.status_var.set("就绪" if all_ok else f"{len(fails)} 项待处理")

    # =====================================================
    # Advanced Page (高级操作 —— 单步命令 / 文件状态 / 诊断)
    # =====================================================
