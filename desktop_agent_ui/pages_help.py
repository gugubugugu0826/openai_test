import os
import threading
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from desktop_agent_ui.theme import *

README_FILE = Path("README_使用说明.txt")

from desktop_agent.updater import check_for_update, download_update_package, DEFAULT_UPDATE_DIR
from desktop_agent.version import APP_VERSION


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
                messagebox.showwarning("正在检查", "当前已经有更新检查任务在运行。")
            return

        config = self.read_config_safely()
        manifest_url = str(config.get("update_manifest_url", "")).strip()

        if not manifest_url:
            if not auto:
                messagebox.showwarning(
                    "缺少更新地址",
                    "请先在「设置」里的「软件更新」填写 update_manifest_url。\n\n"
                    "它应当指向 GitHub Releases 最新发布 API，或 latest.json 更新清单。"
                )
            return

        self.checking_updates = True
        self.append_output(
            f"\n[更新] 正在检查远程更新...\n"
            f"[更新] 当前版本：{APP_VERSION}\n"
            f"[更新] 清单地址：{manifest_url}\n"
        )

        def worker():
            try:
                manifest = check_for_update(manifest_url, APP_VERSION)
                self.root.after(0, lambda: self._handle_update_manifest(manifest, auto))
            except Exception as e:
                self.root.after(0, lambda msg=str(e): self._finish_update_check_error(msg, auto))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_check_error(self, message, auto):
        self.checking_updates = False
        self.append_output(f"[更新] 检查失败：{message}\n")

        if not auto:
            messagebox.showerror("检查更新失败", message)

    def _handle_update_manifest(self, manifest, auto):
        self.checking_updates = False
        latest_version = manifest.get("version", "")
        notes = str(manifest.get("notes", "") or "").strip()

        if not manifest.get("has_update"):
            self.append_output(f"[更新] 当前已是最新版本：{APP_VERSION}\n")

            if not auto:
                messagebox.showinfo("已经是最新版本", f"当前版本：{APP_VERSION}")
            return

        self.append_output(
            f"[更新] 发现新版本：{latest_version}\n"
            f"[更新] 下载地址：{manifest.get('package_url')}\n"
        )

        message = (
            f"发现新版本：{latest_version}\n"
            f"当前版本：{APP_VERSION}\n\n"
            "是否现在下载更新包？"
        )

        if notes:
            message += f"\n\n更新说明：\n{notes[:800]}"

        if messagebox.askyesno("发现新版本", message):
            self.download_update_package_gui(manifest)

    def download_update_package_gui(self, manifest):
        modal = self._make_transfer_modal("正在下载更新包...")
        state = {"cancel": False}
        modal["cancel_btn"].configure(command=lambda: state.update(cancel=True))

        def progress(done, total):
            self.root.after(0, lambda d=done, t=total: self._update_transfer(modal, d, t))

        def worker():
            try:
                target, sha256_actual = download_update_package(
                    manifest,
                    Path.cwd() / DEFAULT_UPDATE_DIR,
                    progress_callback=progress,
                    cancel_flag=state,
                )
                self.root.after(
                    0,
                    lambda p=target, s=sha256_actual: self._finish_update_download(modal, True, p, s)
                )
            except Exception as e:
                self.root.after(
                    0,
                    lambda msg=str(e): self._finish_update_download(modal, False, None, "", msg)
                )

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
            self.append_output(f"[更新] 下载失败：{err}\n")
            messagebox.showerror("下载更新失败", str(err))
            return

        self.append_output(
            f"[更新] 更新包已下载：{target}\n"
            f"[更新] sha256：{sha256_actual}\n"
        )

        if messagebox.askyesno(
            "更新包已下载",
            f"更新包已下载到：\n{target}\n\n"
            "请关闭当前程序后，解压并运行新版。\n\n是否打开更新包所在文件夹？"
        ):
            try:
                os.startfile(str(Path(target).parent))
            except Exception as e:
                messagebox.showerror("打开文件夹失败", str(e))

    def build_help_page(self, parent):
        self.page_header(
            parent,
            "帮助",
            "使用说明、整理流程、安全机制和常见问题。",
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 20), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        toolbar.grid(row=0, column=0, padx=6, pady=6, sticky="ew")

        ctk.CTkButton(toolbar, text="打开 README", corner_radius=8, command=self.open_readme_file).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(toolbar, text="复制推荐流程到日志", corner_radius=8, command=self.print_quick_guide_to_log).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(toolbar, text="检查更新", corner_radius=8, fg_color="#0d9488", hover_color="#0f766e", command=self.check_for_updates_gui).pack(side="left", padx=8, pady=12)

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
        return r"""桌面整理助手 使用说明

最简单的用法（在「整理桌面」页面）：
1. 看顶部状态卡，显示“一切就绪”就可以开始。
2. 点 ① 扫描并生成整理方案（不会移动文件）。
3. 点 ② 查看并调整方案，需要的话改分类或跳过。
4. 点 ③ 确认并开始整理，核对摘要后正式整理。

安全机制：
- ① 扫描只生成方案，不会移动任何文件。
- ③ 整理前会显示完整摘要，需要二次确认。
- 文件夹默认 copy（复制），原文件保留。
- 错误报告里的 API Key 会自动隐藏。

模型模式（在「设置 → AI 模式」里切换，普通用户用默认即可）：
- builtin：软件自带 AI，无需安装 Ollama 或 API Key（推荐）。
- none：只按规则分类，速度最快，不使用 AI。
- ollama：本地 Ollama + Qwen。
- openai_compatible：云端 API。

进阶：
- 「高级操作」页可单步运行 check / scan / preview / review / learn / dryrun / apply / undo。
- 「计划解释」页让 AI 解释本次整理计划。
- 「运行日志」页查看完整输出并生成诊断报告。
"""

    def open_readme_file(self):
        if not README_FILE.exists():
            messagebox.showwarning("没有 README", "找不到 README_使用说明.txt。")
            return

        try:
            os.startfile(str(README_FILE))
        except Exception as e:
            messagebox.showerror("打开 README 失败", str(e))

    def print_quick_guide_to_log(self):
        guide = """
推荐流程（在「整理桌面」页面）：
1. 查看状态卡，显示“一切就绪”
2. ① 扫描并生成整理方案
3. ② 查看 / 调整方案
4. ③ 确认并开始整理
5. 打开整理目录查看结果
"""
        self.append_output(guide)

    # =====================================================
    # First Run Wizard (简化引导)
    # =====================================================

    # =====================================================
    # Command Runner
    # =====================================================
