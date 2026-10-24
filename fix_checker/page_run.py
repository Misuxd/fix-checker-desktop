"""Run Agent page: inputs, live log, result cards, launching."""
from __future__ import annotations

import customtkinter as ctk

from .config import C, FONT, MONO, STATUS_COLORS
from .models import RunRecord
from .widgets import card, entry, ghost_btn, label, pill, primary_btn


class RunPageMixin:
    """Target path, fix trajectory, regression checkboxes, live steps, result panel."""

    def _build_run(self, parent) -> None:
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(22, 10), pady=16)
        right = ctk.CTkFrame(parent, fg_color="transparent", width=360)
        right.pack(side="right", fill="y", padx=(0, 22), pady=16)
        right.pack_propagate(False)

        target = card(left)
        target.pack(fill="x")
        label(target, "Target path", size=12, color=C["muted"], bold=True).pack(
            anchor="w", padx=12, pady=(10, 2)
        )
        self.run_path = entry(target, placeholder_text="/")
        self.run_path.insert(0, "/")
        self.run_path.delete(0, "end")
        self.run_path.insert(0, self.settings.get("target_path", "/"))
        self.run_path.pack(fill="x", padx=12, pady=(0, 10))

        fix = card(left)
        fix.pack(fill="x", pady=(10, 0))
        label(fix, "Fix + trajectory", size=12, color=C["muted"], bold=True).pack(
            anchor="w", padx=12, pady=(10, 2)
        )
        self.run_fix = ctk.CTkTextbox(
            fix,
            fg_color=C["panel"],
            text_color=C["text"],
            border_color=C["border"],
            border_width=1,
            font=(MONO, 12),
            height=120,
        )
        self.run_fix.pack(fill="x", padx=12, pady=(0, 10))
        self.run_fix.insert("1.0", self.settings.get("fix_text", ""))

        regs = card(left)
        regs.pack(fill="x", pady=(10, 0))
        head = ctk.CTkFrame(regs, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(10, 4))
        label(head, "Regression tasks", size=12, color=C["muted"], bold=True).pack(side="left")
        ghost_btn(head, "+ Add regression task", lambda: self.show_page("Regression Tasks")).pack(
            side="right"
        )
        self.run_checks = ctk.CTkFrame(regs, fg_color="transparent")
        self.run_checks.pack(fill="x", padx=12, pady=(0, 10))
        self.current_fix = ctk.BooleanVar(value=self.settings.get("test_current_fix", True))

        opts = ctk.CTkFrame(left, fg_color="transparent")
        opts.pack(fill="x", pady=(12, 0))
        self.run_headless = ctk.CTkSwitch(
            opts,
            text="Show browser live",
            font=(FONT, 12),
            text_color=C["text"],
            progress_color=C["accent"],
        )
        self.run_headless.pack(side="left")
        if self.settings.get("show_browser"):
            self.run_headless.select()
        ghost_btn(opts, "Cancel", self.runner.cancel).pack(side="right", padx=4)
        primary_btn(opts, "Launch agent in browser", lambda: self.launch_agent()).pack(
            side="right"
        )

        log = card(left)
        log.pack(fill="both", expand=True, pady=(12, 0))
        label(log, "Live steps", size=12, color=C["muted"], bold=True).pack(
            anchor="w", padx=12, pady=(10, 2)
        )
        self.run_log = ctk.CTkTextbox(
            log, fg_color=C["panel"], text_color=C["muted"], font=(MONO, 11), state="disabled"
        )
        self.run_log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.result_card = card(right)
        self.result_card.pack(fill="x")
        self.result_title = label(self.result_card, "No run yet", size=26, bold=True)
        self.result_title.pack(anchor="w", padx=14, pady=(14, 6))
        self.result_pill = pill(self.result_card, "queued")
        self.result_pill.pack(anchor="w", padx=14, pady=(0, 14))

        stop = card(right)
        stop.pack(fill="x", pady=(10, 0))
        label(stop, "Where it stopped", size=12, color=C["muted"], bold=True).pack(
            anchor="w", padx=12, pady=(10, 2)
        )
        self.result_step = label(stop, "—", size=13)
        self.result_step.pack(anchor="w", padx=12)
        self.result_url = label(stop, "—", size=11, color=C["muted"])
        self.result_url.pack(anchor="w", padx=12, pady=(0, 10))

        cause = card(right)
        cause.pack(fill="both", expand=True, pady=(10, 0))
        label(cause, "Failed test & cause", size=12, color=C["muted"], bold=True).pack(
            anchor="w", padx=12, pady=(10, 2)
        )
        self.result_name = label(cause, "—", size=13)
        self.result_name.pack(anchor="w", padx=12)
        self.result_details = label(
            cause, "—", size=11, color=C["muted"], wraplength=320, justify="left"
        )
        self.result_details.pack(anchor="w", padx=12, pady=(2, 12))

    def refresh_run(self) -> None:
        if not hasattr(self, "run_checks"):
            return
        for child in self.run_checks.winfo_children():
            child.destroy()
        ctk.CTkCheckBox(
            self.run_checks, text="Current fix (trajectory above)", variable=self.current_fix,
            command=lambda: self._save_test_selection(),
        ).pack(anchor="w", pady=1)
        for task in self.tasks:
            var = ctk.BooleanVar(value=task.enabled)
            ctk.CTkCheckBox(
                self.run_checks,
                text=f"{task.name}  ({task.path})",
                variable=var,
                font=(FONT, 12),
                text_color=C["text"],
                fg_color=C["accent"],
                command=lambda v=var, t=task: self._save_test_selection(t, bool(v.get())),
            ).pack(anchor="w", pady=1)

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
        rec = record
        if rec is None:
            rec = RunRecord(
                title="Manual run", description="Started from Run Agent", status="queued"
            )
            self.history.insert(0, rec)
        self.current = rec
        self.active_run = rec

        rec.status = "running"
        if rec.tag != "commit":
            rec.path = self.run_path.get().strip() or "/"
            rec.description = self.run_fix.get("1.0", "end").strip()
        rec.report = {}
        self.settings.update(target_path=rec.path, fix_text=rec.description,
                             show_browser=bool(self.run_headless.get()),
                             test_current_fix=bool(self.current_fix.get()))
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
            rec.path,
            rec.description,
            [t for t in self.tasks if t.enabled],
            headless=not bool(self.run_headless.get()),
        )
        if not accepted:
            rec.status = "failed"
            self.active_run = None
            self.save_state()

    def _save_test_selection(self, task=None, enabled=None):
        if task is not None:
            task.enabled = enabled
        self.settings["test_current_fix"] = bool(self.current_fix.get())
        self.save_state()

    def _show_result(self, rec) -> None:
        if not hasattr(self, "result_title"):
            return
        rep = rec.report or {}
        ok = rec.status == "passed"
        self.result_title.configure(
            text=rec.status.upper(), text_color=C["green"] if ok else C["red"]
        )
        self.result_pill.configure(
            text=rec.status.upper(), fg_color=STATUS_COLORS.get(rec.status, C["muted"])
        )
        self.result_step.configure(text=f"Step {rep.get('stopped_at_step', 0)}")
        self.result_url.configure(text=rep.get("stopped_url") or "—")
        self.result_name.configure(text=rep.get("failed_test_name") or "—")
        self.result_details.configure(text=rep.get("error_details") or "—")
