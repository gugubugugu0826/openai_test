"""Suggestion Queue page — shows accumulated AI suggestions, lets user confirm."""
from __future__ import annotations

import threading
import tkinter as tk
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from desktop_agent.categories import CATEGORIES
from desktop_agent.i18n import get_category_display, get_category_display_options, t
from desktop_agent.suggestion_queue import (
    SuggestionItem,
    clear_queue,
    get_pending_count,
    load_queue,
    save_queue,
    validate_queue,
)
from desktop_agent_ui.theme import *
from desktop_agent_ui.utils import QueueWriter

QUEUE_FILE = Path("suggestion_queue.json")


class SuggestionsPageMixin:
    def build_suggestions_page(self, parent):
        self.page_header(
            parent,
            t("suggestions.page_title", default="建议队列"),
            t("suggestions.page_subtitle", default="AI 在后台累积的整理建议，确认后一次性执行"),
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        # ── Toolbar ──────────────────────────────────────────────────────
        toolbar = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        toolbar.grid(row=0, column=0, padx=6, pady=(6, 8), sticky="ew")
        toolbar.grid_columnconfigure(1, weight=1)

        self.sugg_count_var = tk.StringVar(value=t("suggestions.loading", default="加载中…"))
        self.sugg_since_var = tk.StringVar(value="")

        left = ctk.CTkFrame(toolbar, fg_color="transparent")
        left.grid(row=0, column=0, padx=16, pady=12, sticky="w")
        ctk.CTkLabel(left, textvariable=self.sugg_count_var, font=ctk.CTkFont(size=16, weight="bold"), text_color=COL_TEXT).pack(anchor="w")
        ctk.CTkLabel(left, textvariable=self.sugg_since_var, font=ctk.CTkFont(size=11), text_color=COL_TEXT_MUTED).pack(anchor="w")

        btn_row = ctk.CTkFrame(toolbar, fg_color="transparent")
        btn_row.grid(row=0, column=1, padx=12, pady=12, sticky="e")

        ctk.CTkButton(
            btn_row,
            text=t("suggestions.refresh", default="刷新"),
            width=80, height=34, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=COL_BORDER,
            text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
            command=self.reload_suggestions,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_row,
            text=t("suggestions.validate", default="验证路径"),
            width=100, height=34, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=COL_BORDER,
            text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
            command=self.validate_and_reload,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_row,
            text=t("suggestions.clear_all", default="清空队列"),
            width=90, height=34, corner_radius=8,
            fg_color="#6b7280", hover_color="#4b5563",
            text_color="white",
            command=self.clear_suggestion_queue,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_row,
            text=t("suggestions.execute_all", default="确认并执行"),
            width=110, height=34, corner_radius=8,
            fg_color=COL_DANGER, hover_color="#b91c1c",
            text_color="white",
            command=self.execute_all_suggestions,
        ).pack(side="left", padx=4)

        # ── Info banner ──────────────────────────────────────────────────
        self.sugg_banner_var = tk.StringVar(value="")
        self.sugg_banner = ctk.CTkLabel(
            body,
            textvariable=self.sugg_banner_var,
            font=ctk.CTkFont(size=12),
            text_color=COL_TEXT_MUTED,
            justify="left",
        )
        self.sugg_banner.grid(row=1, column=0, padx=12, pady=(0, 4), sticky="w")

        # ── Item list ────────────────────────────────────────────────────
        list_frame = ctk.CTkScrollableFrame(body, fg_color="transparent")
        list_frame.grid(row=2, column=0, padx=6, pady=(0, 6), sticky="nsew")
        list_frame.grid_columnconfigure(0, weight=1)
        self._sugg_list_frame = list_frame
        self._sugg_item_widgets: list[dict] = []

        self.reload_suggestions()

    def reload_suggestions(self):
        queue = load_queue()
        enabled = [i for i in queue.items if i.enabled]
        disabled = [i for i in queue.items if not i.enabled]

        count_text = t("suggestions.count", count=len(enabled), default=f"待处理建议 {len(enabled)} 条")
        if disabled:
            count_text += f"  ({len(disabled)} 已禁用)"
        self.sugg_count_var.set(count_text)

        since = queue.accumulated_since
        self.sugg_since_var.set(t("suggestions.since", since=since, default=f"累积自 {since}") if since else "")

        # Clear and rebuild item widgets
        for w in self._sugg_list_frame.winfo_children():
            w.destroy()
        self._sugg_item_widgets.clear()

        if not queue.items:
            self._render_suggestions_guide()
            self.sugg_banner_var.set("")
            return

        # Group by source
        by_source: dict[str, list[SuggestionItem]] = {}
        for item in queue.items:
            by_source.setdefault(item.source_id, []).append(item)

        row_idx = 0
        for source_id, items in by_source.items():
            # Source header
            hdr = ctk.CTkFrame(self._sugg_list_frame, fg_color=COL_ACCENT_SOFT, corner_radius=10)
            hdr.grid(row=row_idx, column=0, padx=4, pady=(12, 4), sticky="ew")
            enabled_in_src = sum(1 for i in items if i.enabled)
            ctk.CTkLabel(
                hdr,
                text=f"  {source_id}  ({enabled_in_src}/{len(items)})",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COL_ACCENT,
            ).pack(side="left", padx=12, pady=8)
            row_idx += 1

            for item in items:
                row_idx = self._add_suggestion_row(item, row_idx, queue)

        # Save queue after any enable changes from previous reload
        self.sugg_banner_var.set(
            t("suggestions.tip", default="提示：修改分类后点击「确认并执行」才会实际移动文件")
        )

    def _render_suggestions_guide(self):
        """Show a visual how-to-use guide when the queue is empty."""
        outer = ctk.CTkFrame(self._sugg_list_frame, fg_color="transparent")
        outer.pack(fill="x", padx=20, pady=40)

        # Title card
        card = ctk.CTkFrame(outer, fg_color=COL_CARD, corner_radius=16)
        card.pack(fill="x", padx=0, pady=0)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=t("suggestions.guide_title", default="如何使用建议队列"),
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COL_TEXT,
        ).pack(anchor="w", padx=22, pady=(20, 6))

        steps = [
            ("① ", t("suggestions.guide_step1", default="在「设置 → 整理来源管理」中开启「建议模式」"), COL_ACCENT),
            ("② ", t("suggestions.guide_step2", default="在「整理桌面」运行扫描 — AI 分类结果会累积到这里，不会立即移动文件"), COL_ACCENT),
            ("③ ", t("suggestions.guide_step3", default="在此页面检查、调整分类，确认后点「确认并执行」"), COL_OK),
        ]
        for icon, text_str, color in steps:
            row_frame = ctk.CTkFrame(card, fg_color="transparent")
            row_frame.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(row_frame, text=icon, font=ctk.CTkFont(size=18, weight="bold"), text_color=color, width=28).pack(side="left", padx=(6, 0))
            ctk.CTkLabel(row_frame, text=text_str, font=ctk.CTkFont(size=13), text_color=COL_TEXT, justify="left", wraplength=560).pack(side="left", padx=(6, 0), pady=4)

        ctk.CTkButton(
            card,
            text=t("suggestions.go_settings", default="前往设置"),
            width=120, height=34, corner_radius=8,
            fg_color=COL_ACCENT, hover_color="#1d4ed8",
            command=lambda: self.show_page("Settings"),
        ).pack(anchor="w", padx=22, pady=(10, 20))

    def _add_suggestion_row(self, item: SuggestionItem, row: int, queue) -> int:
        card = ctk.CTkFrame(self._sugg_list_frame, fg_color=COL_CARD, corner_radius=10)
        card.grid(row=row, column=0, padx=4, pady=3, sticky="ew")
        card.grid_columnconfigure(2, weight=1)

        # Enable checkbox
        enabled_var = tk.BooleanVar(value=item.enabled)

        def _toggle(iv=enabled_var, it=item):
            it.enabled = iv.get()
            save_queue(queue)
            self._refresh_count()

        chk = ctk.CTkCheckBox(card, text="", variable=enabled_var, width=24, command=_toggle)
        chk.grid(row=0, column=0, padx=(12, 4), pady=8)

        # File name
        ctk.CTkLabel(
            card,
            text=item.name,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COL_TEXT,
            anchor="w",
        ).grid(row=0, column=1, padx=(4, 8), pady=8, sticky="w")

        # Reason
        reason_label = item.reason[:80] + "…" if len(item.reason) > 80 else item.reason
        ctk.CTkLabel(
            card,
            text=reason_label,
            font=ctk.CTkFont(size=11),
            text_color=COL_TEXT_MUTED,
            anchor="w",
            wraplength=400,
            justify="left",
        ).grid(row=0, column=2, padx=4, pady=8, sticky="w")

        # Confidence chip
        conf_color = {"high": COL_OK, "medium": COL_WARN, "low": "#9ca3af"}.get(item.confidence, COL_TEXT_MUTED)
        ctk.CTkLabel(
            card,
            text=item.confidence,
            font=ctk.CTkFont(size=11),
            text_color=conf_color,
            width=50,
        ).grid(row=0, column=3, padx=8, pady=8)

        # Category dropdown
        all_cats = get_category_display_options()
        current_cat = item.human_category or item.suggested_category
        current_display = get_category_display(current_cat)
        cat_var = tk.StringVar(value=current_display)

        from desktop_agent.i18n import get_display_to_category_map

        def _on_cat_change(choice, it=item, cv=cat_var):
            mapping = get_display_to_category_map()
            it.human_category = mapping.get(choice, choice)
            save_queue(queue)

        opt = ctk.CTkOptionMenu(
            card,
            variable=cat_var,
            values=all_cats,
            width=160,
            command=_on_cat_change,
        )
        opt.grid(row=0, column=4, padx=(4, 12), pady=8)

        return row + 1

    def _refresh_count(self):
        count = sum(1 for w in self._sugg_list_frame.winfo_children() if isinstance(w, ctk.CTkFrame))
        self.sugg_count_var.set(t("suggestions.count", count=get_pending_count(), default=f"待处理建议 {get_pending_count()} 条"))

    def validate_and_reload(self):
        validate_queue()
        self.reload_suggestions()
        messagebox.showinfo(
            t("suggestions.validate_done_title", default="路径验证完成"),
            t("suggestions.validate_done_msg", default="已移除路径不存在的建议项"),
        )

    def clear_suggestion_queue(self):
        if not messagebox.askyesno(
            t("suggestions.clear_confirm_title", default="确认清空"),
            t("suggestions.clear_confirm_msg", default="确认清空建议队列？此操作不可撤销。"),
        ):
            return
        clear_queue()
        self.reload_suggestions()

    def execute_all_suggestions(self):
        count = get_pending_count()
        if count == 0:
            messagebox.showinfo(
                t("suggestions.no_items_title", default="队列为空"),
                t("suggestions.no_items_msg", default="没有待处理的建议项"),
            )
            return

        if not messagebox.askyesno(
            t("suggestions.execute_confirm_title", default="确认执行"),
            t("suggestions.execute_confirm_msg", count=count, default=f"确认执行 {count} 条建议？文件将被移动/复制。"),
        ):
            return

        if self.running:
            messagebox.showwarning(t("workflow.already_running_title"), t("workflow.already_running_message"))
            return

        self.running = True
        self.show_page("Logs")
        self.status_var.set(t("suggestions.executing", default="执行建议中…"))

        thread = threading.Thread(target=self._worker_execute_suggestions, daemon=True)
        thread.start()

    def _worker_execute_suggestions(self):
        from desktop_agent.workflow import confirm_suggestions

        try:
            writer = QueueWriter(self.output_queue)
            with redirect_stdout(writer), redirect_stderr(writer):
                confirm_suggestions(learn=True)
            self.output_queue.put("\n[Process finished with code 0]\n")
        except Exception as exc:
            self.output_queue.put(f"\n[GUI Error] {exc}\n")
            self.output_queue.put("\n[Process finished with code 1]\n")
        finally:
            self.output_queue.put("__TASK_DONE__")
