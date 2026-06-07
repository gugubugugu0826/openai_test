import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from desktop_agent.i18n import get_language, get_language_by_label, get_language_label, set_language, t
from desktop_agent_ui.theme import *

CONFIG_FILE = Path("config.json")


class ConfigPageMixin:
    def build_config_page(self, parent):
        self.page_header(parent, t("config.page_title"), t("config.page_subtitle"))

        parent.grid_rowconfigure(1, weight=0)
        parent.grid_rowconfigure(2, weight=1)

        actions = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=14)
        actions.grid(row=1, column=0, padx=24, pady=(0, 8), sticky="ew")

        action_buttons = [
            (t("config.save"), {"fg_color": COL_OK, "hover_color": "#059669"}, self.save_config_panel),
            (t("config.load"), {}, self.load_config_panel),
            (t("config.reset"), {"fg_color": "#6b7280", "hover_color": "#4b5563"}, self.reset_config_to_default),
            (t("config.export"), {}, self.export_config),
            (t("config.import"), {}, self.import_config),
            (t("config.get_ai_model"), {"fg_color": "#0d9488", "hover_color": "#0f766e"}, lambda: self.open_model_setup(on_done=self.refresh_home_status)),
        ]
        for text, style, command in action_buttons:
            ctk.CTkButton(actions, text=text, corner_radius=8, command=command, **style).pack(side="left", padx=8, pady=12)

        body = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        body.grid(row=2, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        self.config_vars = {}

        self.build_config_section(
            body,
            row=0,
            title=t("config.basic_title"),
            fields=[
                ("ui_language", t("config.language"), t("config.language_hint")),
                ("desktop_path", t("config.scan_path"), t("config.scan_path_hint")),
                ("normal_target_root", t("config.target_root"), t("config.target_root_hint")),
                ("folder_mode", t("config.folder_mode"), t("config.folder_mode_hint")),
            ],
        )
        self.build_config_section(
            body,
            row=1,
            title=t("config.ai_title"),
            fields=[
                ("llm_provider", "LLM Provider", "none / ollama / openai_compatible / builtin"),
                ("model", t("config.ollama_model"), t("config.ollama_model_hint")),
                ("ollama_url", t("config.ollama_api"), "http://localhost:11434/api/generate"),
                ("api_base_url", t("config.cloud_api_url"), "OpenAI-compatible chat completions endpoint"),
                ("api_model", t("config.cloud_model"), t("config.cloud_model_hint")),
                ("api_key", t("config.cloud_api_key"), t("config.cloud_api_key_hint")),
            ],
        )
        self.build_config_section(
            body,
            row=2,
            title=t("config.builtin_title"),
            fields=[
                ("builtin_server_host", "Builtin Host", t("config.default_host_hint")),
                ("builtin_server_port", "Builtin Port", t("config.default_port_hint")),
                ("builtin_server_path", t("config.llama_server_path"), "runtime\\llama-server.exe"),
                ("builtin_model_path", t("config.gguf_model_path"), "models\\qwen-small.gguf"),
                ("builtin_api_model", "Builtin API Model", t("config.builtin_api_model_hint")),
                ("builtin_context_size", t("config.context_size"), t("config.context_size_hint")),
                ("builtin_threads", t("config.cpu_threads"), t("config.cpu_threads_hint")),
                ("builtin_model_url", t("config.model_download_url"), t("config.model_download_url_hint")),
            ],
        )
        self.build_config_section(
            body,
            row=3,
            title=t("config.performance_title"),
            fields=[
                ("batch_size", t("config.batch_size"), t("config.batch_size_hint")),
                ("max_internal_items_per_folder", t("config.folder_sample_limit"), t("config.folder_sample_limit_hint")),
                ("first_run_completed", t("config.first_run_completed"), "true or false"),
            ],
        )
        self.build_config_section(
            body,
            row=4,
            title=t("config.updates_title"),
            fields=[
                ("update_manifest_url", t("config.update_manifest_url"), t("config.update_manifest_hint")),
                ("auto_check_updates", t("config.auto_check_updates"), "true / false"),
            ],
        )

        self.load_config_panel()

    def build_config_section(self, parent, row, title, fields):
        card = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=14)
        card.grid(row=row, column=0, padx=6, pady=10, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=18, weight="bold"), text_color=COL_TEXT).grid(row=0, column=0, columnspan=3, padx=18, pady=(16, 8), sticky="w")

        for i, (key, label, hint) in enumerate(fields, start=1):
            ctk.CTkLabel(card, text=label, width=160, anchor="w", text_color=COL_TEXT_NAV).grid(row=i, column=0, padx=18, pady=8, sticky="w")

            var = tk.StringVar()
            self.config_vars[key] = var
            var.trace_add("write", lambda *args: self._on_config_var_write())

            input_frame = ctk.CTkFrame(card, fg_color="transparent")
            input_frame.grid(row=i, column=1, padx=8, pady=8, sticky="ew")
            input_frame.grid_columnconfigure(0, weight=1)

            if key == "ui_language":
                widget = ctk.CTkOptionMenu(input_frame, variable=var, values=[get_language_label("zh"), get_language_label("en")])
                widget.grid(row=0, column=0, sticky="ew")
            elif key == "llm_provider":
                widget = ctk.CTkOptionMenu(input_frame, variable=var, values=["none", "ollama", "openai_compatible", "builtin"])
                widget.grid(row=0, column=0, sticky="ew")
            elif key == "folder_mode":
                widget = ctk.CTkOptionMenu(input_frame, variable=var, values=["copy", "move"])
                widget.grid(row=0, column=0, sticky="ew")
            elif key in {"first_run_completed", "auto_check_updates"}:
                widget = ctk.CTkOptionMenu(input_frame, variable=var, values=["true", "false"])
                widget.grid(row=0, column=0, sticky="ew")
            else:
                widget = ctk.CTkEntry(input_frame, textvariable=var)
                widget.grid(row=0, column=0, sticky="ew")

                if key == "desktop_path":
                    ctk.CTkButton(input_frame, text=t("config.browse"), width=70, command=self.browse_desktop_path).grid(row=0, column=1, padx=(8, 0))
                if key == "normal_target_root":
                    ctk.CTkButton(input_frame, text=t("config.browse"), width=70, command=self.browse_target_root).grid(row=0, column=1, padx=(8, 0))
                if key == "api_key":
                    widget.configure(show="*")
                    toggle_btn = ctk.CTkButton(
                        input_frame,
                        text=t("config.show"),
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
                            btn.configure(text=t("config.hide"))
                        else:
                            entry.configure(show="*")
                            btn.configure(text=t("config.show"))

                    toggle_btn.configure(command=_toggle_key)

            ctk.CTkLabel(card, text=hint, text_color=COL_TEXT_MUTED, anchor="w").grid(row=i, column=2, padx=18, pady=8, sticky="w")

    def browse_desktop_path(self):
        initial_dir = self.config_vars.get("desktop_path").get().strip() if self.config_vars.get("desktop_path") else ""
        if not initial_dir:
            initial_dir = str(Path.home() / "Desktop")
        selected = filedialog.askdirectory(title=t("config.select_scan_folder"), initialdir=initial_dir if Path(initial_dir).exists() else str(Path.home()))
        if selected:
            self.config_vars["desktop_path"].set(selected)

    def browse_target_root(self):
        initial_dir = self.config_vars.get("normal_target_root").get().strip() if self.config_vars.get("normal_target_root") else ""
        if not initial_dir:
            initial_dir = "D:\\Desktop_Sorted"
        selected = filedialog.askdirectory(title=t("config.select_target_folder"), initialdir=initial_dir if Path(initial_dir).exists() else str(Path.home()))
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
            config["ui_language"] = get_language_by_label(self.config_vars["ui_language"].get().strip() or get_language_label(get_language()))

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
            config["max_internal_items_per_folder"] = int(self.config_vars["max_internal_items_per_folder"].get().strip())
            config["update_manifest_url"] = self.config_vars["update_manifest_url"].get().strip()
            auto_update_text = self.config_vars["auto_check_updates"].get().strip().lower() or "true"
            config["auto_check_updates"] = auto_update_text == "true"

            if first_run_text not in ["true", "false"]:
                raise ValueError(t("config.err_first_run"))
            if auto_update_text not in ["true", "false"]:
                raise ValueError(t("config.err_auto_update"))
            if config["llm_provider"] not in ["none", "ollama", "openai_compatible", "builtin"]:
                raise ValueError(t("config.err_provider"))
            if config["folder_mode"] not in ["copy", "move"]:
                raise ValueError(t("config.err_folder_mode"))
            if config["batch_size"] <= 0:
                raise ValueError(t("config.err_batch_size"))
            if config["max_internal_items_per_folder"] <= 0:
                raise ValueError(t("config.err_folder_sample_limit"))
            if config["builtin_server_port"] <= 0:
                raise ValueError(t("config.err_builtin_port"))
            if config["builtin_context_size"] <= 0:
                raise ValueError(t("config.err_context_size"))
            if config["builtin_threads"] <= 0:
                raise ValueError(t("config.err_threads"))

            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            set_language(config["ui_language"])
            self.config_dirty = False
            self.update_home_summary()
            self.update_dashboard()
            if not silent:
                messagebox.showinfo(t("config.saved_title"), t("config.saved_message"))
            self.rebuild_window_for_language("Settings")
            return True
        except Exception as exc:
            messagebox.showerror(t("config.save_failed_title"), str(exc))
            return False

    def reset_config_to_default(self):
        if not messagebox.askyesno(t("config.reset_confirm_title"), t("config.reset_confirm_message")):
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
            title=t("config.export_title"),
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialfile="config_backup.json",
        )
        if not target_path:
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as src:
                data = json.load(src)
            with open(target_path, "w", encoding="utf-8") as dst:
                json.dump(data, dst, ensure_ascii=False, indent=2)
            messagebox.showinfo(t("config.exported_title"), t("config.exported_message", path=target_path))
        except Exception as exc:
            messagebox.showerror(t("config.export_failed_title"), str(exc))

    def import_config(self):
        source_path = filedialog.askopenfilename(
            title=t("config.import_title"),
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
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
            messagebox.showinfo(t("config.imported_title"), t("config.imported_message"))
            self.rebuild_window_for_language("Settings")
        except Exception as exc:
            messagebox.showerror(t("config.import_failed_title"), str(exc))
