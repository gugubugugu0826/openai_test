import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from desktop_agent.categories import CATEGORIES
from desktop_agent.i18n import get_category_display, get_language, t
from desktop_agent_ui.theme import *

REVIEW_FILE = Path("desktop_human_review.json")

# Column widths in px for the review table.  None = expand to fill remaining space.
_RCOLS = (46, 88, 240, 86, 182, None)


class ReviewPageMixin:
    def build_review_page(self, parent):
        self.page_header(
            parent,
            "整理方案",
            "逐项确认是否整理、目标分类是否正确；修改后记得保存。",
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(3, weight=1)

        hint = ctk.CTkFrame(body, fg_color=COL_ACCENT_SOFT, corner_radius=12)
        hint.grid(row=0, column=0, padx=6, pady=(0, 8), sticky="ew")
        ctk.CTkLabel(
            hint,
            text="启用 = 会整理；关闭 = 跳过。你可以直接修改分类，也可以勾选多项后批量改分类。",
            font=ctk.CTkFont(size=12), text_color=COL_ACCENT,
        ).pack(anchor="w", padx=14, pady=10)

        toolbar = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        toolbar.grid(row=1, column=0, padx=6, pady=6, sticky="ew")

        def _sep():
            ctk.CTkLabel(toolbar, text="│", text_color=COL_BORDER,
                         width=4, font=ctk.CTkFont(size=18)).pack(side="left", padx=4, pady=10)

        # 组1：加载 / 保存
        ctk.CTkButton(toolbar, text="加载", corner_radius=8,
                      fg_color="transparent", border_width=1, border_color=COL_BORDER,
                      text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
                      command=self.load_review_table).pack(side="left", padx=(10, 4), pady=12)
        ctk.CTkButton(toolbar, text="保存", corner_radius=8,
                      fg_color=COL_OK, hover_color="#059669",
                      command=self.save_review_table).pack(side="left", padx=4, pady=12)

        _sep()

        # 组2：批量启用 / 禁用
        ctk.CTkButton(toolbar, text="全部启用", corner_radius=8,
                      fg_color="transparent", border_width=1, border_color=COL_BORDER,
                      text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
                      command=self.enable_all_review_items).pack(side="left", padx=4, pady=12)
        ctk.CTkButton(toolbar, text="全部禁用", corner_radius=8,
                      fg_color="#6b7280", hover_color="#4b5563",
                      command=self.disable_all_review_items).pack(side="left", padx=4, pady=12)

        _sep()

        # 组3：勾选操作
        ctk.CTkButton(toolbar, text="全选 / 取消", corner_radius=8,
                      fg_color="transparent", border_width=1, border_color=COL_BORDER,
                      text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
                      command=self.check_all_review_items).pack(side="left", padx=4, pady=12)
        ctk.CTkButton(toolbar, text="批量改分类", corner_radius=8,
                      fg_color=COL_ACCENT, hover_color="#1d4ed8",
                      command=self.change_selected_category).pack(side="left", padx=4, pady=12)

        # 过滤栏 — 独立一行，避免挤入工具栏溢出
        filter_bar = ctk.CTkFrame(body, fg_color="transparent")
        filter_bar.grid(row=2, column=0, padx=6, pady=(2, 0), sticky="ew")

        self.review_count_var = tk.StringVar(value="未加载")
        ctk.CTkLabel(filter_bar, textvariable=self.review_count_var,
                     text_color=COL_TEXT_MUTED, font=ctk.CTkFont(size=12)
                     ).pack(side="right", padx=(4, 2))

        self.review_filter_menu = ctk.CTkOptionMenu(
            filter_bar,
            values=self.get_category_display_options(include_all=True),
            variable=self.review_filter_var,
            command=lambda _: self.refresh_review_table(),
            width=210,
        )
        self.review_filter_menu.pack(side="right", padx=(0, 6))

        ctk.CTkLabel(filter_bar, text="过滤分类：",
                     text_color=COL_TEXT_MUTED, font=ctk.CTkFont(size=12)
                     ).pack(side="right", padx=(0, 2))

        self.review_list = ctk.CTkScrollableFrame(body, fg_color="transparent")
        self.review_list.grid(row=3, column=0, padx=6, pady=(4, 8), sticky="nsew")
        self.review_list.grid_columnconfigure(0, weight=1)

        self.review_check_vars = {}

    def _rv_cell(self, parent, width):
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        if width is None:
            cell.pack(side="left", fill="both", expand=True)
        else:
            cell.configure(width=width)
            cell.pack(side="left", fill="y")
            cell.pack_propagate(False)
        return cell

    def _type_pill_style(self, item_type):
        if item_type == "folder":
            return "#ecfdf5", "#047857"
        if item_type == "shortcut":
            return "#fef3c7", "#92400e"
        return "#eff6ff", "#1d4ed8"

    def _make_review_row(self, index, grid_row, item, zebra):
        enabled = bool(item.get("enabled", True))
        base_bg = "#f8fafc" if zebra else COL_CARD

        row = ctk.CTkFrame(self.review_list, fg_color=base_bg, corner_radius=6, height=44)
        row.grid(row=grid_row, column=0, pady=2, sticky="ew")
        row.pack_propagate(False)

        name_color = COL_TEXT if enabled else "#9ca3af"
        muted_color = COL_TEXT_MUTED if enabled else "#cbd5e1"

        # 选 — checkbox
        c0 = self._rv_cell(row, _RCOLS[0])
        cvar = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            c0, text="", variable=cvar, width=24,
            command=self._update_review_count,
        ).pack(anchor="center", expand=True)
        self.review_check_vars[index] = cvar

        # 启用 — toggle switch
        c1 = self._rv_cell(row, _RCOLS[1])
        evar = tk.BooleanVar(value=enabled)
        def on_toggle(i=index):
            en = bool(evar.get())
            self.review_items[i]["enabled"] = en
            self.review_dirty = True
            self.refresh_review_table()
        ctk.CTkSwitch(c1, text="", variable=evar, command=on_toggle).pack(anchor="center", padx=6, expand=True)

        # 名称 — name label
        c2 = self._rv_cell(row, _RCOLS[2])
        ctk.CTkLabel(
            c2, text=item.get("name", ""), text_color=name_color, anchor="w",
        ).pack(anchor="center", fill="x", padx=8, expand=True)

        # 类型 — type pill
        c3 = self._rv_cell(row, _RCOLS[3])
        pill_bg, pill_fg = self._type_pill_style(item.get("type", ""))
        ctk.CTkLabel(
            c3, text=item.get("type", ""), fg_color=pill_bg,
            text_color=pill_fg, corner_radius=6, width=66,
        ).pack(anchor="center", expand=True)

        # 分类 — category dropdown
        c4 = self._rv_cell(row, _RCOLS[4])
        initial_category = item.get("human_category", item.get("category", "")) or CATEGORIES[0]
        hvar = tk.StringVar(value=self.category_to_display(initial_category))
        def on_cat(choice, i=index):
            self.review_items[i]["human_category"] = self.display_to_category(choice)
            self.review_dirty = True
            self._update_review_count()
        ctk.CTkOptionMenu(
            c4, values=self.get_category_display_options(), variable=hvar, command=on_cat, width=198,
        ).pack(anchor="center", padx=6, expand=True)

        # 原因 — horizontally scrollable; mouse-wheel scrolls text, not the parent frame
        c5 = self._rv_cell(row, _RCOLS[5])
        rtxt = tk.Text(
            c5, height=1, wrap="none", bd=0, relief="flat",
            bg=base_bg, fg=muted_color,
            font=("Segoe UI", 11), cursor="arrow",
            selectbackground=base_bg, selectforeground=muted_color,
            highlightthickness=0, padx=8, pady=12,
        )
        rtxt.insert("1.0", item.get("reason", ""))
        rtxt.configure(state="disabled")
        rtxt.bind("<MouseWheel>", lambda e, t=rtxt: t.xview_scroll(-1 * (e.delta // 120), "units") or "break")
        rtxt.pack(fill="both", expand=True)

    def load_review_table(self):
        if not REVIEW_FILE.exists():
            messagebox.showwarning("没有整理方案", "请先扫描并生成整理方案。")
            return

        try:
            with open(REVIEW_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("加载失败", str(e))
            return

        self.review_items = data.get("items", [])
        self.review_filter_var.set(t("全部"))
        self.review_dirty = False
        self.refresh_review_table()

        self.append_output(f"\n[GUI] 已加载整理方案：{len(self.review_items)} 项\n")

    def refresh_review_table(self):
        if not hasattr(self, "review_list"):
            return

        for w in self.review_list.winfo_children():
            w.destroy()
        self.review_check_vars = {}

        hdr = ctk.CTkFrame(self.review_list, fg_color=COL_HOVER, corner_radius=0, height=34)
        hdr.grid(row=0, column=0, pady=(0, 2), sticky="ew")
        hdr.pack_propagate(False)
        for width, text in zip(_RCOLS, [
            "",
            self._lang("启用", "Enabled"),
            self._lang("名称", "Name"),
            self._lang("类型", "Type"),
            self._lang("分类", "Category"),
            self._lang("原因", "Reason"),
        ]):
            cell = self._rv_cell(hdr, width)
            ctk.CTkLabel(
                cell, text=text, font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COL_TEXT_NAV, anchor="w",
            ).pack(anchor="center", fill="x", padx=8, expand=True)

        current_filter = self.display_to_category(self.review_filter_var.get())
        visible = 0

        for index, item in enumerate(self.review_items):
            category = item.get("human_category") or item.get("ai_category") or item.get("category")
            if current_filter != "全部" and category != current_filter:
                continue
            self._make_review_row(index, visible + 1, item, visible % 2 == 1)
            visible += 1

        if visible == 0:
            ctk.CTkLabel(
                self.review_list,
                text="没有可显示的项目",
                text_color=COL_TEXT_MUTED,
            ).grid(row=1, column=0, pady=40)

        self._update_review_count()

    def _update_review_count(self):
        total = len(self.review_items)
        enabled = sum(1 for it in self.review_items if it.get("enabled", True))
        checked = sum(1 for v in self.review_check_vars.values() if v.get())
        if t("全部") != "全部":
            self.review_count_var.set(f"Total {total} items · {enabled} enabled · {checked} selected")
        else:
            self.review_count_var.set(f"共 {total} 项 · 启用 {enabled} · 勾选 {checked}")

    def save_review_table(self, silent=False):
        if not self.review_items:
            return False

        try:
            with open(REVIEW_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            data["items"] = self.review_items

            with open(REVIEW_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.review_dirty = False
            if not silent:
                messagebox.showinfo("已保存", "整理方案已保存。")
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
            messagebox.showwarning("没有勾选项目", "请先勾选要批量修改的项目。")
            return

        editor = ctk.CTkToplevel(self.root)
        editor.title(self._lang("批量修改分类", "Bulk Change Category"))
        editor.geometry("360x180")
        editor.transient(self.root)
        editor.grab_set()

        category_var = tk.StringVar(value=self.category_to_display(CATEGORIES[0]))
        ctk.CTkLabel(
            editor,
            text=self._lang(f"将 {len(indices)} 个项目改为：", f"Change {len(indices)} items to:"),
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(pady=(24, 10))
        ctk.CTkOptionMenu(editor, variable=category_var, values=self.get_category_display_options(), width=280).pack(pady=8)

        def apply_category():
            new_category = self.display_to_category(category_var.get())
            for index in indices:
                if 0 <= index < len(self.review_items):
                    self.review_items[index]["human_category"] = new_category
            self.review_dirty = True
            self.refresh_review_table()
            editor.grab_release()
            # Delay destroy by 50 ms so CTkToplevel's titlebar-color after(10) callback
            # fires first; otherwise Tkinter raises "bad window path name" on Windows.
            editor.after(50, editor.destroy)

        ctk.CTkButton(editor, text="应用", command=apply_category).pack(pady=14)
