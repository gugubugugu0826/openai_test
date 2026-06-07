import json
import os
import re
import tkinter as tk
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from desktop_agent.i18n import get_category_display, t
from desktop_agent.plan_explainer import explain_current_plan
from desktop_agent_ui.theme import *


EXPLANATION_MD_FILE = Path("desktop_agent_explanation.md")
EXPLANATION_JSON_FILE = Path("desktop_agent_explanation.json")


class QueueWriter:
    def __init__(self, output_queue):
        self.output_queue = output_queue

    def write(self, text):
        if text:
            self.output_queue.put(text)

    def flush(self):
        pass


class ExplanationPageMixin:
    def build_explanation_page(self, parent):
        self.page_header(parent, t("explain.page_title"), t("explain.page_subtitle"))

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        toolbar = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        toolbar.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(toolbar, text=t("explain.generate"), corner_radius=8, command=self.generate_plan_explanation_gui).pack(side="left", padx=(12, 8), pady=12)
        ctk.CTkButton(toolbar, text=t("explain.open_file"), corner_radius=8, command=self.open_plan_explanation_file).pack(side="left", padx=8, pady=12)

        self.explanation_status_var = tk.StringVar(value=t("explain.empty_status"))
        self.explanation_meta_var = tk.StringVar(value=t("explain.empty_meta"))

        overview = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        overview.grid(row=1, column=0, padx=6, pady=(8, 6), sticky="ew")
        overview.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(overview, text=t("explain.overview_title"), font=("Microsoft YaHei UI", 15, "bold"), text_color=COL_TEXT).grid(row=0, column=0, padx=18, pady=(14, 2), sticky="w")
        ctk.CTkLabel(overview, textvariable=self.explanation_status_var, font=("Microsoft YaHei UI", 12), text_color=COL_TEXT, wraplength=940, justify="left").grid(row=1, column=0, padx=18, pady=(0, 4), sticky="w")
        ctk.CTkLabel(overview, textvariable=self.explanation_meta_var, font=("Microsoft YaHei UI", 11), text_color=COL_TEXT_MUTED, wraplength=940, justify="left").grid(row=2, column=0, padx=18, pady=(0, 14), sticky="w")

        self.explanation_content = ctk.CTkScrollableFrame(body, corner_radius=14, fg_color=COL_CARD)
        self.explanation_content.grid(row=2, column=0, padx=6, pady=8, sticky="nsew")
        self.explanation_content.grid_columnconfigure(0, weight=1)

    def load_plan_explanation_panel(self):
        if not hasattr(self, "explanation_content"):
            return

        self._clear_explanation_content()

        if EXPLANATION_JSON_FILE.exists():
            try:
                with open(EXPLANATION_JSON_FILE, "r", encoding="utf-8") as f:
                    explanation = json.load(f)
                self._render_explanation_data(explanation)
                return
            except Exception as exc:
                self.explanation_status_var.set(t("explain.load_failed_title"))
                self.explanation_meta_var.set(str(exc))

        if EXPLANATION_MD_FILE.exists():
            try:
                content = EXPLANATION_MD_FILE.read_text(encoding="utf-8")
                self.explanation_status_var.set(t("explain.loaded_title"))
                self.explanation_meta_var.set(t("explain.loaded_meta"))
                self._render_markdown_fallback(self._cleanup_markdown_for_display(content))
            except Exception as exc:
                self.explanation_status_var.set(t("explain.load_failed_title"))
                self.explanation_meta_var.set(str(exc))
                self._render_markdown_fallback(t("explain.read_failed_body", message=str(exc)))
        else:
            self.explanation_status_var.set(t("explain.empty_status"))
            self.explanation_meta_var.set(t("explain.empty_meta"))
            self._render_empty_state()

    def _render_explanation_data(self, explanation):
        summary = explanation.get("summary", "").strip() or t("explain.no_summary")
        self.explanation_status_var.set(summary)
        self.explanation_meta_var.set(
            t(
                "explain.meta_line",
                created_at=explanation.get("created_at", t("common.unknown")),
                source=explanation.get("source_file", t("common.unknown")),
                provider=explanation.get("provider", t("common.unknown")),
                target_root=explanation.get("target_root", t("common.not_set")),
                folder_mode=explanation.get("folder_mode", t("common.unknown")),
            )
        )

        warning_items = explanation.get("warning_items", []) or []
        recommendations = explanation.get("recommendations", []) or []

        row = 0
        self._build_metric_strip(
            row,
            [
                (t("explain.total"), explanation.get("total_items", 0), COL_ACCENT, COL_ACCENT_SOFT),
                (t("explain.enabled"), explanation.get("enabled_items", 0), COL_OK, COL_OK_SOFT),
                (t("explain.skipped"), explanation.get("disabled_items", 0), COL_WARN_TEXT, COL_WARN_SOFT),
                (t("explain.needs_review"), len(warning_items), COL_DANGER, "#fef2f2"),
            ],
        )
        row += 1
        self._build_text_card(t("explain.summary_title"), summary, row)
        row += 1
        self._build_kv_grid_card(
            t("explain.basics_title"),
            [
                (t("explain.created_at"), explanation.get("created_at", t("common.unknown"))),
                (t("explain.source"), explanation.get("source_file", t("common.unknown"))),
                (t("explain.provider"), explanation.get("provider", t("common.unknown"))),
                (t("explain.target_root"), explanation.get("target_root", t("common.not_set"))),
                (t("explain.folder_mode"), explanation.get("folder_mode", t("common.unknown"))),
            ],
            row,
        )
        row += 1
        self._build_two_column_stats(
            row,
            (t("explain.type_stats_title"), explanation.get("type_counts", {}), False),
            (t("explain.source_stats_title"), explanation.get("classified_by_counts", {}), False),
        )
        row += 1
        self._build_ranked_list_card(t("explain.category_stats_title"), explanation.get("category_counts", {}), row, sort_desc=True)
        row += 1
        self._build_warning_card(t("explain.warning_title"), warning_items, row)
        row += 1
        self._build_recommendation_card(t("explain.recommendations_title"), recommendations, row)

    def _clear_explanation_content(self):
        for child in self.explanation_content.winfo_children():
            child.destroy()

    def _make_section_card(self, row, title, subtitle=None):
        card = ctk.CTkFrame(self.explanation_content, fg_color=COL_CARD, corner_radius=12)
        card.grid(row=row, column=0, padx=12, pady=(0, 12), sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, font=("Microsoft YaHei UI", 15, "bold"), text_color=COL_TEXT).grid(row=0, column=0, padx=18, pady=(16, 4), sticky="w")
        start_row = 1
        if subtitle:
            ctk.CTkLabel(card, text=subtitle, font=("Microsoft YaHei UI", 11), text_color=COL_TEXT_MUTED, wraplength=980, justify="left").grid(row=1, column=0, padx=18, pady=(0, 10), sticky="w")
            start_row = 2
        return card, start_row

    def _build_metric_strip(self, row, metrics):
        card, start_row = self._make_section_card(row, t("explain.overview_card_title"), t("explain.overview_card_subtitle"))
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.grid(row=start_row, column=0, padx=18, pady=(0, 16), sticky="ew")
        for idx in range(len(metrics)):
            grid.grid_columnconfigure(idx, weight=1)
        for idx, (label, value, color, bg) in enumerate(metrics):
            item = ctk.CTkFrame(grid, fg_color=bg, corner_radius=12)
            item.grid(row=0, column=idx, padx=(0 if idx == 0 else 8, 0), sticky="ew")
            ctk.CTkLabel(item, text=label, font=("Microsoft YaHei UI", 11), text_color=color).pack(anchor="w", padx=14, pady=(12, 2))
            ctk.CTkLabel(item, text=str(value), font=("Microsoft YaHei UI", 24, "bold"), text_color=COL_TEXT).pack(anchor="w", padx=14, pady=(0, 12))

    def _build_text_card(self, title, text, row):
        card, start_row = self._make_section_card(row, title)
        ctk.CTkLabel(card, text=text, font=("Microsoft YaHei UI", 12), text_color=COL_TEXT, wraplength=980, justify="left").grid(row=start_row, column=0, padx=18, pady=(0, 16), sticky="w")

    def _build_kv_grid_card(self, title, pairs, row):
        card, start_row = self._make_section_card(row, title)
        grid = ctk.CTkFrame(card, fg_color=COL_BG, corner_radius=12)
        grid.grid(row=start_row, column=0, padx=18, pady=(0, 16), sticky="ew")
        grid.grid_columnconfigure((0, 1), weight=1)
        for idx, (label, value) in enumerate(pairs):
            r = idx // 2
            c = idx % 2
            item = ctk.CTkFrame(grid, fg_color="transparent")
            item.grid(row=r, column=c, padx=12, pady=10, sticky="ew")
            ctk.CTkLabel(item, text=label, font=("Microsoft YaHei UI", 10), text_color=COL_TEXT_MUTED).pack(anchor="w")
            ctk.CTkLabel(item, text=str(value), font=("Microsoft YaHei UI", 12, "bold"), text_color=COL_TEXT, wraplength=430, justify="left").pack(anchor="w", pady=(2, 0))

    def _build_two_column_stats(self, row, left_spec, right_spec):
        card, start_row = self._make_section_card(row, t("explain.statistics_title"), t("explain.statistics_subtitle"))
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.grid(row=start_row, column=0, padx=18, pady=(0, 16), sticky="ew")
        grid.grid_columnconfigure((0, 1), weight=1)
        self._build_stats_panel(grid, left_spec[0], left_spec[1], 0, 0, sort_desc=left_spec[2])
        self._build_stats_panel(grid, right_spec[0], right_spec[1], 0, 1, sort_desc=right_spec[2])

    def _build_stats_panel(self, parent, title, stats, row, column, sort_desc=False):
        panel = ctk.CTkFrame(parent, fg_color=COL_BG, corner_radius=12)
        panel.grid(row=row, column=column, padx=(0, 8) if column == 0 else (8, 0), sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(panel, text=title, font=("Microsoft YaHei UI", 13, "bold"), text_color=COL_TEXT).grid(row=0, column=0, padx=14, pady=(14, 8), sticky="w")

        items = list((stats or {}).items())
        if sort_desc:
            items.sort(key=lambda item: item[1], reverse=True)
        if not items:
            ctk.CTkLabel(panel, text=t("common.no_data"), font=("Microsoft YaHei UI", 11), text_color=COL_TEXT_MUTED).grid(row=1, column=0, padx=14, pady=(0, 14), sticky="w")
            return

        for idx, (key, value) in enumerate(items, start=1):
            line = ctk.CTkFrame(panel, fg_color="transparent")
            line.grid(row=idx, column=0, padx=14, pady=4, sticky="ew")
            line.grid_columnconfigure(0, weight=1)
            display_key = get_category_display(str(key))
            ctk.CTkLabel(line, text=display_key, font=("Microsoft YaHei UI", 11), text_color=COL_TEXT).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(line, text=str(value), font=("Microsoft YaHei UI", 11, "bold"), text_color=COL_TEXT).grid(row=0, column=1, sticky="e")

    def _build_ranked_list_card(self, title, stats, row, sort_desc=False):
        card, start_row = self._make_section_card(row, title)
        items = list((stats or {}).items())
        if sort_desc:
            items.sort(key=lambda item: item[1], reverse=True)
        if not items:
            ctk.CTkLabel(card, text=t("common.no_data"), font=("Microsoft YaHei UI", 11), text_color=COL_TEXT_MUTED).grid(row=start_row, column=0, padx=18, pady=(0, 16), sticky="w")
            return

        body = ctk.CTkFrame(card, fg_color=COL_BG, corner_radius=12)
        body.grid(row=start_row, column=0, padx=18, pady=(0, 16), sticky="ew")
        body.grid_columnconfigure(1, weight=1)

        top_value = max(value for _, value in items) if items else 1
        for idx, (key, value) in enumerate(items):
            ctk.CTkLabel(body, text=f"{idx + 1}", width=28, font=("Microsoft YaHei UI", 11, "bold"), text_color=COL_TEXT_MUTED).grid(row=idx, column=0, padx=(14, 8), pady=8, sticky="w")
            row_frame = ctk.CTkFrame(body, fg_color="transparent")
            row_frame.grid(row=idx, column=1, padx=(0, 14), pady=8, sticky="ew")
            row_frame.grid_columnconfigure(1, weight=1)
            display_key = get_category_display(str(key))
            ctk.CTkLabel(row_frame, text=display_key, font=("Microsoft YaHei UI", 11), text_color=COL_TEXT).grid(row=0, column=0, sticky="w")
            bar_bg = ctk.CTkFrame(row_frame, fg_color="#e5eefc", corner_radius=6, height=12)
            bar_bg.grid(row=1, column=0, columnspan=2, pady=(6, 0), sticky="ew")
            bar_bg.grid_columnconfigure(0, weight=max(int(value), 1))
            bar_bg.grid_columnconfigure(1, weight=max(int(top_value - value), 0))
            ctk.CTkFrame(bar_bg, fg_color=COL_ACCENT, corner_radius=6, height=12).grid(row=0, column=0, sticky="ew")
            ctk.CTkLabel(row_frame, text=str(value), font=("Microsoft YaHei UI", 11, "bold"), text_color=COL_TEXT).grid(row=0, column=1, sticky="e", padx=(10, 0))

    def _build_warning_card(self, title, items, row):
        card, start_row = self._make_section_card(row, title, t("explain.warning_subtitle"))
        if not items:
            ctk.CTkLabel(card, text=t("explain.warning_empty"), font=("Microsoft YaHei UI", 11), text_color=COL_TEXT_MUTED).grid(row=start_row, column=0, padx=18, pady=(0, 16), sticky="w")
            return

        list_box = ctk.CTkFrame(card, fg_color=COL_BG, corner_radius=12)
        list_box.grid(row=start_row, column=0, padx=18, pady=(0, 16), sticky="ew")
        list_box.grid_columnconfigure(0, weight=1)

        for idx, item in enumerate(items[:12]):
            entry = ctk.CTkFrame(list_box, fg_color="#ffffff" if idx % 2 == 0 else "#f8fafc", corner_radius=10)
            entry.grid(row=idx, column=0, padx=10, pady=6, sticky="ew")
            entry.grid_columnconfigure(0, weight=1)
            item_name = item.get("name") or item.get("path") or t("common.unnamed_item")
            category = get_category_display(item.get("category") or "无法判断")
            reason = item.get("reason") or t("explain.manual_review_recommended")
            ctk.CTkLabel(entry, text=item_name, font=("Microsoft YaHei UI", 11, "bold"), text_color=COL_TEXT, anchor="w").grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")
            ctk.CTkLabel(entry, text=t("explain.current_category_line", category=category), font=("Microsoft YaHei UI", 10), text_color=COL_TEXT_MUTED, anchor="w").grid(row=1, column=0, padx=12, sticky="w")
            ctk.CTkLabel(entry, text=t("explain.reason_line", reason=reason), font=("Microsoft YaHei UI", 10), text_color="#b45309", anchor="w", wraplength=920, justify="left").grid(row=2, column=0, padx=12, pady=(2, 10), sticky="w")

    def _build_recommendation_card(self, title, recommendations, row):
        card, start_row = self._make_section_card(row, title)
        items = recommendations or [t("explain.no_recommendations")]
        box = ctk.CTkFrame(card, fg_color=COL_OK_SOFT, corner_radius=12)
        box.grid(row=start_row, column=0, padx=18, pady=(0, 16), sticky="ew")
        for idx, rec in enumerate(items):
            ctk.CTkLabel(box, text=f"{idx + 1}. {rec}", font=("Microsoft YaHei UI", 11), text_color=COL_TEXT, wraplength=960, justify="left").grid(row=idx, column=0, padx=14, pady=(12 if idx == 0 else 4, 12 if idx == len(items) - 1 else 0), sticky="w")

    def _render_markdown_fallback(self, content):
        self._build_text_card(t("explain.fallback_title"), content, 0)

    def _render_empty_state(self):
        self._build_text_card(t("explain.no_explanation_title"), t("explain.no_explanation_body"), 0)

    def _cleanup_markdown_for_display(self, content):
        cleaned_lines = []
        for line in content.splitlines():
            line = re.sub(r"^\s*#{1,6}\s*", "", line)
            line = re.sub(r"^\s*[-*]\s*", "- ", line)
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def generate_plan_explanation_gui(self):
        try:
            writer = QueueWriter(self.output_queue)
            with redirect_stdout(writer), redirect_stderr(writer):
                explain_current_plan()
            self.load_plan_explanation_panel()
            self.show_page("Explanation")
        except Exception as exc:
            messagebox.showerror(t("explain.generate_failed_title"), str(exc))

    def open_plan_explanation_file(self):
        if not EXPLANATION_MD_FILE.exists():
            messagebox.showwarning(t("explain.no_file_title"), t("explain.no_file_message"))
            return
        try:
            os.startfile(str(EXPLANATION_MD_FILE))
        except Exception as exc:
            messagebox.showerror(t("explain.open_failed_title"), str(exc))
