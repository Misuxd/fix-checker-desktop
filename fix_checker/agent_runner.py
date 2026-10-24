"""AI browser engines isolated from Tk on one background asyncio loop."""
from __future__ import annotations

import asyncio
import copy
import json
import os
import queue
import socket
import subprocess
import tempfile
import threading
from concurrent.futures import Future
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .models import SuiteReport, TaskResult, TestReport


def target_url(base: str, path: str | None = None) -> str:
    base = base.strip()
    if urlsplit(base).scheme not in ("http", "https") or not urlsplit(base).hostname:
        raise ValueError("Base site URL must be an absolute http:// or https:// URL.")
    if path is None:
        return base
    base = base.rstrip("/") + "/"
    path = path.strip() or "/"
    if path.startswith("//"):
        raise ValueError("Use a path or a complete http:// or https:// URL.")
    url = urljoin(base, path)
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
        raise ValueError("Target must be an http:// or https:// URL.")
    return url


class BrowserAgentRunner:
    def __init__(self) -> None:
        self.steps: queue.Queue[dict] = queue.Queue()
        self.loop = asyncio.new_event_loop()
        self._job: Future | None = None
        self._closed = False
        self._task = None
        self._step_number = 0
        self._secrets = []
        self._pending_cases = []
        self._current_case = None
        self._case_results = []
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        async def shutdown():
            if self._task is not None:
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
            self.loop.stop()
        if not self.loop.is_closed():
            asyncio.run_coroutine_threadsafe(shutdown(), self.loop)

    def cancel(self) -> None:
        if self.busy:
            self.loop.call_soon_threadsafe(self._cancel_tasks)

    def _cancel_tasks(self):
        if self._task is not None:
            self._task.cancel()

    def move_pending_task(self, task_id, direction):
        if self.busy and direction in (-1, 1):
            self.loop.call_soon_threadsafe(self._move_pending_task, task_id, direction)

    def _move_pending_task(self, task_id, direction):
        index = next((i for i, case in enumerate(self._pending_cases) if case["id"] == task_id), -1)
        destination = index + direction
        if index >= 0 and 0 <= destination < len(self._pending_cases):
            self._pending_cases[index], self._pending_cases[destination] = (
                self._pending_cases[destination], self._pending_cases[index])
            self._publish_queue()

    def _publish_queue(self):
        cases = [{"id": result.task_id, "name": result.task_name, "status": result.status.lower()}
                 for result in self._case_results]
        if self._current_case:
            cases.append({**self._current_case, "status": "running"})
        cases.extend({**case, "status": "queued"} for case in self._pending_cases)
        self.steps.put({"kind": "task_queue", "tasks": [
            {key: case[key] for key in ("id", "name", "status")} for case in cases]})

    @property
    def busy(self) -> bool:
        return self._job is not None and not self._job.done()

    def submit(self, settings, tasks, headless) -> bool:
        if self.busy or self._closed:
            return False
        self._job = asyncio.run_coroutine_threadsafe(
            self._run(dict(settings), copy.deepcopy(tasks), headless), self.loop
        )
        return True

    @staticmethod
    def build_prompt(settings, steps) -> str:
        base = settings.get("base_url") or "http://localhost:3000"
        lines = [f"Target page: {target_url(base)}",
                 f"Regression task: {settings.get('task_name', 'Selected task')}", steps.strip()]
        if settings.get("engine") == "skyvern":
            lines += [
                "Use a broad functional check of the requested flow and its expected outcome.",
                "If the requested flow works, return PASSED. Do not fail the task for unrelated console errors,",
                "warnings, failed background requests or cosmetic issues that do not block the expected outcome.",
                "Return FAILED when the requested flow is blocked or its expected outcome is not met.",
            ]
        else:
            lines += [
                "Use detailed checks: verify expected outcomes, missing elements, page errors, console errors and HTTP 404/500.",
                "Report other observed bugs in the app even if the requested flow works.",
                "An observed page error, console error, HTTP 404 or HTTP 5xx makes this task FAILED, even if its functional outcome succeeds.",
            ]
        lines += [
            "Act as a real user. Execute this test; never invent credentials or evidence.",
            "If this test fails, return FAILED with evidence. Do not repair the site or bypass assertions.",
            "If prerequisites or credentials are missing, report FAILED and explain what is missing.",
            "Return PASSED only when this test was executed and its expected outcome verified under the selected check policy.",
            "Return ONLY JSON matching the report schema: status (PASSED/FAILED), stopped_at_step",
            "(integer), stopped_url, failed_test_name and error_details. Identify the exact failing",
            "step, URL and element; on success use empty failure fields.",
        ]
        return "\n".join(lines)

    def _log(self, text):
        for secret in self._secrets:
            text = text.replace(secret, "[redacted]")
        self.steps.put({"kind": "log", "text": text})

    async def _run(self, settings, tasks, headless):
        self._task = asyncio.current_task()
        self._case_results = []
        self._current_case = None
        self._pending_cases = []
        self._pending_cases.extend(dict(id=task.id, name=task.name, steps=task.steps)
                                   for task in tasks if task.enabled)
        total = len(self._pending_cases)
        if not total:
            self.steps.put({"kind": "done", "report": self._failure("Select at least one regression task.")})
            return
        while self._pending_cases:
            self._current_case = self._pending_cases.pop(0)
            self._publish_queue()
            case = self._current_case
            self._log(f"Running task {len(self._case_results) + 1}/{total}: {case['name']}")
            cancelled = False
            try:
                case_settings = {**settings, "task_name": case["name"]}
                report = await self._execute_case(case_settings, case["steps"], headless)
            except asyncio.CancelledError:
                cancelled = True
                report = self._failure("Run cancelled by user.")
            result = TaskResult(**report.model_dump(), task_id=case["id"], task_name=case["name"])
            self._case_results.append(result)
            self.steps.put({"kind": "task_result", "result": result.model_dump(), "total": total})
            self._log(f"{case['name']}: {result.status} {result.error_details}".strip())
            self._current_case = None
            if cancelled:
                for pending in self._pending_cases:
                    skipped = TaskResult(**self._failure("Not run: cancelled by user.").model_dump(),
                                         task_id=pending["id"], task_name=pending["name"])
                    self._case_results.append(skipped)
                    self.steps.put({"kind": "task_result", "result": skipped.model_dump(), "total": total})
                self._pending_cases.clear()
            self._publish_queue()
        failed = [result for result in self._case_results if result.status == "FAILED"]
        first = failed[0] if failed else self._case_results[-1]
        summary = SuiteReport(
            status="FAILED" if failed else "PASSED", stopped_at_step=first.stopped_at_step,
            stopped_url=first.stopped_url, failed_test_name=first.task_name if failed else "",
            error_details=(first.error_details if total == 1 else
                           f"{total - len(failed)}/{total} passed; {len(failed)} failed."),
            task_results=self._case_results,
        )
        self.steps.put({"kind": "done", "report": summary})

    async def _execute_case(self, settings, steps, headless):
        report = None
        url = ""
        diagnostics = []
        self._secrets = [value for value in (
            settings.get("openai_key"), settings.get("skyvern_key"),
            os.getenv("OPENAI_API_KEY"), os.getenv("SKYVERN_API_KEY"),
        ) if value]
        try:
            url = target_url(settings.get("base_url", ""))
            skyvern = settings.get("engine") == "skyvern"
            key_name, env_name, provider = (
                ("skyvern_key", "SKYVERN_API_KEY", "Skyvern") if skyvern else
                ("openai_key", "OPENAI_API_KEY", "OpenAI")
            )
            key = settings.get(key_name) or os.getenv(env_name, "")
            if not key:
                raise ValueError(f"{provider} API key is missing. Set it in Settings or {env_name}.")
            self._step_number = 0
            if not steps.strip():
                raise ValueError("Add steps and an expected result for this regression task.")
            prompt = self.build_prompt(settings, steps)
            self._log(f"Starting {settings.get('engine', 'browser-use')} at {url}")
            async with asyncio.timeout(float(settings.get("timeout", 900))):
                if skyvern:
                    settings["show_browser"] = not headless
                    report = await self._skyvern(settings, key, url, prompt)
                else:
                    error_event = asyncio.Event()
                    async with self._browser(headless, diagnostics, error_event) as address:
                        work = asyncio.create_task(self._browser_use(settings, key, prompt, address))
                        failure = asyncio.create_task(error_event.wait())
                        try:
                            await asyncio.wait([work, failure], return_when=asyncio.FIRST_COMPLETED)
                            if diagnostics:
                                work.cancel()
                                await asyncio.gather(work, return_exceptions=True)
                                first = diagnostics[0]
                                report = TestReport(
                                    status="FAILED", stopped_at_step=first["step"],
                                    stopped_url=first["url"], failed_test_name="Browser diagnostics",
                                    error_details=first["text"],
                                )
                            else:
                                report = await work
                        finally:
                            work.cancel()
                            failure.cancel()
                            await asyncio.gather(work, failure, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}"
            for secret in self._secrets:
                text = text.replace(secret, "[redacted]")
            self.steps.put({"kind": "error", "text": text})
            report = self._failure(text, url)
        return report or self._failure("No report returned.", url)

    @staticmethod
    def _failure(text, url=""):
        return TestReport(status="FAILED", stopped_at_step=0, stopped_url=url,
                          failed_test_name="Agent execution", error_details=text)

    @asynccontextmanager
    async def _browser(self, headless, diagnostics, error_event=None):
        from playwright.async_api import async_playwright
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix="fix-checker-") as profile:
            async with async_playwright() as pw:
                context = await pw.chromium.launch_persistent_context(
                    profile, headless=headless, args=[f"--remote-debugging-port={port}"],
                )
                def attach(page):
                    def record(text, url=None):
                        item = {"url": url or page.url, "text": text, "step": self._step_number}
                        if len(diagnostics) < 100:
                            diagnostics.append(item)
                        self._log(f"Browser error at {item['url']}: {text}")
                        if error_event is not None:
                            error_event.set()
                    page.on("pageerror", lambda error: record(str(error)))
                    page.on("console", lambda msg: record(msg.text) if msg.type == "error" else None)
                    page.on("response", lambda response: record(
                        f"HTTP {response.status}: {response.url}", response.url
                    ) if response.status == 404 or response.status >= 500 else None)
                    page.on("framenavigated", lambda frame: self._log(f"Page: {frame.url}")
                            if frame == page.main_frame else None)
                context.on("page", attach)
                for page in context.pages:
                    attach(page)
                try:
                    yield f"http://127.0.0.1:{port}"
                finally:
                    await context.close()

    async def _browser_use(self, settings, key, prompt, address):
        from browser_use import Agent, Browser, ChatOpenAI
        llm = ChatOpenAI(model=settings.get("model") or "gpt-6-luna", api_key=key,
                         temperature=None, frequency_penalty=None, reasoning_effort="none",
                         reasoning_models=["gpt-5", "gpt-6", "o1", "o3", "o4"])
        browser = Browser(cdp_url=address)
        async def step(state, output, number):
            self._step_number = number
            actions = [a.model_dump(exclude_none=True) for a in output.action]
            self._log(f"Step {number} at {state.url}: {json.dumps(actions, ensure_ascii=False)}")
        try:
            agent = Agent(task=prompt, llm=llm, browser=browser,
                          output_model_schema=TestReport, register_new_step_callback=step,
                          enable_signal_handler=False, use_judge=False,
                          file_system_path=str(Path(__file__).resolve().parent.parent / "artifacts"))
            history = await agent.run(max_steps=100)
            report = self._extract_report(history.final_result())
            if not history.is_successful() and report.status == "PASSED":
                return self._failure("Agent did not complete successfully.")
            return report
        finally:
            await browser.stop()

    async def _skyvern(self, settings, key, url, prompt):
        from .config import APP_DIR
        executable = APP_DIR / ".skyvern-venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not executable.exists():
            raise RuntimeError("Skyvern environment missing. Run setup.ps1 first.")
        process = await asyncio.create_subprocess_exec(
            str(executable), "-u", "-m", "fix_checker.skyvern_worker", cwd=str(APP_DIR),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, limit=1024 * 1024,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        report = None
        try:
            payload = dict(key=key, url=url, prompt=prompt,
                           show_browser=bool(settings.get("show_browser")))
            process.stdin.write((json.dumps(payload) + "\n").encode())
            await process.stdin.drain()
            while line := await process.stdout.readline():
                text = line.decode("utf-8", errors="replace").rstrip().replace(key, "[redacted]")
                if text.startswith("FIX_CHECKER_EVENT "):
                    event = json.loads(text[len("FIX_CHECKER_EVENT "):])
                    if event["kind"] == "done":
                        report = self._extract_report(event["report"])
                    elif event["kind"] == "browser_view":
                        self.steps.put(event)
                    else:
                        if "step" in event:
                            self._step_number = event["step"] or 0
                        self._log(event.get("text", ""))
                elif text:
                    self._log(text[:2000])
            code = await process.wait()
            if code or report is None:
                raise RuntimeError(f"Skyvern worker exited ({code}) without a valid report. See live log.")
            return report
        finally:
            if process.returncode is None:
                try:
                    process.stdin.write(b'{"cancel": true}\n')
                    await process.stdin.drain()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except (BrokenPipeError, ConnectionResetError, asyncio.TimeoutError):
                    if process.returncode is None:
                        process.terminate()
                        await process.wait()
            process.stdin.close()

    @staticmethod
    def _extract_report(value) -> TestReport:
        if isinstance(value, TestReport):
            return value
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("```json") and value.endswith("```"):
                value = value[7:-3].strip()
            return TestReport.model_validate_json(value)
        return TestReport.model_validate(value)
