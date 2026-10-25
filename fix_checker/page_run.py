"""Run Agent page: inputs, live log, result cards, launching."""
from __future__ import annotations

import customtkinter as ctk

from .config import C, FONT, MONO, STATUS_COLORS
from .models import RunRecord
from .widgets import card, ghost_btn, label, pill, primary_btn


class RunPageMixin:
    """Regression task queue, live steps and result panel."""

    def _build_run(self, parent) -> None:
        intro = ctk.CTkFrame(parent, fg_color="transparent")
        intro.pack(fill="x", padx=22, pady=(10, 0))
        label(intro, "Run a check on the flows that matter", size=18, bold=True).pack(anchor="w")
        self.run_destination = label(intro, "", size=11, color=C["muted"], anchor="w", justify="left", wraplength=700)
        self.run_destination.pack(fill="x", pady=(2, 0))
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(22, 10), pady=16)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1, minsize=220)
        left.grid_rowconfigure(3, weight=1, minsize=200)
        right = ctk.CTkFrame(parent, fg_color="transparent", width=360)
        right.pack(side="right", fill="y", padx=(0, 22), pady=16)
        right.pack_propagate(False)

        regs = card(left)
        regs.grid(row=0, column=0, sticky="nsew")
        head = ctk.CTkFrame(regs, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(10, 4))
        self.run_selection_note = label(head, "Choose regression tasks", size=12, color=C["muted"], bold=True)
        self.run_selection_note.pack(side="left")
        ghost_btn(head, "Manage tasks", lambda: self.show_page("Regression Tasks"), width=110).pack(
            side="right"
        )
        self.run_checks = ctk.CTkScrollableFrame(regs, fg_color="transparent", height=220)
        self.run_checks.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        opts = ctk.CTkFrame(left, fg_color="transparent")
        opts.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.run_headless = ctk.CTkSwitch(
            opts,
            text="Show browser live",
            font=(FONT, 12),
            text_color=C["text"],
            progress_color=C["accent"],
            command=self._save_browser_visibility,
        )
        self.run_headless.pack(side="left")
        if self.settings.get("show_browser"):
            self.run_headless.select()
        self.run_cancel = ghost_btn(opts, "Stop run", self.runner.cancel, width=75, state="disabled")
        self.run_cancel.pack(side="right", padx=4)
        self.run_start = primary_btn(opts, "Run selected tasks", lambda: self.launch_agent(), width=145)
        self.run_start.pack(side="right")
        self.browser_note = label(left, "", size=11, color=C["muted"], anchor="w", justify="left", wraplength=350)
        self.browser_note.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        log = card(left)
        log.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        label(log, "Live activity", size=12, color=C["muted"], bold=True).pack(
            anchor="w", padx=12, pady=(10, 2)
        )
        self.run_log = ctk.CTkTextbox(
            log, fg_color=C["panel"], text_color=C["muted"], font=(MONO, 11), state="disabled"
        )
        self.run_log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.result_card = card(right)
        self.result_card.pack(fill="x")
        label(self.result_card, "RUN RESULT", size=10, color=C["muted"], bold=True).pack(
            anchor="w", padx=14, pady=(14, 0))
        self.result_title = label(self.result_card, "Ready when you are", size=22, bold=True)
        self.result_title.pack(anchor="w", padx=14, pady=(14, 6))
        self.result_pill = pill(self.result_card, "queued")
        self.result_pill.configure(text="NOT STARTED", fg_color=C["border"], text_color=C["muted"])
        self.result_pill.pack(anchor="w", padx=14, pady=(0, 14))

        stop = card(right)
        stop.pack(fill="x", pady=(10, 0))
        label(stop, "Last checked location", size=12, color=C["muted"], bold=True).pack(
            anchor="w", padx=12, pady=(10, 2)
        )
        self.result_step = label(stop, "—", size=13)
        self.result_step.pack(anchor="w", padx=12)
        self.result_url = label(stop, "—", size=11, color=C["muted"], wraplength=320, justify="left")
        self.result_url.pack(anchor="w", padx=12, pady=(0, 10))

        cause = card(right)
        cause.pack(fill="both", expand=True, pady=(10, 0))
        label(cause, "What needs attention", size=12, color=C["muted"], bold=True).pack(
            anchor="w", padx=12, pady=(10, 2)
        )
        self.result_name = label(cause, "Choose tasks to get started", size=13, wraplength=320, justify="left")
        self.result_name.pack(anchor="w", padx=12)
        self.result_details = label(
            cause, "Select your regression tasks, then run the agent. Each task gets its own result.",
            size=11, color=C["muted"], wraplength=320, justify="left"
        )
        self.result_details.pack(anchor="w", padx=12, pady=(2, 12))
        self.verdict_title = label(cause, "Task results", size=12, bold=True)
        self.verdict_title.pack(anchor="w", padx=12, pady=(0, 4))
        self.task_verdicts = ctk.CTkScrollableFrame(cause, fg_color="transparent")
        self.task_verdicts.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._verdict_rows = {}

    def refresh_run(self) -> None:
        if not hasattr(self, "run_checks"):
            return
        skyvern = self.settings.get("engine") == "skyvern"
        selected = sum(task.enabled for task in self.tasks)
        running = self.active_run is not None
        self.run_destination.configure(text=f"Website: {self.settings.get('base_url') or 'http://localhost:3000'}")
        self.run_selection_note.configure(text="Task queue" if running else f"Choose tasks · {selected} selected")
        self.run_start.configure(state="disabled" if running or not selected else "normal")
        self.run_cancel.configure(state="normal" if running else "disabled")
        self.run_headless.configure(
            text="Show browser live",
            state="disabled" if self.active_run is not None else "normal",
        )
        self.browser_note.configure(text=(
            "Skyvern needs a public website URL. Live view opens its cloud browser."
            if skyvern else "browser-use supports localhost. Live view opens a separate browser window."
        ))
        for child in self.run_checks.winfo_children():
            child.destroy()
        if self.active_run is not None and self.run_task_queue:
            pending = [case["id"] for case in self.run_task_queue if case["status"] == "queued"]
            for case in self.run_task_queue:
                row = ctk.CTkFrame(self.run_checks, fg_color="transparent")
                row.pack(fill="x", pady=2)
                label(row, case["name"], size=12).pack(side="left")
                pill(row, case["status"]).pack(side="right", padx=4)
                if case["id"] in pending:
                    position = pending.index(case["id"])
                    self._task_order_buttons(row, case["id"], position, len(pending), live=True)
            return
        if not self.tasks:
            label(self.run_checks, "Add the customer flow you want to check first.", size=12,
                  color=C["muted"], wraplength=330, justify="left").pack(
                anchor="w", pady=8)
            primary_btn(self.run_checks, "+ Create a regression task", self.add_task).pack(anchor="w", pady=6)
        for index, task in enumerate(self.tasks):
            row = ctk.CTkFrame(self.run_checks, fg_color="transparent")
            row.pack(fill="x", pady=2)
            var = ctk.BooleanVar(value=task.enabled)
            ctk.CTkCheckBox(
                row,
                text=task.name,
                variable=var,
                font=(FONT, 12),
                text_color=C["text"],
                fg_color=C["accent"],
                command=lambda v=var, t=task: self._save_test_selection(t, bool(v.get())),
                state="disabled" if self.active_run is not None else "normal",
            ).pack(side="left")
            self._task_order_buttons(row, task.id, index, len(self.tasks))

    def _task_order_buttons(self, parent, task_id, position, total, live=False):
        for text, direction, available in (("↓", 1, position < total - 1), ("↑", -1, position > 0)):
            command = (lambda tid=task_id, d=direction: self.runner.move_pending_task(tid, d)) if live else (
                lambda tid=task_id, d=direction: self.move_regression_task(tid, d))
            ghost_btn(parent, text, command, width=30,
                      state="normal" if available and (live or self.active_run is None) else "disabled").pack(
                          side="right", padx=2)

    def _append_log(self, text: str) -> None:
        if not hasattr(self, "run_log"):
            return
        self.run_log.configure(state="normal")
        self.run_log.insert("end", text + "\n")
        if int(self.run_log.index("end-1c").split(".")[0]) > 3000:
            self.run_log.delete("1.0", "1001.0")
        self.run_log.see("end")
        self.run_log.configure(state="disabled")

    def launch_agent(self, record=None) -> None:
        if self.active_run is not None or self.runner.busy:
            self._append_log("A test is already running. Wait for it to finish or cancel it.")
            return
        selected_tasks = [task for task in self.tasks if task.enabled]
        if not selected_tasks and record is None:
            self._append_log("Select at least one regression task before launching.")
            return
        rec = record
        if rec is None:
            rec = RunRecord(
                title="Manual run", description="Started from Run Agent", status="queued"
            )
            self.history.insert(0, rec)
        self.current = rec
        self.active_run = rec
        self.run_task_queue = []

        rec.status = "running"
        rec.path = self.settings.get("base_url") or "http://localhost:3000"
        rec.description = f"{len(selected_tasks)} regression task(s)"
        rec.report = {}
        self.settings["show_browser"] = bool(self.run_headless.get())
        self.save_state()
        self._show_result(rec)
        self.show_page("Run Agent")
        if not rec.commit:
            info = self.monitor.current()
            rec.commit = info[0] if info else ""
        self.refresh_history()
        self._append_log(f"Queued {rec.id} for {rec.path}")

        accepted = self.runner.submit(
            self.settings,
            selected_tasks,
            headless=not bool(self.run_headless.get()),
        )
        if not accepted:
            rec.status = "failed"
            self.active_run = None
            self.save_state()
            self.refresh_history()
            self._show_result(rec)
            self.refresh_run()

    def _save_browser_visibility(self) -> None:
        self.settings["show_browser"] = bool(self.run_headless.get())
        self.save_state()

    def _save_test_selection(self, task=None, enabled=None):
        if task is not None:
            task.enabled = enabled
        self.save_state()
        self.refresh_run()
        self.refresh_journey()

    def _show_result(self, rec) -> None:
        if not hasattr(self, "result_title"):
            return
        record_id = rec.id if rec is not None else None
        if getattr(self, "_verdict_record_id", None) != record_id:
            for row in self._verdict_rows.values():
                row.destroy()
            self._verdict_rows.clear()
            self._verdict_record_id = record_id
        if rec is None:
            self.result_title.configure(text="Ready when you are", text_color=C["text"])
            self.result_pill.configure(text="NOT STARTED", fg_color=C["border"], text_color=C["muted"])
            for box in (self.result_step, self.result_url, self.result_name, self.result_details):
                box.configure(text="—")
            self._show_task_verdicts({})
            return
        rep = rec.report or {}
        self.result_title.configure(
            text=rec.status.upper(), text_color=STATUS_COLORS.get(rec.status, C["text"])
        )
        self.result_pill.configure(
            text=rec.status.upper(), fg_color=STATUS_COLORS.get(rec.status, C["muted"]), text_color=C["bg"]
        )
        self.result_step.configure(text=f"Step {rep.get('stopped_at_step', 0)}")
        self.result_url.configure(text=rep.get("stopped_url") or "—")
        self.result_name.configure(text=rep.get("failed_test_name") or (
            "All selected tasks passed" if rec.status == "passed" else
            "Checking your customer flows…" if rec.status == "running" else "—"))
        self.result_details.configure(text=rep.get("error_details") or (
            "Expected outcomes were verified. Open Run History to revisit this report."
            if rec.status == "passed" else "Follow the live activity while each task runs."
            if rec.status == "running" else "—"))
        self._show_task_verdicts(rep)

    def _show_task_verdicts(self, report):
        results = report.get("task_results", [])
        self.verdict_title.configure(text=f"Task results ({len(results)}/{report.get('total_tasks', len(results))})")
        ids = {result["task_id"] for result in results}
        for task_id in list(self._verdict_rows):
            if task_id not in ids:
                self._verdict_rows.pop(task_id).destroy()
        for result in results:
            task_id = result["task_id"]
            if task_id in self._verdict_rows:
                continue
            row = card(self.task_verdicts)
            row.pack(fill="x", pady=3)
            self._verdict_rows[task_id] = row
            label(row, result["task_name"], size=12, bold=True, wraplength=270).pack(anchor="w", padx=8, pady=(6, 2))
            pill(row, result["status"].lower()).pack(anchor="w", padx=8, pady=2)
            details = result["error_details"] or "Expected outcome verified."
            label(row, details, size=11, color=C["muted"], wraplength=270, justify="left").pack(
                anchor="w", padx=8, pady=(2, 6))
