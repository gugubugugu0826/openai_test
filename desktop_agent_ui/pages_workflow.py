import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from desktop_agent.healthcheck import print_healthcheck
from desktop_agent.i18n import get_category_display, get_language
from desktop_agent.scanner import scan_desktop
from desktop_agent.planner import preview_plan
from desktop_agent.reviewer import create_human_review, learn_from_review
from desktop_agent.executor import dryrun_plan, apply_plan, undo_last_action
from desktop_agent.memory import show_memory
from desktop_agent.state import show_state
from desktop_agent.workflow import run_workflow
from desktop_agent_ui.utils import get_effective_scan_paths, format_scan_paths
from desktop_agent_ui.theme import *

OBSERVATION_FILE = Path("desktop_observation.json")
PLAN_FILE = Path("desktop_agent_plan.json")
REVIEW_FILE = Path("desktop_human_review.json")
ACTION_LOG_FILE = Path("desktop_action_log.json")


class WorkflowPageMixin:
    def _lang(self, zh, en):
        return en if get_language() == "en" else zh

    def build_advanced_page(self, parent):
        self.page_header(
            parent,
            "高级操作",
            self._lang("单步运行各阶段命令、查看中间文件、生成诊断报告。普通使用无需打开本页。", "Run each command step manually, inspect intermediate files, and generate diagnostics."),
        )

        body = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        # 文件状态卡
        status_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        status_card.grid(row=0, column=0, padx=6, pady=(6, 10), sticky="ew")
        status_card.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            status_card, text=self._lang("当前状态", "Status"), font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COL_TEXT,
        ).grid(row=0, column=0, columnspan=3, padx=16, pady=(14, 6), sticky="w")

        items = [
            ("provider", self._lang("当前模式", "Current Mode")),
            ("scan_path", self._lang("扫描路径", "Scan Path")),
            ("target_root", self._lang("目标目录", "Target Folder")),
            ("folder_mode", self._lang("文件夹模式", "Folder Mode")),
            ("observation", "Observation"),
            ("plan", "Plan"),
            ("review", "Review"),
            ("action_log", "Action Log"),
            ("current_log", self._lang("当前日志", "Current Log")),
        ]
        for idx, (key, label) in enumerate(items):
            row = (idx // 3) + 1
            col = idx % 3
            cell = ctk.CTkFrame(status_card, fg_color="transparent")
            cell.grid(row=row, column=col, padx=14, pady=8, sticky="w")
            ctk.CTkLabel(
                cell, text=label, font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COL_TEXT_MUTED,
            ).pack(anchor="w")
            var = tk.StringVar(value="-")
            self.dashboard_vars[key] = var
            ctk.CTkLabel(
                cell, textvariable=var, wraplength=240, justify="left",
                text_color=COL_TEXT, font=ctk.CTkFont(size=12),
            ).pack(anchor="w")

        ctk.CTkButton(
            status_card, text=self._lang("刷新", "Refresh"), width=90, height=32, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=COL_BORDER,
            text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
            command=self.update_dashboard,
        ).grid(row=4, column=0, padx=16, pady=(4, 14), sticky="w")

        # 单步命令卡
        cmd_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        cmd_card.grid(row=1, column=0, padx=6, pady=10, sticky="ew")
        ctk.CTkLabel(
            cmd_card, text=self._lang("单步命令", "Commands"), font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COL_TEXT,
        ).pack(anchor="w", padx=16, pady=(14, 6))

        grid = ctk.CTkFrame(cmd_card, fg_color="transparent")
        grid.pack(fill="x", padx=10, pady=(0, 14))

        commands = [
            (self._lang("环境自检", "Health Check"), lambda: self.run_command("check"), COL_ACCENT),
            (self._lang("扫描", "Scan"), lambda: self.run_command("scan"), COL_ACCENT),
            (self._lang("预览方案", "Preview"), lambda: self.run_command("preview"), COL_ACCENT),
            (self._lang("生成审核文件", "Create Review File"), lambda: self.run_command("review"), COL_ACCENT),
            (self._lang("运行全流程", "Run Workflow"), lambda: self.run_command("run"), COL_ACCENT),
            (self._lang("学习记忆", "Learn"), lambda: self.run_command("learn"), "#7c3aed"),
            (self._lang("预演整理", "Dry Run"), lambda: self.run_command("dryrun"), COL_WARN),
            (self._lang("继续预演", "Continue"), lambda: self.run_command("continue"), COL_WARN),
            (self._lang("正式整理", "Apply"), self.confirm_apply, COL_DANGER),
            (self._lang("撤销上次整理", "Undo"), self.confirm_undo, COL_DANGER),
            (self._lang("预估扫描范围", "Estimate Scan Scope"), self.show_scan_scope_estimate, "#0d9488"),
        ]
        for i, (text, cmd, color) in enumerate(commands):
            ctk.CTkButton(
                grid, text=text, width=150, height=36, corner_radius=8,
                fg_color=color, hover_color=color, command=cmd,
            ).grid(row=i // 4, column=i % 4, padx=6, pady=6, sticky="w")

        # 诊断 / 文件卡
        diag_card = ctk.CTkFrame(body, fg_color=COL_CARD, corner_radius=14)
        diag_card.grid(row=2, column=0, padx=6, pady=10, sticky="ew")
        ctk.CTkLabel(
            diag_card, text=self._lang("诊断 / 文件", "Diagnostics / Files"), font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COL_TEXT,
        ).pack(anchor="w", padx=16, pady=(14, 6))

        diag_row = ctk.CTkFrame(diag_card, fg_color="transparent")
        diag_row.pack(fill="x", padx=10, pady=(0, 14))
        for text, cmd in [
            (self._lang("生成错误报告包", "Create Diagnostic Report"), self.create_diagnostic_report),
            (self._lang("打开程序目录", "Open Project Folder"), self.open_project_folder),
            (self._lang("打开 logs 文件夹", "Open Logs Folder"), self.open_logs_folder),
            (self._lang("打开目标目录", "Open Target Folder"), self.open_target_folder),
            (self._lang("关于", "About"), self.show_about),
        ]:
            ctk.CTkButton(
                diag_row, text=text, height=36, corner_radius=8,
                fg_color="transparent", border_width=1, border_color=COL_BORDER,
                text_color=COL_TEXT_NAV, hover_color=COL_HOVER, command=cmd,
            ).pack(side="left", padx=6, pady=4)

        self.update_dashboard()

    def file_status_text(self, path: Path):
        if path.exists():
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                return f"{self._lang('存在', 'Exists')}\n{mtime}"
            except Exception:
                return self._lang("存在", "Exists")
        return self._lang("不存在", "Not Found")

    def update_dashboard(self):
        if not self.dashboard_vars:
            return
        try:
            config = self.read_config_safely()
            desktop_path = config.get("desktop_path", "").strip()
            scan_path = format_scan_paths(get_effective_scan_paths(desktop_path))

            values = {
                "provider": config.get("llm_provider", "unknown"),
                "scan_path": scan_path,
                "target_root": config.get("normal_target_root", ""),
                "folder_mode": config.get("folder_mode", ""),
                "observation": self.file_status_text(OBSERVATION_FILE),
                "plan": self.file_status_text(PLAN_FILE),
                "review": self.file_status_text(REVIEW_FILE),
                "action_log": self.file_status_text(ACTION_LOG_FILE),
                "current_log": str(self.current_log_file.name if self.current_log_file else "-"),
            }

            for key, value in values.items():
                if key in self.dashboard_vars:
                    self.dashboard_vars[key].set(value)
        except Exception as e:
            self.append_output(f"\n[GUI] {self._lang('状态刷新失败', 'Status refresh failed')}: {e}\n")

    # =====================================================
    # Logs Page
    # =====================================================

    def get_command_handler(self, command):
        def _gui_apply_confirm():
            return messagebox.askyesno(
                self._lang("未检测到审核文件", "Review file not found"),
                self._lang(
                    "没有找到人工审核文件 desktop_human_review.json。\n建议先执行 Review 步骤。\n\n仍然继续执行原始计划吗？",
                    "desktop_human_review.json was not found.\nIt is recommended to generate the review file first.\n\nContinue with the original plan anyway?",
                ),
            )

        handlers = {
            "check": print_healthcheck,
            "scan": scan_desktop,
            "preview": preview_plan,
            "review": create_human_review,
            "learn": learn_from_review,
            "dryrun": dryrun_plan,
            "apply": lambda: apply_plan(confirm_callback=_gui_apply_confirm),
            "undo": undo_last_action,
            "memory": show_memory,
            "state": show_state,
            "run": run_workflow,
        }
        return handlers.get(command)

    def run_command(self, command, guided=False, on_done=None, busy_text=None):
        if self.running:
            messagebox.showwarning(self._lang("正在运行", "Already Running"), self._lang("当前已有任务在运行，请等待完成。", "Another task is already running. Please wait for it to finish."))
            return

        if command in ["scan", "run"]:
            if not self.confirm_scan_safety():
                return

        if command != "continue" and self.get_command_handler(command) is None:
            messagebox.showerror(self._lang("错误", "Error"), f"{self._lang('未知命令', 'Unknown command')}: {command}")
            return

        self.running = True
        self.status_var.set(f"{self._lang('运行中', 'Running')}: {command}")
        self.guided_on_done = on_done

        if guided:
            self._open_progress_modal(busy_text or "正在处理…")
        else:
            self.show_page("Logs")

        header = (
            f"\n{'=' * 90}\n"
            f"Running Agent command: {command}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'=' * 90}\n"
        )
        self.append_output(header)

        thread = threading.Thread(
            target=self.worker_run_command,
            args=(command,),
            daemon=True,
        )
        thread.start()

    def worker_run_command(self, command):
        try:
            writer = QueueWriter(self.output_queue)

            with redirect_stdout(writer), redirect_stderr(writer):
                if command == "continue":
                    print("=" * 80)
                    print("GUI Continue Workflow")
                    print("=" * 80)
                    print("将执行：learn -> dryrun")
                    print("注意：GUI 版 continue 不会自动 apply。")
                    print("=" * 80)

                    learn_from_review()
                    dryrun_plan()

                    print("\nGUI continue 阶段完成。")
                    print("确认预演无误后，请点击 Apply 正式执行。")
                else:
                    handler = self.get_command_handler(command)
                    handler()

            self.output_queue.put("\n[Process finished with code 0]\n")
        except Exception as e:
            self.output_queue.put(f"\n[GUI Error] {e}\n")
            self.output_queue.put("\n[Process finished with code 1]\n")
        finally:
            self.output_queue.put("__TASK_DONE__")

    def poll_output_queue(self):
        try:
            while True:
                msg = self.output_queue.get_nowait()

                if msg == "__TASK_DONE__":
                    self.running = False
                    self.status_var.set(self._lang("就绪", "Ready"))
                    on_done = self.guided_on_done
                    self.guided_on_done = None
                    self._close_progress_modal()
                    self.update_home_summary()
                    self.update_dashboard()
                    self.load_plan_explanation_panel()
                    if on_done:
                        try:
                            on_done()
                        except Exception as e:
                            messagebox.showerror(self._lang("操作失败", "Operation Failed"), str(e))
                    else:
                        self.refresh_home_status()
                    continue

                self.append_output(msg)

                # 引导弹窗里实时显示“最新一行”，不再把用户甩进黑色终端
                if self.guided_status_var is not None:
                    line = msg.strip()
                    if line:
                        self._last_output_line = line[-120:]
                        try:
                            self.guided_status_var.set(self._last_output_line)
                        except Exception:
                            pass
        except queue.Empty:
            pass

        self.root.after(100, self.poll_output_queue)

    # =====================================================
    # Guided Progress Modal
    # =====================================================

    def _open_progress_modal(self, busy_text):
        self._close_progress_modal()

        modal = ctk.CTkToplevel(self.root)
        modal.title(self._lang("请稍候", "Please Wait"))
        modal.geometry("440x210")
        modal.transient(self.root)
        modal.resizable(False, False)
        try:
            modal.grab_set()
        except Exception:
            pass

        self.root.update_idletasks()
        try:
            x = self.root.winfo_rootx() + (self.root.winfo_width() - 440) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - 210) // 2
            modal.geometry(f"440x210+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass

        ctk.CTkLabel(
            modal, text=busy_text, font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COL_TEXT, wraplength=400, justify="left",
        ).pack(padx=22, pady=(24, 12), anchor="w")

        pb = ctk.CTkProgressBar(modal, width=396, mode="indeterminate")
        pb.pack(padx=22, pady=(0, 12))
        pb.start()
        self.guided_pb = pb

        self.guided_status_var = tk.StringVar(value=self._lang("正在准备…", "Preparing..."))
        ctk.CTkLabel(
            modal, textvariable=self.guided_status_var, font=ctk.CTkFont(size=12),
            text_color=COL_TEXT_MUTED, wraplength=400, justify="left", anchor="w",
        ).pack(padx=22, pady=(0, 10), anchor="w", fill="x")

        ctk.CTkButton(
            modal, text=self._lang("转到后台（查看详细日志）", "Send to Background"), height=34, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=COL_BORDER,
            text_color=COL_TEXT_NAV, hover_color=COL_HOVER,
            command=self._detach_guided,
        ).pack(padx=22, pady=(0, 16), anchor="e")

        self.guided_modal = modal

    def _close_progress_modal(self):
        if self.guided_pb is not None:
            try:
                self.guided_pb.stop()
            except Exception:
                pass
            self.guided_pb = None
        if self.guided_modal is not None:
            try:
                self.guided_modal.grab_release()
            except Exception:
                pass
            try:
                self.guided_modal.destroy()
            except Exception:
                pass
            self.guided_modal = None
        self.guided_status_var = None

    def _detach_guided(self):
        # 用户选择“转到后台”：关弹窗、取消自动跳转，任务继续，输出在「运行日志」里
        self.guided_on_done = None
        self._close_progress_modal()
        self.show_page("Logs")

    # =====================================================
    # Scan Safety
    # =====================================================

    def estimate_scan_scope(self):
        try:
            config = self.read_config_safely()
            desktop_path = config.get("desktop_path", "").strip()
            scan_paths = get_effective_scan_paths(desktop_path)

            total = folders = files = shortcuts = others = 0
            missing_paths = []

            for scan_path in scan_paths:
                if not scan_path.exists() or not scan_path.is_dir():
                    missing_paths.append(str(scan_path))
                    continue

                for item in scan_path.iterdir():
                    total += 1
                    if item.is_dir():
                        folders += 1
                    elif item.is_file():
                        files += 1
                        if item.suffix.lower() in [".lnk", ".url"]:
                            shortcuts += 1
                    else:
                        others += 1

            if missing_paths:
                return {
                    "ok": False,
                    "path": format_scan_paths(scan_paths),
                    "message": self._lang(
                        "扫描路径不存在或不是文件夹：" + ", ".join(missing_paths),
                        "Scan path not found or is not a folder: " + ", ".join(missing_paths)
                    ),
                }

            return {
                "ok": True,
                "path": format_scan_paths(scan_paths),
                "paths": [str(path) for path in scan_paths],
                "total": total,
                "folders": folders,
                "files": files,
                "shortcuts": shortcuts,
                "others": others,
            }
        except Exception as e:
            return {
                "ok": False,
                "path": "",
                "message": str(e),
            }

    def confirm_scan_safety(self):
        scope = self.estimate_scan_scope()

        if not scope:
            return True

        if not scope.get("ok"):
            return messagebox.askyesno(
                self._lang("扫描路径检查失败", "Scan Path Check Failed"),
                self._lang(f"无法预估扫描范围：{scope.get('message')}\n\n仍然继续吗？", f"Could not estimate the scan scope: {scope.get('message')}\n\nContinue anyway?")
            )

        if get_language() == "en":
            self.append_output(
                "\n[GUI] Scan scope estimate:\n"
                f"Path: {scope['path']}\n"
                f"Top-level items: {scope['total']}\n"
                f"Folders: {scope['folders']}\n"
                f"Files: {scope['files']}\n"
                f"Shortcuts: {scope['shortcuts']}\n"
                f"Other: {scope['others']}\n"
            )
        else:
            self.append_output(
                "\n[GUI] 扫描范围预估：\n"
                f"路径：{scope['path']}\n"
                f"第一层项目：{scope['total']} 个\n"
                f"文件夹：{scope['folders']} 个\n"
                f"文件：{scope['files']} 个\n"
                f"快捷方式：{scope['shortcuts']} 个\n"
                f"其他：{scope['others']} 个\n"
            )

        if scope["total"] >= 300:
            return messagebox.askyesno(
                self._lang("扫描项目较多", "Large Scan Scope"),
                self._lang(
                    f"当前扫描路径第一层项目较多：{scope['total']} 个。\n\n路径：{scope['path']}\n\n这可能需要较长时间。\n\n仍然继续吗？",
                    f"The scan path has {scope['total']} top-level items.\n\nPath: {scope['path']}\n\nThis may take a while.\n\nContinue anyway?"
                )
            )

        return True

    def show_scan_scope_estimate(self):
        scope = self.estimate_scan_scope()

        if not scope or not scope.get("ok"):
            messagebox.showerror(self._lang("预估失败", "Estimate Failed"), str(scope))
            return

        if get_language() == "en":
            message = (
                f"Scan path:\n{scope['path']}\n\n"
                f"Top-level items: {scope['total']}\n"
                f"Folders: {scope['folders']}\n"
                f"Files: {scope['files']}\n"
                f"Shortcuts: {scope['shortcuts']}\n"
                f"Other: {scope['others']}"
            )
        else:
            message = (
                f"扫描路径：\n{scope['path']}\n\n"
                f"第一层项目：{scope['total']} 个\n"
                f"文件夹：{scope['folders']} 个\n"
                f"文件：{scope['files']} 个\n"
                f"快捷方式：{scope['shortcuts']} 个\n"
                f"其他：{scope['others']} 个"
            )

        messagebox.showinfo(self._lang("扫描范围预估", "Scan Scope Estimate"), message)
        self.append_output("\n[GUI] " + message + "\n")

    # =====================================================
    # Apply Summary / Confirm
    # =====================================================

    def load_items_for_apply_summary(self):
        if REVIEW_FILE.exists():
            try:
                with open(REVIEW_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("items", []), "desktop_human_review.json"
            except Exception:
                pass

        if PLAN_FILE.exists():
            try:
                with open(PLAN_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("items", []), "desktop_agent_plan.json"
            except Exception:
                pass

        return [], "无"

    def build_apply_summary(self):
        config = self.read_config_safely()
        target_root = config.get("normal_target_root", "")
        folder_mode = config.get("folder_mode", "")

        items, source = self.load_items_for_apply_summary()

        enabled_items = [item for item in items if item.get("enabled", True)]
        skipped_items = [item for item in items if not item.get("enabled", True)]

        type_counts = {"file": 0, "folder": 0, "shortcut": 0, "other": 0}
        category_counts = {}

        for item in enabled_items:
            item_type = item.get("type", "other")
            if item_type not in type_counts:
                item_type = "other"
            type_counts[item_type] += 1

            category = item.get("human_category") or item.get("category") or item.get("ai_category") or "无法判断"
            category_counts[category] = category_counts.get(category, 0) + 1

        if get_language() == "en":
            category_text = "\n".join(
                [f"- {get_category_display(cat)}: {count}" for cat, count in sorted(category_counts.items())]
            ) or "- None"
            summary = (
                "About to run Apply.\n\n"
                f"Source: {source}\n"
                f"Target folder: {target_root}\n"
                f"folder_mode: {folder_mode}\n\n"
                f"Enabled: {len(enabled_items)}\n"
                f"Skipped: {len(skipped_items)}\n"
                f"Files: {type_counts['file']}\n"
                f"Folders: {type_counts['folder']}\n"
                f"Shortcuts: {type_counts['shortcut']}\n"
                f"Other: {type_counts['other']}\n\n"
                f"Category summary:\n{category_text}\n\n"
                "Confirm to start organizing."
            )
        else:
            category_text = "\n".join(
                [f"- {cat}: {count}" for cat, count in sorted(category_counts.items())]
            ) or "- 无"
            summary = (
                "即将执行整理（Apply）。\n\n"
                f"数据来源：{source}\n"
                f"整理目标目录：{target_root}\n"
                f"folder_mode：{folder_mode}\n\n"
                f"启用项目：{len(enabled_items)}\n"
                f"跳过项目：{len(skipped_items)}\n"
                f"普通文件：{type_counts['file']}\n"
                f"文件夹：{type_counts['folder']}\n"
                f"快捷方式：{type_counts['shortcut']}\n"
                f"其他类型：{type_counts['other']}\n\n"
                f"分类摘要：\n{category_text}\n\n"
                "确认后会正式整理文件。"
            )

        return {
            "summary": summary,
            "enabled_count": len(enabled_items),
        }

    def confirm_apply(self):
        summary_data = self.build_apply_summary()
        enabled_count = summary_data["enabled_count"]
        summary = summary_data["summary"]

        if enabled_count == 0:
            if not messagebox.askyesno(self._lang("没有启用项目", "No Enabled Items"), self._lang("当前没有启用项目，仍然尝试 Apply 吗？", "There are no enabled items. Try Apply anyway?")):
                return

        if enabled_count >= 200:
            if not messagebox.askyesno(
                self._lang("大量项目执行警告", "Large Execution Warning"),
                self._lang(
                    f"当前启用项目数量为 {enabled_count} 个。\n\n是否继续查看最终执行摘要？",
                    f"There are {enabled_count} enabled items.\n\nContinue to the final summary?"
                )
            ):
                return

        if messagebox.askyesno(self._lang("整理二次确认", "Final Apply Confirmation"), summary):
            self.append_output("\n[GUI] 用户确认 Apply。执行摘要：\n")
            self.append_output(summary + "\n")
            self.run_command(
                "apply",
                guided=True,
                busy_text=self._lang("正在整理文件…\n请稍候，不要关闭程序。", "Organizing files...\nPlease wait — do not close the app."),
                on_done=self._after_apply_done,
            )
        else:
            self.append_output("\n[GUI] 用户取消 Apply。\n")

    def confirm_undo(self):
        if messagebox.askyesno(
            self._lang("确认撤销", "Confirm Undo"),
            self._lang("Undo 会根据上一次 action log 尝试撤销被移动的项目。\n\n确认撤销吗？", "Undo will use the latest action log to restore moved items when possible.\n\nContinue?")
        ):
            self.run_command("undo")

    # =====================================================
    # Review Logic
    # =====================================================
