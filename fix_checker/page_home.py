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
            values = {
                "title": rec.title or rec.commit[:7] or "untitled",
                "description": rec.description or "—",
                "meta": f"{rec.id}  ·  {rec.tag}  ·  {(rec.commit or '')[:7]}",
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

    def _create_home_row(self, rec):
        row = card(self.home_list)
        cached = {"frame": row, "record": rec, "values": {}, "position": None}
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 0))
        cached["title"] = label(top, "", size=14, bold=True)
        cached["title"].pack(side="left")
        cached["status"] = pill(top, rec.status)
        cached["status"].pack(side="right")
        ghost_btn(top, "View result", lambda: self.view_run(cached["record"])).pack(side="right", padx=8)

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
        self.show_page("Run Agent")
        self._show_result(record)
