import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from desktop_agent.i18n import (
    get_language,
    get_language_label,
    set_language,
    t,
)
from desktop_agent_ui.theme import *

CONFIG_FILE = Path("config.json")


class ConfigPageMixin:
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
                ("desktop_path", "扫描路径", "留空表示当前用户桌面 + 公用桌面"),
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

        self.build_config_section(
            body,
            row=4,
            title="软件更新",
            fields=[
                ("update_manifest_url", "更新清单地址", "指向 latest.json；留空表示不检查更新"),
                ("auto_check_updates", "启动时自动检查", "true / false"),
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

            if key == "ui_language":
                widget = ctk.CTkOptionMenu(
                    input_frame,
                    variable=var,
                    values=[get_language_label("zh"), get_language_label("en")],
                )
                widget.grid(row=0, column=0, sticky="ew")
            elif key == "llm_provider":
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

                if key == "api_key":
                    widget.configure(show="*")
                    toggle_btn = ctk.CTkButton(
                        input_frame,
                        text="显示",
                        width=60,
                        corner_radius=8,
                        fg_color="transparent",
                        border_width=1,
                        border_color=COL_BORDER,
                        text_color=COL_TEXT_NAV,
                        hover_color=COL_HOVER,
                    )
                    toggle_btn.grid(row=0, column=1, padx=(8, 0))

                    def _toggle_key(btn=toggle_btn, entry=widget):
                        if entry.cget("show") == "*":
                            entry.configure(show="")
                            btn.configure(text="隐藏")
                        else:
                            entry.configure(show="*")
                            btn.configure(text="显示")

                    toggle_btn.configure(command=_toggle_key)

            ctk.CTkLabel(
                card,
                text=hint,
                text_color=COL_TEXT_MUTED,
                anchor="w",
            ).grid(row=i, column=2, padx=18, pady=8, sticky="w")

    # =====================================================
    # Help Page
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
            if key == "ui_language":
                value = get_language_label(value or get_language())
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

            config["ui_language"] = get_language()

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
            config["update_manifest_url"] = self.config_vars["update_manifest_url"].get().strip()
            auto_update_text = self.config_vars["auto_check_updates"].get().strip().lower() or "true"
            config["auto_check_updates"] = auto_update_text == "true"

            if first_run_text not in ["true", "false"]:
                raise ValueError("first_run_completed 只能是 true 或 false")

            if auto_update_text not in ["true", "false"]:
                raise ValueError("auto_check_updates 只能是 true 或 false")

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
                messagebox.showinfo(
                    self._lang("保存成功", "Saved"),
                    self._lang("设置已保存。", "Settings saved.")
                )
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

        set_language(default_config.get("ui_language"))
        self.load_config_panel()
        self.update_home_summary()
        self.update_dashboard()
        self.rebuild_window_for_language("Settings")

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

            set_language(config.get("ui_language"))
            self.load_config_panel()
            self.update_home_summary()
            self.update_dashboard()
            messagebox.showinfo(self._lang("导入成功", "Imported"), self._lang("配置已导入。建议回到「整理桌面」点「重新检查」。", "Config imported. Return to Organize Desktop and click Re-check."))
            self.rebuild_window_for_language("Settings")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    # =====================================================
    # Diagnostics
    # =====================================================
