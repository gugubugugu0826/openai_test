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

        # ── Toolbar — primary action highlighted, others as quiet secondary ──
        toolbar = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        toolbar.grid(row=0, column=0, padx=6, pady=(6, 10), sticky="ew")
        toolbar.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(toolbar, fg_color="transparent")
        left.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        ctk.CTkButton(
            left, text=t("help.check_updates"),
            width=120, height=34, corner_radius=8,
            fg_color=COL_ACCENT, hover_color="#1d4ed8", text_color="white",
            command=self.check_for_updates_gui,
        ).pack(side="left", padx=4)

        for label, cmd in (
            (t("help.open_readme"), self.open_readme_file),
            (t("help.copy_flow"), self.print_quick_guide_to_log),
        ):
            ctk.CTkButton(
                left, text=label,
                width=120, height=34, corner_radius=8,
                fg_color="transparent", border_width=1, border_color=COL_BORDER,
                text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
                command=cmd,
            ).pack(side="left", padx=4)

        ctk.CTkLabel(
            toolbar, text=f"v {APP_VERSION}",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=COL_TEXT_MUTED,
        ).grid(row=0, column=2, padx=18, sticky="e")

        # ── Scrollable, card-based content ─────────────────────────────────
        scroll = ctk.CTkScrollableFrame(body, fg_color="transparent")
        scroll.grid(row=1, column=0, padx=2, pady=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        row = 0
        for section in self._help_sections():
            row = self._render_help_section(scroll, row, section)
        self._render_help_faq(scroll, row)

    # ------------------------------------------------------------------ data
    def _help_sections(self):
        """Structured help content. Each item is i18n-driven with a fallback."""
        return [
            {
                "icon": "⌂", "accent": COL_ACCENT, "soft": COL_ACCENT_SOFT,
                "title": t("help.start_title", default="快速开始"),
                "numbered": True,
                "items": [
                    t("help.start_step1", default="在「整理桌面」页，等待顶部状态卡显示“一切就绪”。"),
                    t("help.start_step2", default="点第 1 步：扫描并生成整理方案（只读，不会移动任何文件）。"),
                    t("help.start_step3", default="点第 2 步：查看方案，按需修改分类或跳过某些项目。"),
                    t("help.start_step4", default="点第 3 步：核对摘要后确认，正式开始整理。"),
                ],
            },
            {
                "icon": "🛡", "accent": COL_OK, "soft": COL_OK_SOFT,
                "title": t("help.safety_title", default="安全机制"),
                "items": [
                    t("help.safety_1", default="扫描只生成方案，绝不移动文件。"),
                    t("help.safety_2", default="正式整理前显示完整摘要，需要二次确认。"),
                    t("help.safety_3", default="文件夹默认 copy（复制），原文件保留在原处。"),
                    t("help.safety_4", default="日志与错误报告里的 API Key 会自动隐藏。"),
                    t("help.safety_5", default="每次整理都可在「整理桌面」页用“撤销”回退上一轮移动。"),
                ],
            },
            {
                "icon": "✦", "accent": COL_ACCENT, "soft": COL_ACCENT_SOFT,
                "title": t("help.models_title", default="模型模式（在「设置」里切换）"),
                "items": [
                    t("help.model_builtin", default="builtin：软件自带本地 AI，无需安装 Ollama 或填 API Key。"),
                    t("help.model_none", default="none：仅用规则分类，最快，完全不调用 AI。"),
                    t("help.model_ollama", default="ollama：连接本地 Ollama + Qwen 模型。"),
                    t("help.model_openai", default="openai_compatible：连接云端 OpenAI 兼容 API。"),
                ],
            },
            {
                "icon": "★", "accent": "#6366f1", "soft": "#eef2ff",
                "title": t("help.v3_title", default="v3.0 新功能"),
                "items": [
                    t("help.v3_queue", default="建议队列：开启“建议模式”后，扫描结果先累积成建议，审阅后再一次性执行，更安全。"),
                    t("help.v3_sources", default="多来源整理：除桌面外，可添加下载、文档、微信文件等目录一起整理。"),
                    t("help.v3_schedule", default="定时整理：在「设置 → 定时自动整理」配置 Windows 计划任务，到点自动运行。"),
                    t("help.v3_intent", default="意图输入：在「高级操作」页填写本次整理目的，AI 会优先参考你的意图。"),
                    t("help.v3_incremental", default="增量扫描：来源可设为“增量”，再次扫描时只处理新增文件。"),
                ],
            },
            {
                "icon": "☰", "accent": COL_TEXT_NAV, "soft": COL_HOVER,
                "title": t("help.pages_title", default="各页面导航"),
                "items": [
                    t("help.page_home", default="整理桌面：主流程（扫描 → 查看 → 确认整理）和状态自检。"),
                    t("help.page_suggestions", default="建议队列：查看并确认 AI 累积的整理建议。"),
                    t("help.page_review", default="整理方案：逐项查看/调整分类、启用或跳过。"),
                    t("help.page_settings", default="设置：模型、目标目录、整理来源、定时任务、语言、更新。"),
                    t("help.page_explanation", default="计划解释：方案摘要、风险项与建议。"),
                    t("help.page_memory", default="整理记忆：管理“关键词 → 分类”的自定义规则。"),
                    t("help.page_logs", default="运行日志：查看输出并生成诊断报告。"),
                    t("help.page_advanced", default="高级操作：单步执行各阶段命令、填写整理意图。"),
                ],
            },
        ]

    def _help_faqs(self):
        return [
            (
                t("help.faq_q1", default="提示模型没下载 / 没联网怎么办？"),
                t("help.faq_a1", default="可在「设置」把模型模式切到 none（仅规则）或 builtin（自带 AI），无需联网即可整理。"),
            ),
            (
                t("help.faq_q2", default="文件被分错类、移动错了怎么撤销？"),
                t("help.faq_a2", default="回到「整理桌面」页点“撤销”，会把上一轮移动的文件放回原位置；复制的文件夹不会被删除。"),
            ),
            (
                t("help.faq_q3", default="为什么扫描到了我没放在桌面的东西？"),
                t("help.faq_a3", default="Windows 桌面是“当前用户桌面 + 公用桌面(C:\\Users\\Public\\Desktop)”的合并视图，程序与系统保持一致。"),
            ),
            (
                t("help.faq_q4", default="“完整”和“增量”扫描有什么区别？"),
                t("help.faq_a4", default="完整：每次处理来源里的全部项目；增量：只处理上次扫描后新增的文件，适合下载、文档这类持续变化的目录。"),
            ),
            (
                t("help.faq_q5", default="建议模式和直接整理有什么不同？"),
                t("help.faq_a5", default="直接整理扫描后即生成方案；建议模式把结果先存入“建议队列”，你可以多次累积、审阅、调整后再统一执行。"),
            ),
        ]

    # --------------------------------------------------------------- renderers
    def _render_help_section(self, parent, row, section):
        card = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=14)
        card.grid(row=row, column=0, padx=4, pady=(0, 12), sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, padx=18, pady=(16, 6), sticky="ew")
        ctk.CTkLabel(head, text=section["icon"], font=ctk.CTkFont(size=18), text_color=section["accent"]).pack(side="left")
        ctk.CTkLabel(head, text=section["title"], font=ctk.CTkFont(size=15, weight="bold"), text_color=COL_TEXT).pack(side="left", padx=(10, 0))

        numbered = section.get("numbered", False)
        for idx, item in enumerate(section["items"], start=1):
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.grid(row=idx, column=0, padx=18, pady=2, sticky="ew")
            line.grid_columnconfigure(1, weight=1)
            bullet = f"{idx}." if numbered else "•"
            ctk.CTkLabel(line, text=bullet, font=ctk.CTkFont(size=13, weight="bold"), text_color=section["accent"], width=22).grid(row=0, column=0, sticky="nw")
            ctk.CTkLabel(line, text=item, font=ctk.CTkFont(size=13), text_color=COL_TEXT_NAV, anchor="w", justify="left", wraplength=720).grid(row=0, column=1, sticky="w")

        ctk.CTkFrame(card, fg_color="transparent", height=10).grid(row=len(section["items"]) + 1, column=0)
        return row + 1

    def _render_help_faq(self, parent, row):
        card = ctk.CTkFrame(parent, fg_color=COL_CARD, corner_radius=14)
        card.grid(row=row, column=0, padx=4, pady=(0, 12), sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, padx=18, pady=(16, 6), sticky="ew")
        ctk.CTkLabel(head, text="?", font=ctk.CTkFont(size=18, weight="bold"), text_color=COL_WARN).pack(side="left")
        ctk.CTkLabel(head, text=t("help.faq_title", default="常见问题"), font=ctk.CTkFont(size=15, weight="bold"), text_color=COL_TEXT).pack(side="left", padx=(10, 0))

        r = 1
        for question, answer in self._help_faqs():
            ctk.CTkLabel(card, text=question, font=ctk.CTkFont(size=13, weight="bold"), text_color=COL_TEXT, anchor="w", justify="left", wraplength=740).grid(row=r, column=0, padx=18, pady=(8, 1), sticky="w")
            ctk.CTkLabel(card, text=answer, font=ctk.CTkFont(size=12), text_color=COL_TEXT_MUTED, anchor="w", justify="left", wraplength=740).grid(row=r + 1, column=0, padx=18, pady=(0, 2), sticky="w")
            r += 2

        ctk.CTkFrame(card, fg_color="transparent", height=10).grid(row=r, column=0)
        return row + 1

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
