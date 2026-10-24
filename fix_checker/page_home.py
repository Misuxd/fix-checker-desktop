"""Home page: list of test runs."""
from __future__ import annotations

import customtkinter as ctk

from .config import C, STATUS_COLORS
from .models import time_ago
from .widgets import card, entry, ghost_btn, label, pill


class HomePageMixin:
    """Pending Checks list with search and filter chips."""

    def _build_home(self, parent) -> None:
        head = card(parent)
        head.pack(fill="x", padx=22, pady=(16, 10))
        label(head, "Pending Checks", size=16, bold=True).pack(
            anchor="w", padx=14, pady=(10, 2)
        )
        self.home_count = label(head, "", size=12, color=C["muted"])
        self.home_count.pack(anchor="w", padx=14, pady=(0, 10))

        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x", padx=22)
        self.home_search = entry(bar, placeholder_text="Search commits, titles, URLs...")
        self.home_search.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._home_search_after = None
        self.home_search.bind("<KeyRelease>", self._schedule_home_search)
        self.home_status = ctk.CTkOptionMenu(
            bar, values=["All statuses", "queued", "running", "passed", "failed"],
            width=130, command=lambda _: self.refresh_home())
        self.home_status.pack(side="left", padx=4)
        self.home_source = ctk.CTkOptionMenu(
            bar, values=["All runs", "manual", "commit"], width=110,
            command=lambda _: self.refresh_home())
        self.home_source.pack(side="left", padx=4)

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.pack(fill="x", padx=22, pady=(8, 0))
        self._history_selected = set()
        self._home_visible_ids = set()
        self.home_select_all = ghost_btn(actions, "Select all", self.select_all_history, width=100)
        self.home_select_all.pack(side="left")
        self.home_delete = ghost_btn(actions, "Delete selected", self.delete_selected_history,
                                     state="disabled", width=150)
        self.home_delete.pack(side="left", padx=8)
        label(actions, "The active run cannot be deleted.", size=11, color=C["muted"]).pack(side="right")

        self.home_list = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.home_list.pack(fill="both", expand=True, padx=22, pady=(10, 16))
        self.home_list.grid_columnconfigure(0, weight=1)
        self._home_rows = {}
        self.refresh_home()

    def _schedule_home_search(self, _event=None) -> None:
        if self._home_search_after is not None:
            self.after_cancel(self._home_search_after)
        self._home_search_after = self.after(120, self._apply_home_search)

    def _apply_home_search(self) -> None:
        self._home_search_after = None
        self.refresh_home()

    def refresh_home(self) -> None:
        if not hasattr(self, "home_list"):
            return

        needle = self.home_search.get().strip().lower()
        rows = [
            r
            for r in self.history
            if not needle or needle in f"{r.title} {r.description} {r.path} {r.commit}".lower()
        ]
        if self.home_status.get() != "All statuses":
            rows = [r for r in rows if r.status == self.home_status.get()]
        if self.home_source.get() != "All runs":
            rows = [r for r in rows if r.tag == self.home_source.get()]
        count_text = f"{len(rows)} run(s)"
        if getattr(self, "_home_count_text", None) != count_text:
            self.home_count.configure(text=count_text)
            self._home_count_text = count_text

        current_ids = {rec.id for rec in self.history}
        visible_ids = {rec.id for rec in rows}
        active_id = self.active_run.id if self.active_run else None
        self._history_selected.intersection_update(current_ids - {active_id})
        self._home_visible_ids = visible_ids - {active_id}
        pending = [rec.id for rec in self.pending_runs]
        for run_id, cached in list(self._home_rows.items()):
            if run_id not in current_ids:
                cached["frame"].destroy()
                del self._home_rows[run_id]
            elif run_id not in visible_ids and cached["position"] is not None:
                cached["frame"].grid_remove()
                cached["position"] = None

        for index, rec in enumerate(rows):
            cached = self._home_rows.get(rec.id)
            if cached is None:
                cached = self._create_home_row(rec)
                self._home_rows[rec.id] = cached
            cached["record"] = rec
            selected = rec.id in self._history_selected
            if cached["selected"].get() != selected:
                cached["selected"].set(selected)
            if cached.get("selectable") != (rec.id != active_id):
                cached["checkbox"].configure(state="disabled" if rec.id == active_id else "normal")
                cached["selectable"] = rec.id != active_id
            queue_position = pending.index(rec.id) if rec.id in pending else None
            queue_state = (queue_position, len(pending)) if queue_position is not None else None
            if cached.get("queue_state") != queue_state:
                for button in (cached["queue_up"], cached["queue_down"]):
                    button.pack_forget()
                if queue_position is not None:
                    cached["queue_down"].configure(state="normal" if queue_position < len(pending) - 1 else "disabled")
                    cached["queue_up"].configure(state="normal" if queue_position > 0 else "disabled")
                    cached["queue_down"].pack(side="right", padx=2)
                    cached["queue_up"].pack(side="right", padx=2)
                cached["queue_state"] = queue_state
            values = {
                "title": rec.title or rec.commit[:7] or "untitled",
                "description": rec.description or "—",
                "meta": f"{rec.id}  ·  {rec.tag}  ·  {(rec.commit or '')[:7]}" + (
                    f"  ·  Queue #{queue_position + 1}" if queue_position is not None else ""),
                "age": time_ago(rec.started),
                "status": rec.status,
            }
            for field, value in values.items():
                if cached["values"].get(field) == value:
                    continue
                if field == "status":
                    cached[field].configure(text=value.upper(), fg_color=STATUS_COLORS.get(value, C["muted"]))
                else:
                    cached[field].configure(text=value)
            cached["values"] = values
            if cached["position"] != index:
                cached["frame"].grid(row=index, column=0, sticky="ew", pady=5)
                cached["position"] = index
        self._update_history_actions()

    def _create_home_row(self, rec):
        row = card(self.home_list)
        cached = {"frame": row, "record": rec, "values": {}, "position": None}
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 0))
        cached["selected"] = ctk.BooleanVar(value=rec.id in self._history_selected)
        cached["checkbox"] = ctk.CTkCheckBox(top, text="", width=24, variable=cached["selected"],
            command=lambda: self._select_history(cached["record"].id, bool(cached["selected"].get())))
        cached["checkbox"].pack(side="left", padx=(0, 8))
        cached["title"] = label(top, "", size=14, bold=True)
        cached["title"].pack(side="left")
        cached["status"] = pill(top, rec.status)
        cached["status"].pack(side="right")
        ghost_btn(top, "View result", lambda: self.view_run(cached["record"])).pack(side="right", padx=8)
        cached["queue_up"] = ghost_btn(top, "↑", lambda: self.move_pending_run(cached["record"].id, -1), width=30)
        cached["queue_down"] = ghost_btn(top, "↓", lambda: self.move_pending_run(cached["record"].id, 1), width=30)

        cached["description"] = label(row, "", size=12, color=C["muted"])
        cached["description"].pack(anchor="w", padx=14)

        meta = ctk.CTkFrame(row, fg_color="transparent")
        meta.pack(fill="x", padx=14, pady=(6, 10))
        cached["meta"] = label(meta, "", size=11, color=C["muted"])
        cached["meta"].pack(side="left")
        cached["age"] = label(meta, "", size=11, color=C["muted"])
        cached["age"].pack(side="right")
        return cached

    def view_run(self, record):
        self.current = record
        self.show_page("Run Agent")
        self._show_result(record)

    def _select_history(self, run_id, selected):
        if selected:
            self._history_selected.add(run_id)
        else:
            self._history_selected.discard(run_id)
        self._update_history_actions()

    def _update_history_actions(self):
        count = len(self._history_selected)
        self.home_delete.configure(text=f"Delete selected ({count})", state="normal" if count else "disabled")
        all_selected = bool(self._home_visible_ids) and self._home_visible_ids <= self._history_selected
        self.home_select_all.configure(text="Clear selection" if all_selected else "Select all",
                                       state="normal" if self._home_visible_ids else "disabled")

    def select_all_history(self):
        if self._home_visible_ids <= self._history_selected:
            self._history_selected.difference_update(self._home_visible_ids)
        else:
            self._history_selected.update(self._home_visible_ids)
        self.refresh_home()

    def delete_selected_history(self):
        active_id = self.active_run.id if self.active_run else None
        deleted = self._history_selected - {active_id}
        if not deleted:
            return
        self.history = [rec for rec in self.history if rec.id not in deleted]
        self.pending_runs = [rec for rec in self.pending_runs if rec.id not in deleted]
        if self.current is not None and self.current.id in deleted:
            self.current = self.active_run
            self._show_result(self.current)
        self._history_selected.difference_update(deleted)
        self.save_state()
        self.refresh_history()
