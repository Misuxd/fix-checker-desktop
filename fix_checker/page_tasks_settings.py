"""Guided setup and saved regression tasks."""
from __future__ import annotations

from tkinter import filedialog, messagebox

import customtkinter as ctk

from .config import C, FONT
from .models import RegressionTask
from .widgets import card, entry, ghost_btn, label, primary_btn

EXAMPLE_TASK_NAME = "Search for a product"
EXAMPLE_TASK_STEPS = (
    "1. From the website URL, navigate to /products.\n"
    '2. Enter "backpack" in the product search field.\n'
    "3. Submit the search.\n"
    'Expected result: At least one product is shown and every result contains "backpack" in its name.'
)


class TasksSettingsMixin:
    """Saved regression flows and the app settings form."""

    # -- Regression Tasks --------------------------------------------------
    def _build_tasks(self, parent) -> None:
        head = card(parent)
        head.pack(fill="x", padx=22, pady=(16, 10))
        primary_btn(head, "Continue to Run Agent →", lambda: self.show_page("Run Agent")).pack(
            side="right", padx=14, pady=14
        )
        label(head, "Protect the flows your customers rely on", size=18, bold=True,
              wraplength=420, justify="left").pack(
            anchor="w", padx=14, pady=(10, 2)
        )
        label(head, "Describe an action and the result you expect. The agent replays each selected task.",
              size=12, color=C["muted"], wraplength=520, justify="left").pack(
            anchor="w", padx=14, pady=(0, 8)
        )
        primary_btn(head, "+ Add regression task", self.add_task).pack(
            anchor="w", padx=14, pady=(0, 12)
        )
        guide = ctk.CTkFrame(parent, fg_color="transparent")
        guide.pack(fill="x", padx=36, pady=(0, 8))
        label(guide, "One customer flow per task · Include prerequisites · Finish with an expected result",
              size=11, color=C["muted"], wraplength=700, justify="left").pack(anchor="w")

        self.tasks_list = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.tasks_list.pack(fill="both", expand=True, padx=22, pady=(0, 16))
        self.refresh_tasks()

    def refresh_tasks(self) -> None:
        if not hasattr(self, "tasks_list"):
            return
        for child in self.tasks_list.winfo_children():
            child.destroy()
        if not self.tasks:
            empty = card(self.tasks_list)
            empty.pack(fill="x", pady=5)
            label(empty, "What should always work on your website?", size=17, bold=True).pack(
                anchor="w", padx=18, pady=(24, 6))
            label(empty, "Start with sign-in, search or checkout. The task editor includes an example to help you write your first check.",
                  size=12, color=C["muted"], wraplength=620, justify="left").pack(
                anchor="w", padx=18, pady=(0, 14))
            primary_btn(empty, "Create your first task", self.add_task).pack(
                anchor="w", padx=18, pady=(0, 24))
        for index, task in enumerate(self.tasks):
            row = card(self.tasks_list)
            row.pack(fill="x", pady=5)

            top = ctk.CTkFrame(row, fg_color="transparent")
            top.pack(fill="x", padx=14, pady=(10, 0))
            label(top, task.name or "untitled", size=14, bold=True).pack(side="left")
            ghost_btn(top, "Delete", lambda t=task: self.delete_task(t), width=65).pack(side="right")
            ghost_btn(top, "Edit", lambda t=task: self.edit_task(t), width=65).pack(side="right", padx=6)
            self._task_order_buttons(top, task.id, index, len(self.tasks))

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

    def move_regression_task(self, task_id, direction) -> None:
        if self.active_run is not None:
            return
        index = next((i for i, task in enumerate(self.tasks) if task.id == task_id), -1)
        destination = index + direction
        if index >= 0 and 0 <= destination < len(self.tasks):
            self.tasks[index], self.tasks[destination] = self.tasks[destination], self.tasks[index]
            self.save_state()
            self.refresh_tasks()
            self.refresh_run()

    def edit_task(self, task=None) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Edit regression task" if task else "Add regression task")
        dialog.geometry("680x680")
        dialog.minsize(600, 620)
        dialog.transient(self)
        label(dialog, "Describe a customer flow", size=20, bold=True).pack(
            anchor="w", padx=14, pady=(16, 2))
        label(dialog, "Include where to go, what to do and how to tell it worked.",
              size=12, color=C["muted"]).pack(anchor="w", padx=14, pady=(0, 10))
        example = card(dialog)
        example.pack(fill="x", padx=14, pady=(0, 6))
        label(example, "EXAMPLE · " + EXAMPLE_TASK_NAME, size=12, bold=True, color=C["accent"]).pack(
            anchor="w", padx=12, pady=(10, 4))
        label(example, EXAMPLE_TASK_STEPS, size=12, color=C["muted"], justify="left",
              wraplength=560).pack(anchor="w", padx=12, pady=(0, 8))
        name = self._field(dialog, "Task name", placeholder="e.g. Search for a product")
        label(dialog, "Steps and expected result", size=12).pack(anchor="w", padx=14, pady=8)
        steps = ctk.CTkTextbox(dialog, height=160, fg_color=C["panel"], border_width=1,
                               border_color=C["border"], font=(FONT, 13), wrap="word")
        steps.pack(fill="both", expand=True, padx=14)
        name.insert(0, task.name if task else "")
        steps.insert("1.0", task.steps if task else "")

        def use_example():
            if (name.get().strip() or steps.get("1.0", "end").strip()) and not messagebox.askyesno(
                "Use example", "Replace this draft with the example?", parent=dialog
            ):
                return
            name.delete(0, "end")
            name.insert(0, EXAMPLE_TASK_NAME)
            steps.delete("1.0", "end")
            steps.insert("1.0", EXAMPLE_TASK_STEPS)
            name.focus_set()

        ghost_btn(example, "Use this example", use_example, width=150).pack(
            anchor="w", padx=12, pady=(0, 10))
        label(dialog, "Adapt the example to your site. Include test credentials if the flow needs sign-in.",
              size=11, color=C["muted"], wraplength=560, justify="left").pack(
            anchor="w", padx=14, pady=(6, 0))

        def save():
            title, trajectory = name.get().strip(), steps.get("1.0", "end").strip()
            if not title or not trajectory:
                messagebox.showerror("Incomplete task", "Enter a name, steps and expected result.", parent=dialog)
                return
            target = task or RegressionTask()
            target.name, target.steps = title, trajectory
            if task is None:
                self.tasks.append(target)
            self.save_state()
            self.refresh_tasks()
            self.refresh_run()
            self.refresh_journey()
            dialog.destroy()
        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=14)
        ghost_btn(actions, "Cancel", dialog.destroy, width=90).pack(side="left")
        primary_btn(actions, "Save task", save).pack(side="right")
        dialog.after(100, dialog.grab_set)
        name.focus_set()

    def delete_task(self, task) -> None:
        self.tasks = [t for t in self.tasks if t.id != task.id]
        self.save_state()
        self.refresh_tasks()
        self.refresh_run()
        self.refresh_journey()

    # -- Home & Setup -----------------------------------------------------
    def _build_settings(self, parent) -> None:
        welcome = ctk.CTkFrame(parent, fg_color="transparent")
        welcome.pack(fill="x", padx=24, pady=(14, 10))
        label(welcome, "Make every change a confident one.", size=25, bold=True).pack(anchor="w")
        label(welcome, "Connect your website, define the flows that matter, then let FixGuard check them.",
              size=13, color=C["muted"]).pack(anchor="w", pady=(4, 6))
        self.setup_summary = label(welcome, "", size=12, color=C["accent"])
        self.setup_summary.pack(anchor="w")

        journey = ctk.CTkFrame(parent, fg_color="transparent")
        journey.pack(fill="x", padx=22, pady=(0, 12))
        journey.grid_columnconfigure((0, 1, 2), weight=1, uniform="journey")
        self.journey_buttons = []
        for index, page in enumerate(("Home & Setup", "Regression Tasks", "Run Agent")):
            button = ghost_btn(journey, "", lambda p=page: self.show_page(p), height=58,
                               anchor="w", text_color=C["text"])
            button.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 5, 0))
            self.journey_buttons.append(button)

        footer = ctk.CTkFrame(parent, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=22, pady=(10, 16))
        self.settings_note = label(footer, "Your API key and setup are saved on this computer.",
                                   size=11, color=C["muted"], justify="left", anchor="w")
        self.settings_note.pack(fill="x", pady=(0, 8))
        self.settings_note.bind("<Configure>", lambda event: self.settings_note.configure(
            wraplength=max(200, event.width)))
        ghost_btn(footer, "Save setup", self.save_settings, width=120).pack(side="left")
        primary_btn(footer, "Continue to Regression Tasks →", self._continue_to_tasks).pack(side="right")

        self.setup_body = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.setup_body.pack(fill="both", expand=True, padx=16)
        self.setup_body.grid_columnconfigure(0, weight=3, uniform="setup")
        self.setup_body.grid_columnconfigure(1, weight=2, uniform="setup")
        left = ctk.CTkFrame(self.setup_body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right = ctk.CTkFrame(self.setup_body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")

        website = card(left)
        website.pack(fill="x", pady=(0, 10))
        label(website, "1. Connect your website", size=16, bold=True).pack(
            anchor="w", padx=14, pady=(14, 0))
        self._setup_hint(website, "Use the running version of the site you want to test.", wraplength=360)
        self.set_url = self._field(website, "Website URL", placeholder="https://your-website.com")
        self._setup_hint(website, "Each task starts at this exact URL. Include further navigation in its steps.",
                         bottom=14, wraplength=360)

        agent = card(left)
        agent.pack(fill="x")
        label(agent, "2. Choose your test agent", size=16, bold=True).pack(
            anchor="w", padx=14, pady=(14, 0))
        self._setup_hint(agent, "Choose the browser engine and add its API key.", wraplength=360)
        label(agent, "Browser engine", size=12, color=C["muted"]).pack(anchor="w", padx=14, pady=(8, 2))
        self.set_engine = ctk.CTkOptionMenu(
            agent, values=["skyvern", "browser-use"], command=self._change_engine,
        )
        self.set_engine.pack(anchor="w", padx=14)
        self.set_key_label = label(agent, "", size=12, color=C["muted"], bold=True)
        self.set_key_label.pack(anchor="w", padx=14, pady=(8, 2))
        self.set_key = entry(agent, placeholder_text="Enter your provider API key")
        self.set_key.pack(fill="x", padx=14)
        self.set_key.configure(show="*")
        self.set_engine_note = self._setup_hint(agent, "", wraplength=360)
        self.set_model = self._field(agent, "Model (browser-use only)")
        self._setup_hint(agent, "Save setup to apply key, model and website changes.", bottom=14, wraplength=360)

        automation = card(right)
        automation.pack(fill="x", pady=(0, 10))
        label(automation, "3. Automate with Git", size=16, bold=True).pack(
            anchor="w", padx=14, pady=(14, 0))
        self._setup_hint(automation, "Optional · Connect a local repository to check your site after each commit.")
        self.set_repo = self._field(automation, "Local Git repository", placeholder="Choose a repository folder")
        ghost_btn(automation, "Browse for repository", self.pick_repo).pack(
            anchor="w", padx=14, pady=(8, 6))
        self.set_auto = ctk.CTkSwitch(
            automation,
            text="Test after each commit",
            font=(FONT, 13),
            text_color=C["text"],
            progress_color=C["accent"],
        )
        self.set_auto.pack(anchor="w", padx=14, pady=(10, 6))
        self._setup_hint(automation, "Your website must already serve the version you want to check. "
                         "Clear the repository field to disconnect it.", bottom=14)

        next_step = card(right)
        next_step.pack(fill="x")
        label(next_step, "What happens next?", size=16, bold=True).pack(
            anchor="w", padx=14, pady=(14, 0))
        self._setup_hint(next_step, "Add a regression task\nDescribe a customer flow, its prerequisites and the result you expect.")
        self._setup_hint(next_step, "Run the agent\nChoose tasks, watch progress and review a result for each flow.")
        self._setup_hint(next_step, "Review your history\nFind previous reports and keep track of queued commit checks.", bottom=14)
        ghost_btn(next_step, "View run history →", lambda: self.show_page("Run History")).pack(
            fill="x", padx=14, pady=(0, 14))
        self.refresh_settings()

    def _setup_hint(self, parent, text, bottom=0, wraplength=260):
        hint = label(parent, text, size=11, color=C["muted"], justify="left", anchor="w", wraplength=wraplength)
        hint.pack(fill="x", padx=14, pady=(6, bottom))
        return hint

    def _field(self, parent, name, placeholder=""):
        label(parent, name, size=12, color=C["muted"], bold=True).pack(
            anchor="w", padx=14, pady=(8, 2)
        )
        box = entry(parent, placeholder_text=placeholder)
        box.pack(fill="x", padx=14)
        return box

    def refresh_settings(self) -> None:
        if not hasattr(self, "set_key"):
            return
        # Navigation should keep a setup draft until the user saves it.
        if getattr(self, "_settings_loaded", False):
            self.refresh_journey()
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
        self._settings_loaded = True
        self.refresh_journey()

    def refresh_journey(self) -> None:
        if not hasattr(self, "setup_summary"):
            return
        key = "skyvern_key" if self.settings.get("engine") == "skyvern" else "openai_key"
        has_key = bool(self.settings.get(key))
        selected = sum(task.enabled for task in self.tasks)
        self.setup_summary.configure(text=(
            "API key added · Define your regression tasks next." if has_key and not self.tasks else
            f"API key added · {selected} tasks selected for your next run." if has_key else
            "Start here · Add your test agent's API key, then save your setup."
        ))
        for button, text in zip(self.journey_buttons, (
            "1 · Set up your website\n" + ("API key added" if has_key else "Add your API key"),
            f"2 · Define regression tasks\n{len(self.tasks)} saved · {selected} selected",
            "3 · Run & review\n" + ("Agent running" if self.active_run else f"{len(self.history)} runs in history"),
        )):
            button.configure(text=text)
        repo = bool(self.settings.get("repo_path"))
        self.sync_dot.configure(text=(
            "● Commit checks enabled" if repo and self.settings.get("auto_run") else
            "● Repository selected" if repo else "● Manual testing"
        ))

    def _continue_to_tasks(self) -> None:
        if self.save_settings():
            self.show_page("Regression Tasks")

    def _show_engine_key(self, engine) -> None:
        self._key_engine = engine
        skyvern = engine == "skyvern"
        self.set_key_label.configure(text="Skyvern API key" if skyvern else "OpenAI API key")
        self.set_key.delete("0", "end")
        self.set_key.insert(0, self._key_drafts["skyvern_key" if skyvern else "openai_key"])
        self.set_engine_note.configure(text=(
            "Broad functional checks: if the requested flow works, it passes. Unrelated app issues do not fail the task. "
            "Skyvern uses a cloud browser and needs a publicly reachable site URL."
            if skyvern else "Functional checks with detailed logs: passes when your requested flow works. "
            "Unrelated page, console or background request errors are logged without failing the task. "
            "Uses your OpenAI API key and a local browser."
        ))
        self.set_model.configure(state="disabled" if skyvern else "normal")
        self.ai_model.configure(text="Skyvern" if skyvern else "browser-use")

    def _change_engine(self, engine) -> None:
        key = "skyvern_key" if self._key_engine == "skyvern" else "openai_key"
        self._key_drafts[key] = self.set_key.get().strip()
        self._show_engine_key(engine)
        self.settings["engine"] = engine
        self.save_state()
        self.refresh_run()
        self.settings_note.configure(text="Engine selected. Save setup to apply API key and model changes.")
        self.refresh_journey()

    def pick_repo(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.set_repo.delete("0", "end")
            self.set_repo.insert(0, path)

    def save_settings(self) -> bool:
        from .agent_runner import target_url
        try:
            target_url(self.set_url.get().strip() or "http://localhost:3000", "/")
            repo_path = self.set_repo.get().strip()
            if repo_path:
                import git
                with git.Repo(repo_path):
                    pass
        except Exception as exc:
            self.settings_note.configure(text=f"Check your setup: {exc}")
            return False
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
        self.ai_model.configure(text="Skyvern" if self.settings["engine"] == "skyvern" else "browser-use")
        self.settings_note.configure(text="Setup saved. Next, add the customer flows you want to protect.")
        self.monitor.start(self.settings["repo_path"])
        self.refresh_run()
        self.refresh_journey()
        return True
