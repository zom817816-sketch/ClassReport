"""Small teacher-facing GUI for the packaged report generator."""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk

from .cli import main as cli_main
from .feishu import DEFAULT_BASE_URL, parse_base_token, read_project_env


def application_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


class TeacherApp:
    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.root = application_root()
        self.messages: queue.Queue[str | None] = queue.Queue()
        self.running = False
        try:
            self.config = read_project_env(self.root)
            self.config_error = ""
        except (FileNotFoundError, ValueError) as error:
            self.config = {}
            self.config_error = str(error)

        default_token = self.config.get("FEISHU_APP_TOKEN") or parse_base_token(DEFAULT_BASE_URL)
        self.initial_access_token = self.config.get("USER_ACCESS_TOKEN", "")
        self.initial_app_token = default_token
        self.access_token = tk.StringVar(value=self.initial_access_token)
        self.app_token = tk.StringVar(value=default_token)
        self.teacher = tk.StringVar(value="毛远老师")
        self.report_date = tk.StringVar(value=date.today().isoformat())

        self.window.title("课情报告生成器")
        self.window.geometry("700x560")
        self.window.minsize(640, 500)
        self._build()
        self._drain_messages()
        if self.config_error:
            self._append(f"配置提示：{self.config_error}\n")
        else:
            self._append("已加载内置飞书配置，可直接生成报告。\n")

    def _build(self) -> None:
        container = ttk.Frame(self.window, padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="课情报告生成器", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        ttk.Label(container, text="内置默认凭据；令牌过期或切换多维表格时可在下方更新。", foreground="#666666").pack(anchor="w", pady=(3, 14))

        form = ttk.Frame(container)
        form.pack(fill="x")
        self._field(form, 0, "飞书用户令牌", self.access_token, show="•")
        self._field(form, 1, "多维表格 app_token", self.app_token)
        self._field(form, 2, "指导老师", self.teacher)
        self._field(form, 3, "报告日期", self.report_date)
        ttk.Label(form, text="app_token 是 Base 链接中 /base/ 后的那段字符串。", foreground="#666666").grid(row=4, column=1, sticky="w", pady=(0, 12))

        buttons = ttk.Frame(container)
        buttons.pack(fill="x", pady=(2, 10))
        self.test_button = ttk.Button(buttons, text="测试飞书连接", command=lambda: self._run(sync_only=True))
        self.test_button.pack(side="left")
        self.generate_button = ttk.Button(buttons, text="下载并生成报告", command=lambda: self._run(sync_only=False))
        self.generate_button.pack(side="left", padx=10)
        ttk.Button(buttons, text="打开输出目录", command=self._open_output).pack(side="left")

        ttk.Label(container, text="运行日志").pack(anchor="w")
        self.log = tk.Text(container, height=16, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True)

    @staticmethod
    def _field(parent: ttk.Frame, row: int, label: str, value: tk.StringVar, show: str | None = None) -> None:
        ttk.Label(parent, text=label, width=18).grid(row=row, column=0, sticky="w", pady=5)
        entry = ttk.Entry(parent, textvariable=value, show=show or "")
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        parent.columnconfigure(1, weight=1)

    def _append(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _save_overrides(self) -> bool:
        token = self.access_token.get().strip()
        app_token = self.app_token.get().strip()
        if not token and not (self.config.get("APP_ID") and self.config.get("APP_SECRET")):
            messagebox.showerror("缺少凭据", "请填写飞书用户令牌。")
            return False
        if not app_token.isalnum():
            messagebox.showerror("app_token 无效", "请填写多维表格链接中的 app_token。")
            return False
        if token == self.initial_access_token and app_token == self.initial_app_token:
            return True
        override = self.root / "ClassReportGenerator.config.env"
        override.write_text(
            f"USER_ACCESS_TOKEN={token}\nFEISHU_APP_TOKEN={app_token}\n",
            encoding="utf-8",
        )
        self.config["USER_ACCESS_TOKEN"] = token
        self.initial_access_token = token
        self.initial_app_token = app_token
        self._append("已保存本机配置更新。\n")
        return True

    def _command(self, sync_only: bool) -> list[str]:
        base_url = f"https://xinzhoujy.feishu.cn/base/{self.app_token.get().strip()}"
        cli_args = ["--root", str(self.root), "--sync-feishu", "--feishu-url", base_url]
        if sync_only:
            cli_args.append("--sync-only")
        else:
            cli_args.extend(["--date", self.report_date.get().strip(), "--teacher", self.teacher.get().strip()])
        return cli_args

    def _run(self, sync_only: bool) -> None:
        if self.running or not self._save_overrides():
            return
        self.running = True
        self.test_button.configure(state="disabled")
        self.generate_button.configure(state="disabled")
        self._append("\n开始运行，请勿关闭窗口……\n")
        command = self._command(sync_only)
        threading.Thread(target=self._worker, args=(command,), daemon=True).start()

    def _worker(self, command: list[str]) -> None:
        class QueueWriter:
            def __init__(self, messages: queue.Queue[str | None]) -> None:
                self.messages = messages

            def write(self, text: str) -> int:
                if text:
                    self.messages.put(text)
                return len(text)

            def flush(self) -> None:
                return None

        stream = QueueWriter(self.messages)
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                cli_main(command)
            self.messages.put("\n运行完成。\n")
        except SystemExit as error:
            message = error.code if isinstance(error.code, str) else "运行失败，请根据上方提示处理。"
            self.messages.put(f"\n{message}\n")
        except Exception as error:
            self.messages.put(f"\n运行失败：{error}\n")
        finally:
            self.messages.put(None)

    def _drain_messages(self) -> None:
        try:
            while True:
                message = self.messages.get_nowait()
                if message is None:
                    self.running = False
                    self.test_button.configure(state="normal")
                    self.generate_button.configure(state="normal")
                else:
                    self._append(message)
        except queue.Empty:
            pass
        self.window.after(120, self._drain_messages)

    def _open_output(self) -> None:
        output = self.root / "output"
        if output.exists():
            os.startfile(output)
        else:
            messagebox.showinfo("尚无输出", "请先下载并生成报告。")


def launch() -> None:
    window = tk.Tk()
    TeacherApp(window)
    window.mainloop()
