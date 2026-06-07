import os
import threading
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from desktop_agent.i18n import t
from desktop_agent.updater import DEFAULT_UPDATE_DIR, check_for_update, download_update_package
from desktop_agent.version import APP_VERSION
from desktop_agent_ui.theme import *


README_FILE = Path("README_使用说明.txt")


class HelpPageMixin:
    def auto_check_updates_if_needed(self):
        config = self.read_config_safely()
        if not config.get("auto_check_updates", True):
            return
        if not str(config.get("update_manifest_url", "")).strip():
            return
        self.check_for_updates_gui(auto=True)

    def check_for_updates_gui(self, auto=False):
        if getattr(self, "checking_updates", False):
            if not auto:
                messagebox.showwarning(t("help.update.checking_title"), t("help.update.checking_message"))
            return

        config = self.read_config_safely()
        manifest_url = str(config.get("update_manifest_url", "")).strip()
        if not manifest_url:
            if not auto:
                messagebox.showwarning(t("help.update.missing_url_title"), t("help.update.missing_url_message"))
            return

        self.checking_updates = True
        self.append_output(
            t(
                "help.update.check_start_log",
                current_version=APP_VERSION,
                manifest_url=manifest_url,
            )
        )

        def worker():
            try:
                manifest = check_for_update(manifest_url, APP_VERSION)
                self.root.after(0, lambda: self._handle_update_manifest(manifest, auto))
            except Exception as exc:
                self.root.after(0, lambda msg=str(exc): self._finish_update_check_error(msg, auto))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_check_error(self, message, auto):
        self.checking_updates = False
        self.append_output(t("help.update.check_failed_log", message=message))
        if not auto:
            messagebox.showerror(t("help.update.check_failed_title"), message)

    def _handle_update_manifest(self, manifest, auto):
        self.checking_updates = False
        latest_version = manifest.get("version", "")
        notes = str(manifest.get("notes", "") or "").strip()

        if not manifest.get("has_update"):
            self.append_output(t("help.update.latest_log", version=APP_VERSION))
            if not auto:
                messagebox.showinfo(t("help.update.latest_title"), t("help.update.latest_message", version=APP_VERSION))
            return

        self.append_output(
            t(
                "help.update.available_log",
                version=latest_version,
                package_url=manifest.get("package_url", ""),
            )
        )

        message = t(
            "help.update.available_message",
            latest_version=latest_version,
            current_version=APP_VERSION,
        )
        if notes:
            message += "\n\n" + t("help.update.notes_prefix") + "\n" + notes[:800]

        if messagebox.askyesno(t("help.update.available_title"), message):
            self.download_update_package_gui(manifest)

    def download_update_package_gui(self, manifest):
        modal = self._make_transfer_modal(t("help.update.downloading"))
        state = {"cancel": False}
        modal["cancel_btn"].configure(command=lambda: state.update(cancel=True))

        def progress(done, total):
            self.root.after(0, lambda d=done, t_total=total: self._update_transfer(modal, d, t_total))

        def worker():
            try:
                target, sha256_actual = download_update_package(
                    manifest,
                    Path.cwd() / DEFAULT_UPDATE_DIR,
                    progress_callback=progress,
                    cancel_flag=state,
                )
                self.root.after(0, lambda p=target, s=sha256_actual: self._finish_update_download(modal, True, p, s))
            except Exception as exc:
                self.root.after(0, lambda msg=str(exc): self._finish_update_download(modal, False, None, "", msg))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_download(self, modal, ok, target, sha256_actual="", err=None):
        try:
            modal["modal"].grab_release()
        except Exception:
            pass
        try:
            modal["modal"].destroy()
        except Exception:
            pass

        if not ok:
            self.append_output(t("help.update.download_failed_log", message=err))
            messagebox.showerror(t("help.update.download_failed_title"), str(err))
            return

        self.append_output(
            t(
                "help.update.downloaded_log",
                target=str(target),
                sha256=sha256_actual,
            )
        )

        if messagebox.askyesno(t("help.update.downloaded_title"), t("help.update.downloaded_message", target=str(target))):
            try:
                os.startfile(str(Path(target).parent))
            except Exception as exc:
                messagebox.showerror(t("help.open_folder_failed_title"), str(exc))

    def build_help_page(self, parent):
        self.page_header(parent, t("help.page_title"), t("help.page_subtitle"))

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        toolbar.grid(row=0, column=0, padx=6, pady=6, sticky="ew")

        ctk.CTkButton(toolbar, text=t("help.open_readme"), corner_radius=8, command=self.open_readme_file).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(toolbar, text=t("help.copy_flow"), corner_radius=8, command=self.print_quick_guide_to_log).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(toolbar, text=t("help.check_updates"), corner_radius=8, fg_color="#0d9488", hover_color="#0f766e", command=self.check_for_updates_gui).pack(side="left", padx=8, pady=12)

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
        return t("help.content")

    def open_readme_file(self):
        if not README_FILE.exists():
            messagebox.showwarning(t("help.no_readme_title"), t("help.no_readme_message"))
            return

        try:
            os.startfile(str(README_FILE))
        except Exception as exc:
            messagebox.showerror(t("help.open_readme_failed_title"), str(exc))

    def print_quick_guide_to_log(self):
        self.append_output(t("help.quick_flow_log"))
