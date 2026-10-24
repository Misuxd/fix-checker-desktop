"""Home page: list of test runs."""
from __future__ import annotations

import customtkinter as ctk

from .config import C, FONT
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
        self.home_search = entry(bar, placeholder_text="Search commits, titles, paths...")
        self.home_search.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.home_search.bind("<KeyRelease>", lambda _e: self.refresh_home())
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
        self.refresh_home()

    def refresh_home(self) -> None:
        if not hasattr(self, "home_list"):
            return
        for child in self.home_list.winfo_children():
            child.destroy()

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
        self.home_count.configure(text=f"{len(rows)} run(s)")

        for rec in rows:
            row = card(self.home_list)
            row.pack(fill="x", pady=5)

            top = ctk.CTkFrame(row, fg_color="transparent")
            top.pack(fill="x", padx=14, pady=(10, 0))
            label(top, rec.title or rec.commit[:7] or "untitled", size=14, bold=True).pack(
                side="left"
            )
            pill(top, rec.status).pack(side="right")
            ghost_btn(top, "View result", lambda r=rec: self.view_run(r)).pack(side="right", padx=8)

            label(row, rec.description or "—", size=12, color=C["muted"]).pack(
                anchor="w", padx=14
            )

            meta = ctk.CTkFrame(row, fg_color="transparent")
            meta.pack(fill="x", padx=14, pady=(6, 10))
            label(
                meta,
                f"{rec.id}  ·  {rec.tag}  ·  {(rec.commit or '')[:7]}",
                size=11,
                color=C["muted"],
            ).pack(side="left")
            label(meta, time_ago(rec.started), size=11, color=C["muted"]).pack(side="right")

    def view_run(self, record):
        self.show_page("Run Agent")
        self._show_result(record)
