import json
import shutil
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from desktop_agent.i18n import t

try:
    from desktop_agent.builtin_llm import get_builtin_config
except Exception:
    get_builtin_config = None


CONFIG_FILE = Path("config.json")
PROJECT_DIR = Path.cwd()

COL_CARD = "#ffffff"
COL_ACCENT = "#2563eb"
COL_TEXT = "#111827"
COL_TEXT_MUTED = "#6b7280"
COL_TEXT_NAV = "#374151"
COL_HOVER = "#f1f3f9"
COL_BORDER = "#e5e7eb"

MODEL_DOWNLOAD_URL = ""
MODEL_MIN_VALID_BYTES = 20 * 1024 * 1024
HF_HOST = "huggingface.co"
HF_MIRROR_HOST = "hf-mirror.com"


class ModelDownloadMixin:
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
        primary = self.get_model_url()
        urls = []

        def add(url):
            if url and url not in urls:
                urls.append(url)

        add(primary)

        if primary:
            if HF_HOST in primary:
                add(primary.replace(HF_HOST, HF_MIRROR_HOST))
            elif HF_MIRROR_HOST in primary:
                add(primary.replace(HF_MIRROR_HOST, HF_HOST))

        return urls

    def show_first_run_wizard_if_needed(self):
        config = self.read_config_safely()

        if config.get("first_run_completed", False):
            return

        wizard = ctk.CTkToplevel(self.root)
        wizard.title(t("dialogs.welcome_title"))
        wizard.geometry("560x540")
        wizard.transient(self.root)
        wizard.grab_set()

        ctk.CTkLabel(
            wizard,
            text=t("app.title"),
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(pady=(24, 8))
        ctk.CTkLabel(
            wizard,
            text=t("dialogs.welcome_subtitle"),
            text_color=COL_TEXT_MUTED,
        ).pack(pady=(0, 18))

        box = ctk.CTkFrame(wizard, fg_color=COL_CARD, corner_radius=12)
        box.pack(fill="x", padx=28, pady=10)

        target_var = tk.StringVar(value=config.get("normal_target_root", "") or "D:\\Desktop_Sorted")

        ctk.CTkLabel(box, text=t("dialogs.target_folder"), font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=18, pady=(16, 6))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkEntry(row, textvariable=target_var).pack(side="left", fill="x", expand=True)

        def pick_target():
            selected = filedialog.askdirectory(title=t("dialogs.pick_target"))
            if selected:
                target_var.set(selected)

        ctk.CTkButton(row, text=t("common.browse"), width=70, command=pick_target).pack(side="left", padx=(8, 0))

        mode_var = tk.StringVar(value="builtin")
        mode_box = ctk.CTkFrame(wizard, fg_color="transparent")
        mode_box.pack(fill="x", padx=28, pady=10)

        ctk.CTkLabel(mode_box, text=t("dialogs.mode_title"), font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 8))

        for value, title, desc in [
            ("builtin", t("dialogs.mode_builtin_title"), t("dialogs.mode_builtin_desc")),
            ("none", t("dialogs.mode_none_title"), t("dialogs.mode_none_desc")),
        ]:
            card = ctk.CTkFrame(mode_box, fg_color=COL_CARD, corner_radius=12)
            card.pack(fill="x", pady=5)
            ctk.CTkRadioButton(
                card,
                text=title,
                variable=mode_var,
                value=value,
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(anchor="w", padx=16, pady=(12, 2))
            ctk.CTkLabel(
                card, text=desc, text_color=COL_TEXT_MUTED,
                wraplength=460, justify="left"
            ).pack(anchor="w", padx=42, pady=(0, 12))

        def finish():
            provider = mode_var.get()
            self.update_config_provider(provider, target_root=target_var.get().strip())
            try:
                wizard.grab_release()
            except Exception:
                pass
            wizard.destroy()

            if provider == "builtin" and not self.is_model_present():
                self.open_model_setup(on_done=lambda: (self.refresh_home_status(), self.show_page("Home")))
            else:
                self.refresh_home_status()
                self.show_page("Home")

        ctk.CTkButton(wizard, text=t("dialogs.get_started"), height=40, corner_radius=8, command=finish).pack(pady=20)

    def update_config_provider(self, provider, target_root=None):
        config = self.read_config_safely()
        config["first_run_completed"] = True
        config["llm_provider"] = provider
        if target_root:
            config["normal_target_root"] = target_root
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        self.load_config_panel()
        self.update_home_summary()

    def open_model_setup(self, on_done=None, allow_skip=True):
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(t("dialogs.model_setup_title"))
        dlg.geometry("620x560")
        dlg.minsize(620, 520)
        dlg.transient(self.root)
        dlg.grab_set()

        ctk.CTkLabel(
            dlg,
            text=t("dialogs.model_setup_title"),
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(24, 8))
        ctk.CTkLabel(
            dlg,
            text=t("dialogs.model_setup_subtitle"),
            text_color=COL_TEXT_MUTED, justify="left",
            wraplength=480,
        ).pack(pady=(0, 18))

        target = self.get_model_file_path()

        def option(title, desc, button, cmd, primary=False):
            card = ctk.CTkFrame(dlg, fg_color=COL_CARD, corner_radius=12)
            card.pack(fill="x", padx=26, pady=8)
            card.grid_columnconfigure(0, weight=1)
            tf = ctk.CTkFrame(card, fg_color="transparent")
            tf.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
            ctk.CTkLabel(tf, text=title, font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w")
            ctk.CTkLabel(tf, text=desc, text_color=COL_TEXT_MUTED, wraplength=400, justify="left").pack(anchor="w", pady=(2, 0))
            ctk.CTkButton(
                card, text=button, width=110, height=34, corner_radius=8,
                fg_color=COL_ACCENT if primary else "transparent",
                text_color="white" if primary else COL_TEXT_NAV,
                border_width=0 if primary else 1, border_color=COL_BORDER,
                hover_color=COL_ACCENT if primary else COL_HOVER,
                command=cmd,
            ).grid(row=0, column=1, padx=16, pady=12)

        option(
            t("dialogs.model_download_title"),
            t("dialogs.model_download_desc", path=target),
            t("dialogs.download"),
            lambda: self._start_model_download(dlg, on_done),
            True,
        )
        option(
            t("dialogs.model_pick_title"),
            t("dialogs.model_pick_desc"),
            t("dialogs.choose_file"),
            lambda: self._pick_model_file(dlg, on_done),
        )

        if allow_skip:
            option(
                t("dialogs.model_skip_title"),
                t("dialogs.model_skip_desc"),
                t("common.skip"),
                lambda: self._skip_model(dlg, on_done),
            )

        cancel_btn = ctk.CTkButton(modal := dlg, text=t("common.cancel"), height=32, corner_radius=8, fg_color="#6b7280", hover_color="#4b5563")
        cancel_btn.configure(command=lambda: (modal.grab_release(), modal.destroy()))
        cancel_btn.pack(pady=(10, 18))

    def _skip_model(self, dlg, on_done):
        config = self.read_config_safely()
        config["llm_provider"] = "none"
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        self.load_config_panel()
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()
        self.refresh_home_status()
        self.show_page("Home")

    def _pick_model_file(self, dlg, on_done):
        source = filedialog.askopenfilename(
            title=t("dialogs.pick_gguf_title"),
            filetypes=[(t("dialogs.gguf_files"), "*.gguf"), (t("dialogs.all_files"), "*.*")],
        )
        if not source:
            return
        target = self.get_model_file_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()
        self._run_copy_with_progress(Path(source), target, on_done)

    def _start_model_download(self, dlg, on_done):
        urls = self.get_model_urls()
        if not urls:
            messagebox.showwarning(
                t("dialogs.no_model_url_title"),
                t("dialogs.no_model_url_message")
            )
            return
        target = self.get_model_file_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()
        self._run_download_with_progress(urls, target, on_done)

    def _make_transfer_modal(self, title):
        modal = ctk.CTkToplevel(self.root)
        modal.title(t("workflow.please_wait"))
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
        status = tk.StringVar(value=t("workflow.preparing"))
        ctk.CTkLabel(modal, textvariable=status, text_color=COL_TEXT_MUTED).pack(padx=22, pady=(0, 10), anchor="w")
        cancel_btn = ctk.CTkButton(modal, text=t("common.cancel"), height=32, corner_radius=8, fg_color="#6b7280", hover_color="#4b5563")
        cancel_btn.pack(padx=22, pady=(0, 14), anchor="e")
        return {"modal": modal, "pb": pb, "status": status, "cancel_btn": cancel_btn}

    def _update_transfer(self, modal, done, total):
        try:
            if total > 0:
                modal["pb"].set(min(done / total, 1.0))
                modal["status"].set(f"{done / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB")
            else:
                modal["status"].set(t("dialogs.processed_mb", done=f"{done / 1024 / 1024:.1f}"))
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
            messagebox.showinfo(t("common.done"), t("dialogs.model_ready_message"))
            if on_done:
                on_done()
        else:
            messagebox.showerror(t("common.failed"), str(err))

    def _run_copy_with_progress(self, src, target, on_done):
        modal = self._make_transfer_modal(t("dialogs.copying_model"))
        state = {"cancel": False}
        modal["cancel_btn"].configure(command=lambda: state.update(cancel=True))
        part = target.parent / (target.name + ".part")

        def worker():
            try:
                total = src.stat().st_size
                done = 0
                with open(src, "rb") as fin, open(part, "wb") as fout:
                    while True:
                        if state["cancel"]:
                            raise RuntimeError(t("common.cancelled"))
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

        modal = self._make_transfer_modal(t("dialogs.downloading_model"))
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
                    errors.append(t("common.cancelled"))
                    break

                self.root.after(0, lambda i=idx, n=total_sources: set_status(t("dialogs.connecting_source", index=i, total=n)))
                self.root.after(0, lambda: set_indeterminate(True))

                try:
                    with requests.get(url, stream=True, timeout=(20, 60)) as resp:
                        resp.raise_for_status()
                        total = int(resp.headers.get("Content-Length", 0)) or 0
                        done = 0
                        got_first = False

                        with open(part, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=1024 * 256):
                                if state["cancel"]:
                                    raise RuntimeError(t("common.cancelled"))
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
                    return
                except Exception as e:
                    errors.append(t("dialogs.source_error", index=idx, error=e))
                    try:
                        if part.exists():
                            part.unlink()
                    except Exception:
                        pass
                    if state["cancel"]:
                        break
                    continue

            msg = "；".join(errors[-2:]) if errors else t("common.unknown_error")
            self.root.after(0, lambda m=msg: self._finish_transfer(modal, False, on_done, m))

        threading.Thread(target=worker, daemon=True).start()
