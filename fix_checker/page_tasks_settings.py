"""Regression Tasks and Settings pages."""
from __future__ import annotations

from tkinter import filedialog, messagebox

import customtkinter as ctk

from .config import C, FONT
from .models import RegressionTask
from .widgets import card, entry, ghost_btn, label, primary_btn


class TasksSettingsMixin:
    """Saved regression flows and the app settings form."""

    # -- Regression Tasks --------------------------------------------------
    def _build_tasks(self, parent) -> None:
        head = card(parent)
        head.pack(fill="x", padx=22, pady=(16, 10))
        label(head, "Regression Tasks", size=16, bold=True).pack(
            anchor="w", padx=14, pady=(10, 2)
        )
        label(head, "Flows replayed after every commit.", size=12, color=C["muted"]).pack(
            anchor="w", padx=14, pady=(0, 8)
        )
        primary_btn(head, "+ Add regression task", self.add_task).pack(
            anchor="w", padx=14, pady=(0, 12)
        )

        self.tasks_list = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.tasks_list.pack(fill="both", expand=True, padx=22, pady=(0, 16))
        self.refresh_tasks()

    def refresh_tasks(self) -> None:
        if not hasattr(self, "tasks_list"):
            return
        for child in self.tasks_list.winfo_children():
            child.destroy()
        for task in self.tasks:
            row = card(self.tasks_list)
            row.pack(fill="x", pady=5)

            top = ctk.CTkFrame(row, fg_color="transparent")
            top.pack(fill="x", padx=14, pady=(10, 0))
            label(top, task.name or "untitled", size=14, bold=True).pack(side="left")
            ghost_btn(top, "Delete", lambda t=task: self.delete_task(t)).pack(side="right")
            ghost_btn(top, "Edit", lambda t=task: self.edit_task(t)).pack(side="right", padx=6)

            label(row, f"path: {task.path}", size=11, color=C["muted"]).pack(
                anchor="w", padx=14
            )
            label(
                row,
                task.steps or "—",
                size=12,
                color=C["muted"],
                wraplength=900,
                justify="left",
            ).pack(anchor="w", padx=14, pady=(2, 10))

    def add_task(self) -> None:
        self.edit_task()

    def edit_task(self, task=None) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Edit regression task" if task else "Add regression task")
        dialog.geometry("600x450")
        dialog.transient(self)
        name = self._field(dialog, "Task name")
        path = self._field(dialog, "Start path or full URL")
        label(dialog, "Steps and expected result", size=12).pack(anchor="w", padx=14, pady=8)
        steps = ctk.CTkTextbox(dialog, height=150)
        steps.pack(fill="both", expand=True, padx=14)
        name.insert(0, task.name if task else "")
        path.insert(0, task.path if task else "/")
        steps.insert("1.0", task.steps if task else "")
        def save():
            title, trajectory = name.get().strip(), steps.get("1.0", "end").strip()
            if not title or not trajectory:
                messagebox.showerror("Incomplete task", "Enter a name, steps and expected result.", parent=dialog)
                return
            from .agent_runner import target_url
            try:
                target_url(self.settings["base_url"], path.get())
            except ValueError as exc:
                messagebox.showerror("Invalid URL", str(exc), parent=dialog)
                return
            target = task or RegressionTask()
            target.name, target.path, target.steps = title, path.get().strip() or "/", trajectory
            if task is None:
                self.tasks.append(target)
            self.save_state()
            self.refresh_tasks()
            self.refresh_run()
            dialog.destroy()
        primary_btn(dialog, "Save task", save).pack(padx=14, pady=14)
        dialog.after(100, dialog.grab_set)

    def delete_task(self, task) -> None:
        self.tasks = [t for t in self.tasks if t.id != task.id]
        self.save_state()
        self.refresh_tasks()
        self.refresh_run()

    # -- Settings ----------------------------------------------------------
    def _build_settings(self, parent) -> None:
        body = card(parent)
        body.pack(fill="both", expand=True, padx=22, pady=16)
        label(body, "Settings", size=16, bold=True).pack(anchor="w", padx=14, pady=(12, 8))

        label(body, "Browser engine", size=12, color=C["muted"]).pack(anchor="w", padx=14, pady=(8, 2))
        self.set_engine = ctk.CTkOptionMenu(
            body, values=["browser-use", "skyvern"], command=self._change_engine,
        )
        self.set_engine.pack(anchor="w", padx=14)
        self.set_key_label = label(body, "", size=12, color=C["muted"], bold=True)
        self.set_key_label.pack(anchor="w", padx=14, pady=(8, 2))
        self.set_key = entry(body, width=520)
        self.set_key.pack(anchor="w", padx=14)
        self.set_key.configure(show="*")
        self.set_engine_note = label(body, "", size=11, color=C["muted"])
        self.set_engine_note.pack(anchor="w", padx=14, pady=(4, 0))
        self.set_model = self._field(body, "Model name (browser-use)")
        self.set_url = self._field(body, "Base site URL")
        self.set_repo = self._field(body, "Git repo path")

        self.set_auto = ctk.CTkSwitch(
            body,
            text="Auto-run after every commit",
            font=(FONT, 13),
            text_color=C["text"],
            progress_color=C["accent"],
        )
        self.set_auto.pack(anchor="w", padx=14, pady=(10, 6))

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(4, 14))
        ghost_btn(row, "Pick repo folder", self.pick_repo).pack(side="left")
        primary_btn(row, "Save settings", self.save_settings).pack(side="right")
        self.settings_note = label(row, "", size=11, color=C["muted"])
        self.settings_note.pack(side="right", padx=10)

        self.refresh_settings()

    def _field(self, parent, name):
        label(parent, name, size=12, color=C["muted"], bold=True).pack(
            anchor="w", padx=14, pady=(8, 2)
        )
        box = entry(parent, width=520)
        box.pack(anchor="w", padx=14)
        return box

    def refresh_settings(self) -> None:
        if not hasattr(self, "set_key"):
            return
        s = self.settings
        self.set_engine.set(s.get("engine", "skyvern"))
        self._key_drafts = {key: s.get(key, "") for key in ("openai_key", "skyvern_key")}
        self.set_model.configure(state="normal")
        for box, key in (
            (self.set_model, "model"),
            (self.set_url, "base_url"),
            (self.set_repo, "repo_path"),
        ):
            box.delete("0", "end")
            box.insert(0, s.get(key, ""))
        self._show_engine_key(self.set_engine.get())
        if s.get("auto_run"):
            self.set_auto.select()
        else:
            self.set_auto.deselect()

    def _show_engine_key(self, engine) -> None:
        self._key_engine = engine
        skyvern = engine == "skyvern"
        self.set_key_label.configure(text="Skyvern API key" if skyvern else "OpenAI API key")
        self.set_key.delete("0", "end")
        self.set_key.insert(0, self._key_drafts["skyvern_key" if skyvern else "openai_key"])
        self.set_engine_note.configure(text=(
            "Skyvern uses a cloud browser and needs a publicly reachable site URL."
            if skyvern else "browser-use uses your OpenAI API key and runs Chromium locally."
        ))
        self.set_model.configure(state="disabled" if skyvern else "normal")

    def _change_engine(self, engine) -> None:
        key = "skyvern_key" if self._key_engine == "skyvern" else "openai_key"
        self._key_drafts[key] = self.set_key.get().strip()
        self._show_engine_key(engine)

    def pick_repo(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.set_repo.delete("0", "end")
            self.set_repo.insert(0, path)

    def save_settings(self) -> None:
        from .agent_runner import target_url
        try:
            target_url(self.set_url.get().strip() or "http://localhost:3000", "/")
            repo_path = self.set_repo.get().strip()
            if repo_path:
                import git
                with git.Repo(repo_path):
                    pass
        except Exception as exc:
            self.settings_note.configure(text=f"Invalid settings: {exc}")
            return
        key = "skyvern_key" if self.set_engine.get() == "skyvern" else "openai_key"
        self._key_drafts[key] = self.set_key.get().strip()
        self.settings.update(self._key_drafts)
        self.settings.update(
            {
                "model": self.set_model.get().strip() or "gpt-6-luna",
                "base_url": self.set_url.get().strip() or "http://localhost:3000",
                "repo_path": self.set_repo.get().strip(),
                "auto_run": bool(self.set_auto.get()),
                "engine": self.set_engine.get(),
            }
        )
        self.save_state()
        self.ai_model.configure(text="Skyvern" if self.settings["engine"] == "skyvern" else self.settings["model"])
        self.settings_note.configure(text="Saved")
        self.monitor.start(self.settings["repo_path"])
