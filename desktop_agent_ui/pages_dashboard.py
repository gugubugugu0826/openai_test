import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from desktop_agent.healthcheck import run_healthcheck
from desktop_agent.i18n import get_language, t
from desktop_agent_ui.theme import *
from desktop_agent_ui.utils import format_scan_paths, get_effective_scan_paths

OBSERVATION_FILE = Path("desktop_observation.json")
REVIEW_FILE = Path("desktop_human_review.json")
ACTION_LOG_FILE = Path("desktop_action_log.json")


class DashboardPageMixin:
    def build_home_page(self, parent):
        self.page_header(parent, t("dashboard.page_title"), t("dashboard.page_subtitle"))

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        self.home_status_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        self.home_status_card.grid(row=0, column=0, padx=6, pady=(6, 10), sticky="ew")
        self.home_status_card.grid_columnconfigure(0, weight=1)
        self._render_home_status_message(
            t("dashboard.checking_title"),
            t("dashboard.checking_subtitle"),
            COL_TEXT_MUTED,
            COL_CARD,
        )

        summary = ctk.CTkFrame(body, fg_color="transparent")
        summary.grid(row=1, column=0, padx=0, pady=(0, 4), sticky="ew")
        summary.grid_columnconfigure((0, 1), weight=1)

        self.home_scan_var = tk.StringVar(value="-")
        self.home_target_var = tk.StringVar(value="-")
        self.home_suggestions_var = tk.StringVar(value="-")
        self.home_schedule_var = tk.StringVar(value="-")
        summary.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self._mini_card(summary, 0, t("dashboard.scan_path"), self.home_scan_var)
        self._mini_card(summary, 1, t("dashboard.target_folder"), self.home_target_var)
        self._mini_card(summary, 2, t("dashboard.pending_suggestions", default="待确认建议"), self.home_suggestions_var)
        self._mini_card(summary, 3, t("dashboard.next_schedule", default="下次自动整理"), self.home_schedule_var)

        self._step_badge_vars = [tk.StringVar(value=""), tk.StringVar(value=""), tk.StringVar(value="")]
        steps = [
            ("1", t("dashboard.step1_title"), t("dashboard.step1_body"), t("dashboard.step1_button"), self.start_scan, COL_ACCENT, "#1d4ed8"),
            ("2", t("dashboard.step2_title"), t("dashboard.step2_body"), t("dashboard.step2_button"), self.load_review_table, COL_ACCENT, "#1d4ed8"),
            ("3", t("dashboard.step3_title"), t("dashboard.step3_body"), t("dashboard.step3_button"), self.confirm_apply, COL_DANGER, "#b91c1c"),
        ]
        for i, (num, title, desc, btn_text, cmd, color, hover_color) in enumerate(steps, start=2):
            self._step_card(body, i, num, title, desc, btn_text, cmd, color, hover_color, self._step_badge_vars[i - 2])

        footer = ctk.CTkFrame(body, fg_color="transparent")
        footer.grid(row=5, column=0, pady=(8, 4), sticky="w")

        ctk.CTkButton(
            footer,
            text=t("dashboard.recheck"),
            width=110,
            height=36,
            corner_radius=8,
            fg_color="transparent",
            border_width=1,
            border_color=COL_BORDER,
            text_color=COL_TEXT_NAV,
            hover_color=COL_HOVER,
            command=self.refresh_home_status,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            footer,
            text=t("dashboard.open_target"),
            width=160 if get_language() == "en" else 130,
            height=36,
            corner_radius=8,
            fg_color=COL_OK,
            hover_color="#059669",
            command=self.open_target_folder,
        ).pack(side="left", padx=6)

        self._show_v3_guide_if_needed(body)

    def _mini_card(self, parent, col, label, var):
        card = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=12)
        card.grid(row=0, column=col, padx=6, pady=6, sticky="ew")
        ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=12, weight="bold"), text_color=COL_TEXT_MUTED).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(card, textvariable=var, font=ctk.CTkFont(size=13), text_color=COL_TEXT, wraplength=380, justify="left", anchor="w").pack(anchor="w", padx=14, pady=(0, 12))

    def _step_card(self, parent, row, num, title, desc, btn_text, cmd, color, hover_color=None, badge_var=None):
        card = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=14)
        card.grid(row=row, column=0, padx=6, pady=6, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text=num, width=34, height=34, corner_radius=17, fg_color=color, text_color="white", font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=0, padx=14, pady=10)

        tf = ctk.CTkFrame(card, fg_color="transparent")
        tf.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=8)
        ctk.CTkLabel(tf, text=title, font=ctk.CTkFont(size=15, weight="bold"), text_color=COL_TEXT).pack(anchor="w")
        ctk.CTkLabel(tf, text=desc, font=ctk.CTkFont(size=12), text_color=COL_TEXT_MUTED, justify="left").pack(anchor="w", pady=(2, 0))
        if badge_var is not None:
            ctk.CTkLabel(tf, textvariable=badge_var, font=ctk.CTkFont(size=11, weight="bold"), text_color=COL_OK).pack(anchor="w", pady=(3, 0))

        ctk.CTkButton(card, text=btn_text, width=88, height=36, corner_radius=8, fg_color=color, hover_color=hover_color or color, command=cmd).grid(row=0, column=2, padx=14, pady=10)

    def update_home_summary(self):
        if not hasattr(self, "home_scan_var"):
            return
        config = self.read_config_safely()
        dp = config.get("desktop_path", "").strip()
        scan = format_scan_paths(get_effective_scan_paths(dp))
        self.home_scan_var.set(scan)
        self.home_target_var.set(config.get("normal_target_root", "") or "-")

        # Suggestion queue count
        try:
            from desktop_agent.suggestion_queue import get_pending_count
            count = get_pending_count()
            self.home_suggestions_var.set(f"{count} 条" if count > 0 else t("dashboard.no_suggestions", default="暂无"))
        except Exception:
            self.home_suggestions_var.set("-")

        # Next schedule
        try:
            from desktop_agent.scheduler import get_task_status
            status = get_task_status()
            if status.get("exists"):
                self.home_schedule_var.set(status.get("next_run", t("dashboard.schedule_unknown", default="已启用")))
            else:
                self.home_schedule_var.set(t("dashboard.schedule_off", default="未启用"))
        except Exception:
            self.home_schedule_var.set("-")

        if hasattr(self, "_step_badge_vars"):
            step_files = [OBSERVATION_FILE, REVIEW_FILE, ACTION_LOG_FILE]
            step_labels = [t("dashboard.badge_scanned"), t("dashboard.badge_plan_ready"), t("dashboard.badge_applied")]
            for var, file_path, label in zip(self._step_badge_vars, step_files, step_labels):
                var.set(label if file_path.exists() else "")

    def _show_v3_guide_if_needed(self, body):
        """Show a dismissible v3.0 new features card if not yet dismissed."""
        config = self.read_config_safely()
        if config.get("v3_guide_dismissed"):
            return
        self._v3_guide_card = ctk.CTkFrame(body, fg_color="#eff6ff", corner_radius=14)
        self._v3_guide_card.grid(row=6, column=0, padx=6, pady=(8, 0), sticky="ew")
        self._v3_guide_card.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self._v3_guide_card, fg_color="transparent")
        hdr.grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 4), sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hdr,
            text=t("dashboard.v3_guide_title", default="v3.0 新功能 — 快速上手"),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#1e40af",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            hdr,
            text=t("dashboard.v3_guide_dismiss", default="知道了，不再显示"),
            width=130, height=28, corner_radius=6,
            fg_color="transparent", border_width=1, border_color="#93c5fd",
            text_color="#1d4ed8", hover_color="#dbeafe",
            command=self._dismiss_v3_guide,
        ).grid(row=0, column=1, sticky="e")

        items = [
            t("dashboard.v3_tip1", default="💡 建议队列：在「设置」里开启建议模式 → 扫描 → 审阅建议再执行，更安全"),
            t("dashboard.v3_tip2", default="📁 多来源：可添加下载、文档等目录一起整理，不局限于桌面"),
            t("dashboard.v3_tip3", default="⏱ 定时整理：在「设置 → 定时自动整理」配置 Windows 计划任务自动运行"),
            t("dashboard.v3_tip4", default="🧠 意图输入：在「高级操作」页填写本次整理目的，AI 会优先考虑你的意图"),
        ]
        for i, tip in enumerate(items):
            ctk.CTkLabel(
                self._v3_guide_card,
                text=tip,
                font=ctk.CTkFont(size=12),
                text_color="#1e40af",
                anchor="w",
                justify="left",
                wraplength=700,
            ).grid(row=i + 1, column=0, columnspan=2, padx=22, pady=2, sticky="w")

        ctk.CTkFrame(self._v3_guide_card, fg_color="transparent", height=10).grid(row=len(items) + 1, column=0)

    def _dismiss_v3_guide(self):
        try:
            import json
            from pathlib import Path
            cfg_path = Path("config.json")
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            data["v3_guide_dismissed"] = True
            cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        if hasattr(self, "_v3_guide_card"):
            self._v3_guide_card.destroy()

    def start_scan(self):
        self.run_command("run", guided=True, busy_text=t("dashboard.scan_busy"), on_done=self._after_scan_done)

    def _after_scan_done(self):
        if not REVIEW_FILE.exists():
            messagebox.showwarning(t("dashboard.no_plan_title"), t("dashboard.no_plan_message"))
            self.show_page("Logs")
            return
        self.load_review_table()
        self.show_page("Review")

    def _after_apply_done(self):
        self.show_page("Home")
        self.refresh_home_status()
        if messagebox.askyesno(t("dashboard.apply_done_title"), t("dashboard.apply_done_message")):
            self.open_target_folder()

    def refresh_home_status(self):
        if not hasattr(self, "home_status_card") or self._checking:
            return
        self._checking = True
        self.status_var.set(t("dashboard.checking_title"))
        self._render_home_status_message(t("dashboard.checking_title"), t("dashboard.checking_subtitle"), COL_TEXT_MUTED, "#f9fafb")
        self.update_home_summary()
        threading.Thread(target=self._do_home_check, daemon=True).start()

    def _do_home_check(self):
        try:
            results = run_healthcheck()
        except Exception as exc:
            results = [{"name": "Error", "ok": False, "message": str(exc)}]
        try:
            self.root.after(0, lambda: self._render_home_status(results))
        except RuntimeError:
            return

    def _clear(self, frame):
        for widget in frame.winfo_children():
            widget.destroy()

    def _render_home_status_message(self, title, subtitle, color, bg):
        self.home_status_card.configure(fg_color=bg)
        self._clear(self.home_status_card)
        ctk.CTkLabel(self.home_status_card, text=title, font=ctk.CTkFont(size=16, weight="bold"), text_color=color).grid(row=0, column=0, padx=18, pady=(16, 2), sticky="w")
        ctk.CTkLabel(self.home_status_card, text=subtitle, font=ctk.CTkFont(size=13), text_color=color).grid(row=1, column=0, padx=18, pady=(0, 16), sticky="w")

    def _render_home_status(self, results):
        self._checking = False
        all_ok = all(r.get("ok") for r in results)
        fails = [r for r in results if not r.get("ok") and r.get("name") not in self.HIDDEN_CHECKS]

        self._clear(self.home_status_card)
        if all_ok:
            title = t("dashboard.ready_title")
            subtitle = t("dashboard.ready_subtitle")
            color = COL_OK
            bg = COL_OK_SOFT
        else:
            title = t("dashboard.issue_title", count=len(fails))
            subtitle = t("dashboard.issue_subtitle")
            color = COL_WARN_TEXT
            bg = COL_WARN_SOFT

        self.home_status_card.configure(fg_color=bg)
        ctk.CTkLabel(self.home_status_card, text=title, font=ctk.CTkFont(size=16, weight="bold"), text_color=color).grid(row=0, column=0, padx=18, pady=(12, 2), sticky="w")
        ctk.CTkLabel(self.home_status_card, text=subtitle, font=ctk.CTkFont(size=13), text_color=color, wraplength=620, justify="left").grid(row=1, column=0, padx=18, pady=(0, 8), sticky="w")

        rrow = 2
        for result in fails:
            name = t(self.FRIENDLY_CHECKS.get(result.get("name"), result.get("name")))
            line = ctk.CTkFrame(self.home_status_card, fg_color="transparent")
            line.grid(row=rrow, column=0, padx=18, pady=2, sticky="w")
            ctk.CTkLabel(line, text="✗", text_color=COL_DANGER, width=18, font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
            ctk.CTkLabel(line, text=f"{name}: {result.get('message', '')}", text_color="#7c2d12", font=ctk.CTkFont(size=13), justify="left", wraplength=560).pack(side="left", padx=(6, 0))
            rrow += 1

        config = self.read_config_safely()
        if config.get("llm_provider") == "builtin" and not self.is_model_present():
            ctk.CTkButton(
                self.home_status_card,
                text=t("dashboard.get_ai_model"),
                height=32,
                corner_radius=8,
                fg_color=COL_ACCENT,
                hover_color=COL_ACCENT,
                command=lambda: self.open_model_setup(on_done=self.refresh_home_status),
            ).grid(row=rrow, column=0, padx=18, pady=(6, 0), sticky="w")
            rrow += 1

        ctk.CTkButton(
            self.home_status_card,
            text=t("dashboard.open_check_log"),
            height=28,
            corner_radius=8,
            fg_color="transparent",
            border_width=1,
            border_color=COL_BORDER,
            text_color=COL_TEXT_NAV,
            hover_color=COL_HOVER,
            command=lambda: self.run_command("check"),
        ).grid(row=rrow, column=0, padx=18, pady=(6, 12), sticky="w")

        self.status_var.set(t("dashboard.status_ready") if all_ok else t("dashboard.status_issues", count=len(fails)))

    def _check_pattern_suggestions_startup(self):
        def _run():
            try:
                from desktop_agent.pattern_analyzer import analyze_correction_history
                suggestions = analyze_correction_history()
                if suggestions:
                    self.root.after(0, lambda: self._show_pattern_suggestions_dialog(suggestions))
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    def _show_pattern_suggestions_dialog(self, suggestions):
        if not suggestions:
            return
        texts = [s.suggestion_text for s in suggestions[:5]]
        msg = "\n".join(f"{i + 1}. {txt}" for i, txt in enumerate(texts))
        if len(suggestions) > 5:
            msg += f"\n...还有 {len(suggestions) - 5} 条"
        msg += "\n\n是否打开记忆页面查看并确认这些规则建议？"
        if messagebox.askyesno(t("pattern.dialog_title", default="发现规则建议"), msg):
            self.show_page("Memory")
