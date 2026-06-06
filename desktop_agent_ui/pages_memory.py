import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

from desktop_agent_ui.theme import *

MEMORY_FILE = Path("agent_memory.json")
CATEGORIES = [
    "课程资料", "代码项目", "作业报告", "简历求职", "证件合同", "图片截图", "视频音频", "压缩包", "安装包",
    "游戏相关", "临时文件", "浏览器通讯", "办公学习", "系统工具", "影音娱乐", "网盘VPN", "其他快捷方式", "无法判断",
]

DEFAULT_MEMORY = {
    "rules": [
        {"match": "简历", "category": "简历求职", "note": "示例规则：文件名含“简历”"},
        {"match": "发票", "category": "证件合同", "note": "示例规则：含“发票”"},
    ]
}


class MemoryPageMixin:
    def build_memory_page(self, parent):
        self.page_header(
            parent,
            "整理记忆",
            "管理整理规则：文件名 / 路径命中关键词时，自动归到指定分类。无需手写 JSON。",
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        tip_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        tip_card.grid(row=0, column=0, padx=6, pady=(6, 8), sticky="ew")
        tip_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            tip_card,
            text="规则会优先于 AI 分类",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color=COL_TEXT,
        ).grid(row=0, column=0, padx=18, pady=(14, 2), sticky="w")
        ctk.CTkLabel(
            tip_card,
            text="建议只添加稳定、明确的关键词，例如“简历”“发票”“课程”。双击表格中的规则可以直接编辑。",
            font=("Microsoft YaHei UI", 11),
            text_color=COL_TEXT_MUTED,
            wraplength=980,
            justify="left",
        ).grid(row=1, column=0, padx=18, pady=(0, 14), sticky="w")

        toolbar = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        toolbar.grid(row=1, column=0, padx=6, pady=6, sticky="ew")
        toolbar.grid_columnconfigure(0, weight=1)

        actions = ctk.CTkFrame(toolbar, fg_color="transparent")
        actions.grid(row=0, column=0, padx=12, pady=12, sticky="w")

        buttons = [
            ("添加规则", None, self.add_memory_rule_dialog),
            ("编辑选中", None, self.edit_selected_memory_rule),
            ("删除选中", COL_DANGER, self.delete_selected_memory_rules),
            ("保存", COL_OK, self.save_memory_panel),
            ("重新加载", "#6b7280", self.load_memory_panel),
        ]
        for idx, (text, color, command) in enumerate(buttons):
            kwargs = {"text": text, "corner_radius": 8, "width": 132, "command": command}
            if color == COL_DANGER:
                kwargs["fg_color"] = COL_DANGER
                kwargs["hover_color"] = "#b91c1c"
            elif color == COL_OK:
                kwargs["fg_color"] = COL_OK
                kwargs["hover_color"] = "#059669"
            elif color:
                kwargs["fg_color"] = color
                kwargs["hover_color"] = "#4b5563"
            ctk.CTkButton(actions, **kwargs).grid(row=0, column=idx, padx=(0, 10))

        status_box = ctk.CTkFrame(toolbar, fg_color=COL_BG, corner_radius=12)
        status_box.grid(row=0, column=1, padx=(0, 12), pady=12, sticky="e")

        self.memory_count_var = tk.StringVar(value="0 条规则")
        self.memory_status_var = tk.StringVar(value="已加载")

        ctk.CTkLabel(
            status_box,
            text="当前状态",
            font=("Microsoft YaHei UI", 10),
            text_color=COL_TEXT_MUTED,
        ).pack(anchor="w", padx=14, pady=(10, 0))
        ctk.CTkLabel(
            status_box,
            textvariable=self.memory_count_var,
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color=COL_TEXT,
        ).pack(anchor="w", padx=14, pady=(2, 0))
        ctk.CTkLabel(
            status_box,
            textvariable=self.memory_status_var,
            font=("Microsoft YaHei UI", 11),
            text_color=COL_TEXT_MUTED,
        ).pack(anchor="w", padx=14, pady=(2, 10))

        table_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        table_card.grid(row=2, column=0, padx=6, pady=8, sticky="nsew")
        table_card.grid_rowconfigure(1, weight=1)
        table_card.grid_columnconfigure(0, weight=1)

        table_header = ctk.CTkFrame(table_card, fg_color="transparent")
        table_header.grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 6), sticky="ew")
        table_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            table_header,
            text="规则列表",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color=COL_TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            table_header,
            text="命中关键词后会优先归类到指定分类。",
            font=("Microsoft YaHei UI", 11),
            text_color=COL_TEXT_MUTED,
        ).grid(row=1, column=0, pady=(2, 0), sticky="w")

        table_surface = ctk.CTkFrame(table_card, fg_color=COL_BG, corner_radius=12)
        table_surface.grid(row=1, column=0, columnspan=2, padx=16, pady=(6, 16), sticky="nsew")
        table_surface.grid_rowconfigure(0, weight=1)
        table_surface.grid_columnconfigure(0, weight=1)

        self._setup_ttk_style()

        columns = ("match", "category", "note")
        self.memory_tree = ttk.Treeview(table_surface, columns=columns, show="headings", selectmode="extended")

        headings = {"match": "命中关键词", "category": "归类到", "note": "备注"}
        widths = {"match": 240, "category": 170, "note": 620}
        for col in columns:
            self.memory_tree.heading(col, text=headings[col])
            self.memory_tree.column(col, width=widths[col], anchor="w")

        self.memory_tree.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=14)

        y_scroll = ttk.Scrollbar(table_surface, orient="vertical", command=self.memory_tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 14), pady=14)
        self.memory_tree.configure(yscrollcommand=y_scroll.set)
        self.memory_tree.bind("<Double-1>", lambda e: self.edit_selected_memory_rule())

        self.load_memory_panel()

    def _setup_ttk_style(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Treeview",
            background="#ffffff",
            foreground="#111827",
            rowheight=32,
            fieldbackground="#ffffff",
            borderwidth=0,
            relief="flat",
            font=("Microsoft YaHei UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#f8fafc",
            foreground="#111827",
            font=("Microsoft YaHei UI", 10, "bold"),
            relief="flat",
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", "#dbeafe")],
            foreground=[("selected", "#111827")],
        )
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

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
            self._refresh_memory_status("已从本地记忆文件加载。")
        except Exception as e:
            messagebox.showerror("加载记忆失败", str(e))

    def refresh_memory_table(self):
        if not hasattr(self, "memory_tree"):
            return

        for row in self.memory_tree.get_children():
            self.memory_tree.delete(row)

        rules = self.memory_data.get("rules", [])
        for index, rule in enumerate(rules):
            tag = "even" if index % 2 == 0 else "odd"
            self.memory_tree.insert(
                "",
                "end",
                iid=str(index),
                tags=(tag,),
                values=(
                    rule.get("match", ""),
                    rule.get("category", ""),
                    rule.get("note", ""),
                ),
            )

        self.memory_tree.tag_configure("even", background="#ffffff")
        self.memory_tree.tag_configure("odd", background="#f8fafc")

        self.memory_count_var.set(f"{len(rules)} 条规则")
        if self.memory_dirty:
            self._refresh_memory_status("有未保存修改。")
        else:
            self._refresh_memory_status("已保存到本地记忆。")

    def _refresh_memory_status(self, text=None):
        if not hasattr(self, "memory_status_var"):
            return
        if text:
            self.memory_status_var.set(text)
        elif self.memory_dirty:
            self.memory_status_var.set("有未保存修改。")
        else:
            self.memory_status_var.set("已保存到本地记忆。")

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
        editor.geometry("520x400")
        editor.configure(fg_color=COL_BG)
        editor.transient(self.root)
        editor.grab_set()

        card = ctk.CTkFrame(editor, fg_color=COL_CARD, corner_radius=16)
        card.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(
            card,
            text="新增整理规则" if is_new else "编辑整理规则",
            font=("Microsoft YaHei UI", 18, "bold"),
            text_color=COL_TEXT,
        ).pack(anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(
            card,
            text="命中关键词后，这条规则会优先把文件归到指定分类。",
            font=("Microsoft YaHei UI", 11),
            text_color=COL_TEXT_MUTED,
        ).pack(anchor="w", padx=20, pady=(0, 12))

        ctk.CTkLabel(card, text="命中关键词（出现在文件名或路径里）", anchor="w").pack(fill="x", padx=20, pady=(8, 4))
        match_var = tk.StringVar(value=rule.get("match", ""))
        ctk.CTkEntry(card, textvariable=match_var, height=36).pack(fill="x", padx=20)

        ctk.CTkLabel(card, text="归类到", anchor="w").pack(fill="x", padx=20, pady=(14, 4))
        cat_default = rule.get("category", CATEGORIES[0])
        if cat_default not in CATEGORIES:
            cat_default = CATEGORIES[0]
        cat_var = tk.StringVar(value=cat_default)
        ctk.CTkOptionMenu(card, variable=cat_var, values=CATEGORIES, height=36).pack(fill="x", padx=20)

        ctk.CTkLabel(card, text="备注（可选）", anchor="w").pack(fill="x", padx=20, pady=(14, 4))
        note_var = tk.StringVar(value=rule.get("note", ""))
        ctk.CTkEntry(card, textvariable=note_var, height=36).pack(fill="x", padx=20)

        action_row = ctk.CTkFrame(card, fg_color="transparent")
        action_row.pack(fill="x", padx=20, pady=20)
        action_row.grid_columnconfigure((0, 1), weight=1)

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

        ctk.CTkButton(
            action_row,
            text="取消",
            fg_color="transparent",
            border_width=1,
            border_color=COL_BORDER,
            text_color=COL_TEXT_NAV,
            hover_color=COL_HOVER,
            height=38,
            command=editor.destroy,
        ).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkButton(
            action_row,
            text="保存规则",
            fg_color=COL_ACCENT,
            hover_color="#1d4ed8",
            height=38,
            command=save,
        ).grid(row=0, column=1, padx=(8, 0), sticky="ew")

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
            self.refresh_memory_table()
            self._refresh_memory_status("已保存到本地记忆。")
            if not silent:
                messagebox.showinfo("保存成功", "整理记忆已保存。")
            return True
        except Exception as e:
            messagebox.showerror("保存记忆失败", str(e))
            return False
