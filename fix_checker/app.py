"""Main window: sidebar, page switching, event pump."""
from __future__ import annotations

import queue
import os
import time
import webbrowser
from dataclasses import asdict
from typing import Optional

import customtkinter as ctk

from .agent_runner import BrowserAgentRunner
from .config import C, FONT, HISTORY_FILE, SETTINGS_FILE, TASKS_FILE
from .git_monitor import GitMonitor
from .models import DEFAULT_TASKS, RegressionTask, RunRecord, load_json, save_json, time_ago
from .page_home import HomePageMixin
from .page_run import RunPageMixin
from .page_tasks_settings import TasksSettingsMixin
from .widgets import card, label, primary_btn

PAGES = ("Home & Setup", "Regression Tasks", "Run Agent", "Run History")


class DeveloperAppUI(HomePageMixin, RunPageMixin, TasksSettingsMixin, ctk.CTk):
    """FixGuard: runs an AI browser test after every commit."""

    REFRESH = {
        "Home & Setup": "refresh_settings",
        "Run History": "refresh_home",
        "Run Agent": "refresh_run",
        "Regression Tasks": "refresh_tasks",
    }

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("FixGuard")
        width = max(1080, min(1280, self.winfo_screenwidth() - 80))
        height = max(700, min(820, self.winfo_screenheight() - 100))
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2 - 30)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(1080, 700)
        self.configure(fg_color=C["bg"])

        self.settings = self._load_settings()
        self.tasks = self._load_tasks()
        self.history = self._load_history()
        self.current: Optional[RunRecord] = None
        self.active_run: Optional[RunRecord] = None
        self.pending_runs = []
        self.run_task_queue = []
        self.ui_events = queue.Queue()
        self.runner = BrowserAgentRunner()
        self.monitor = GitMonitor(self.on_commit)

        self._build_shell()
        self._build_pages()
        self.show_page("Home & Setup")
        if self.settings.get("repo_path"):
            self.monitor.start(self.settings["repo_path"])
        self.after(200, self._pump)
        self.after(60_000, self._refresh_periodic)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- stored state ------------------------------------------------------
    @staticmethod
    def _defaults() -> dict:
        return {
            "openai_key": "",
            "skyvern_key": "",
            "model": "gpt-6-luna",
            "base_url": "http://localhost:3000",
            "repo_path": "",
            "auto_run": True,
            "engine": "skyvern",
            "show_browser": False,
        }

    def _load_settings(self) -> dict:
        merged = self._defaults()
        data = load_json(SETTINGS_FILE, {})
        if isinstance(data, dict):
            merged.update(data)
        for obsolete in ("target_path", "test_current_fix", "fix_text"):
            merged.pop(obsolete, None)
        merged["openai_key"] = merged.get("openai_key") or os.getenv("OPENAI_API_KEY", "")
        merged["skyvern_key"] = merged.get("skyvern_key") or os.getenv("SKYVERN_API_KEY", "")
        return merged

    def _load_tasks(self) -> list:
        data = load_json(TASKS_FILE, None)
        tasks = []
        if isinstance(data, list):
            for row in data:
                try:
                    tasks.append(RegressionTask(**{key: value for key, value in row.items() if key != "path"}))
                except (AttributeError, TypeError):
                    continue
        return tasks if isinstance(data, list) else [RegressionTask(**asdict(t)) for t in DEFAULT_TASKS]

    def _load_history(self) -> list:
        data = load_json(HISTORY_FILE, [])
        history = []
        if isinstance(data, list):
            for row in data:
                try:
                    record = RunRecord(**row)
                    if record.status == "running":
                        record.status = "failed"
                        record.report = {"status": "FAILED", "error_details": "Application closed during this run."}
                    history.append(record)
                except TypeError:
                    continue
        return history

    def save_state(self) -> None:
        save_json(SETTINGS_FILE, self.settings)
        save_json(TASKS_FILE, [asdict(t) for t in self.tasks])
        save_json(HISTORY_FILE, [asdict(r) for r in self.history[:50]])

    # -- shell -------------------------------------------------------------
    def _build_shell(self) -> None:
        sidebar = ctk.CTkFrame(self, width=260, fg_color=C["panel"], corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(18, 10))
        ctk.CTkLabel(
            brand, text="◆", text_color=C["accent"], font=(FONT, 20, "bold")
        ).pack(side="left")
        label(brand, "FixGuard", size=20, bold=True).pack(side="left", padx=8)
        label(sidebar, "Confidence after every change.", size=12, color=C["muted"]).pack(
            anchor="w", padx=22, pady=(0, 22)
        )
        label(sidebar, "YOUR WORKFLOW", size=10, color=C["muted"], bold=True).pack(
            anchor="w", padx=22, pady=(0, 8)
        )

        self.nav = {}
        for name in PAGES:
            btn = ctk.CTkButton(
                sidebar,
                text=name,
                anchor="w",
                fg_color="transparent",
                hover_color=C["card_hover"],
                text_color=C["muted"],
                font=(FONT, 14),
                corner_radius=8,
                height=40,
                command=lambda n=name: self.show_page(n),
            )
            btn.pack(fill="x", padx=14, pady=2)
            self.nav[name] = btn

        hist_card = card(sidebar)
        label(hist_card, "Recent runs", size=12, color=C["muted"], bold=True).pack(
            anchor="w", padx=12, pady=(10, 4)
        )
        self.hist_list = ctk.CTkScrollableFrame(hist_card, fg_color="transparent", height=100)
        self.hist_list.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        ai = card(sidebar)
        ai.pack(side="bottom", fill="x", padx=14, pady=(0, 14))
        label(ai, "TEST AGENT", size=10, color=C["muted"], bold=True).pack(
            anchor="w", padx=12, pady=(10, 0)
        )
        model = "Skyvern" if self.settings["engine"] == "skyvern" else "browser-use"
        self.ai_model = label(ai, model, size=13, bold=True)
        self.ai_model.pack(anchor="w", padx=12)
        primary_btn(ai, "Test latest commit", self.test_latest).pack(
            fill="x", padx=12, pady=(8, 12)
        )
        hist_card.pack(fill="both", expand=True, padx=14, pady=(14, 8))

        main = ctk.CTkFrame(self, fg_color=C["bg"])
        main.pack(side="left", fill="both", expand=True)

        top = ctk.CTkFrame(main, height=52, fg_color=C["bg"], corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)
        self.page_title = label(top, "Home & Setup", size=17, bold=True)
        self.page_title.pack(side="left", padx=22)
        self.sync_dot = label(top, "", size=12, color=C["muted"])
        self.sync_dot.pack(side="right", padx=22)

        self.container = ctk.CTkFrame(main, fg_color=C["bg"])
        self.container.pack(fill="both", expand=True)

    def _build_pages(self) -> None:
        self.pages = {name: ctk.CTkFrame(self.container, fg_color=C["bg"]) for name in PAGES}
        self._build_home(self.pages["Run History"])
        self._build_run(self.pages["Run Agent"])
        self._build_tasks(self.pages["Regression Tasks"])
        self._build_settings(self.pages["Home & Setup"])
        self.refresh_history()

    def show_page(self, name: str) -> None:
        for child in self.container.winfo_children():
            child.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        self.page_title.configure(text=name)
        for n, btn in self.nav.items():
            btn.configure(
                fg_color=C["card"] if n == name else "transparent",
                text_color=C["text"] if n == name else C["muted"],
            )
        method = getattr(self, self.REFRESH[name], None)
        if method:
            method()
        self.refresh_journey()

    # -- events ------------------------------------------------------------
    def _refresh_periodic(self) -> None:
        if getattr(self, "_closing", False):
            return
        self.refresh_history()
        self.after(60_000, self._refresh_periodic)

    def _pump(self) -> None:
        if getattr(self, "_closing", False):
            return
        try:
            for _ in range(100):
                self._handle_step(self.runner.steps.get_nowait())
        except queue.Empty:
            pass
        try:
            for _ in range(20):
                sha, message = self.ui_events.get_nowait()
                self._record_commit(sha, message)
        except queue.Empty:
            pass
        if self.active_run is None and not self.runner.busy and self.pending_runs:
            self.launch_agent(self.pending_runs.pop(0))
        self.after(200, self._pump)

    def _handle_step(self, item: dict) -> None:
        kind = item.get("kind")
        if kind == "log":
            self._append_log(item.get("text", ""))
        elif kind == "error":
            self._append_log(f"ERROR: {item.get('text', '')}")
        elif kind == "task_queue":
            self.run_task_queue = item["tasks"]
            self.refresh_run()
        elif kind == "task_result" and self.active_run is not None:
            self.active_run.report.setdefault("task_results", []).append(item["result"])
            self.active_run.report["total_tasks"] = item["total"]
            self._show_result(self.active_run)
            self.save_state()
        elif kind == "browser_view":
            url = item.get("url", "")
            self._append_log(f"Live browser: {url}")
            try:
                if not webbrowser.open_new_tab(url):
                    self._append_log("Open the live browser URL above to watch the run.")
            except Exception as exc:
                self._append_log(f"Could not open live browser: {exc}. Open the URL above.")
        elif kind == "done":
            self._finish_run(item.get("report"))

    def on_commit(self, sha: str, message: str) -> None:
        """Called from the monitor thread; marshal onto the UI thread."""
        self.ui_events.put((sha, message))

    def _record_commit(self, sha: str, message: str) -> None:
        rec = RunRecord(
            title=message,
            description=f"{sum(task.enabled for task in self.tasks)} regression task(s)",
            commit=sha,
            path=self.settings.get("base_url") or "http://localhost:3000",
            status="queued",
            tag="commit",
        )
        self.history.insert(0, rec)
        self.current = rec
        if self.settings.get("auto_run"):
            self.pending_runs.append(rec)
        self.refresh_history()
        self.save_state()

    def test_latest(self) -> None:
        if self.active_run is not None or self.runner.busy:
            self._append_log("A test is already running. Wait for it to finish or cancel it.")
            self.show_page("Run Agent")
            return
        info = self.monitor.current()
        if info:
            sha, subject = info
            rec = RunRecord(
                title=subject, description="Manual run", commit=sha, status="queued", tag="manual"
            )
            self.history.insert(0, rec)
            self.current = rec
            self.refresh_history()
            self.launch_agent(rec)
        else:
            self._append_log("Choose a Git repository in Home & Setup to test its latest commit.")
            self.show_page("Home & Setup")
            self.settings_note.configure(text="Choose and save a Git repository to test its latest commit.")

    def _finish_run(self, report) -> None:
        rec = self.active_run
        if rec is None:
            return
        rec.finished = time.time()
        if report is None:
            rec.status = "failed"
            rec.report = {"status": "failed", "error_details": "Agent could not complete the run."}
        else:
            rec.status = getattr(report, "status", "failed").lower()
            rec.report = (
                report.model_dump() if hasattr(report, "model_dump") else dict(report.__dict__)
            )
        self.active_run = None
        self.run_task_queue = []
        self.save_state()
        self.refresh_history()
        self._show_result(rec)
        self.refresh_run()

    def move_pending_run(self, run_id, direction) -> None:
        index = next((i for i, run in enumerate(self.pending_runs) if run.id == run_id), -1)
        destination = index + direction
        if index >= 0 and 0 <= destination < len(self.pending_runs):
            self.pending_runs[index], self.pending_runs[destination] = (
                self.pending_runs[destination], self.pending_runs[index])
            self.refresh_home()

    def refresh_history(self) -> None:
        if not hasattr(self, "hist_list"):
            return
        for child in self.hist_list.winfo_children():
            child.destroy()
        for rec in self.history[:12]:
            row = ctk.CTkFrame(self.hist_list, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=2)
            label(row, (rec.title or rec.commit[:7] or "untitled")[:26], size=12).pack(
                side="left"
            )
            label(row, time_ago(rec.started), size=11, color=C["muted"]).pack(side="right")
        self.refresh_home()
        self.refresh_journey()

    # -- shutdown ----------------------------------------------------------
    def _on_close(self) -> None:
        if getattr(self, "_closing", False):
            return
        self._closing = True
        self.settings["show_browser"] = bool(self.run_headless.get())
        self.save_state()
        self.monitor.stop()
        self.runner.close()
        self.withdraw()
        self._await_shutdown()

    def _await_shutdown(self) -> None:
        if getattr(self, "_shutdown_complete", False):
            return
        if self.runner.thread.is_alive():
            self.after(50, self._await_shutdown)
        else:
            for callback in self.tk.call("after", "info"):
                self.tk.call("after", "cancel", callback)
            self._shutdown_complete = True
            self.destroy()
