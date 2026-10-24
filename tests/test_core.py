import asyncio
import json
import queue
import sys
import tempfile
import threading
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import Mock, patch
from unittest.mock import AsyncMock
from types import SimpleNamespace

from pydantic import ValidationError

from fix_checker.agent_runner import BrowserAgentRunner, target_url
from fix_checker.models import RegressionTask, RunRecord, TestReport, load_json, save_json


def report(status="PASSED"):
    return TestReport(status=status, stopped_at_step=3, stopped_url="http://localhost/done",
                      failed_test_name="", error_details="")


class ReportsAndPaths(unittest.TestCase):
    def test_report_requires_all_fields_and_never_guesses_success(self):
        for value in ["not passed, failed", '{"status":"PASSED"}', None, {"status": "unknown"}]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                BrowserAgentRunner._extract_report(value)
        self.assertEqual(BrowserAgentRunner._extract_report(report().model_dump_json()).status, "PASSED")
        self.assertEqual(report("failed").status, "FAILED")

    def test_urls_and_selected_flows(self):
        self.assertEqual(target_url("http://localhost:3000", "/login"), "http://localhost:3000/login")
        self.assertEqual(target_url("https://site.test", "https://other.test/path"), "https://other.test/path")
        for base, path in [("broken", "/"), ("https://site.test", "file:///a"), ("https://site.test", "//other")]:
            with self.assertRaises(ValueError):
                target_url(base, path)
        text = BrowserAgentRunner.build_prompt(
            {"base_url": "https://site.test", "test_current_fix": False}, "/", "EXCLUDED_FIX",
            [RegressionTask(name="SELECTED", steps="Open /x and click"),
             RegressionTask(name="EXCLUDED_TASK", enabled=False)])
        self.assertIn("SELECTED", text)
        self.assertNotIn("EXCLUDED", text)

    def test_atomic_storage_and_corrupt_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            save_json(path, {"saved": True})
            self.assertEqual(load_json(path, {}), {"saved": True})
            self.assertFalse(path.with_suffix(".json.tmp").exists())
            path.write_text("invalid", encoding="utf-8")
            self.assertEqual(load_json(path, []), [])


class RunnerLifecycle(unittest.TestCase):
    def setUp(self):
        self.runner = BrowserAgentRunner()

    def tearDown(self):
        self.runner.close()
        self.runner.thread.join(timeout=10)
        self.assertFalse(self.runner.thread.is_alive())

    def done(self):
        while True:
            item = self.runner.steps.get(timeout=10)
            if item["kind"] == "done":
                self.runner._job.result(timeout=10)
                return item["report"]

    def test_missing_key_emits_one_failure_and_completes(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            self.assertTrue(self.runner.submit({"base_url": "http://localhost"}, "/", "click", [], True))
            result = self.done()
        self.assertEqual(result.status, "FAILED")
        self.assertIn("API key", result.error_details)

    def test_missing_provider_key_never_falls_back_to_other_provider(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "SKYVERN_API_KEY": ""}):
            for engine, other_key, provider, env_name in (
                ("skyvern", "openai_key", "Skyvern", "SKYVERN_API_KEY"),
                ("browser-use", "skyvern_key", "OpenAI", "OPENAI_API_KEY"),
            ):
                with self.subTest(engine=engine):
                    self.runner.submit({"base_url": "http://localhost", "engine": engine,
                                        other_key: "other-provider-secret"}, "/", "Click", [], True)
                    result = self.done()
                    self.assertEqual(result.status, "FAILED")
                    self.assertIn(f"{provider} API key is missing", result.error_details)
                    self.assertIn(env_name, result.error_details)

    def test_skyvern_uses_own_saved_key_or_environment_without_local_browser(self):
        self.runner._browser = Mock(side_effect=AssertionError("Skyvern must use its cloud browser"))
        self.runner._skyvern = AsyncMock(return_value=report())
        for saved_key in ("saved-skyvern-key", ""):
            with self.subTest(saved_key=bool(saved_key)), patch.dict(
                "os.environ", {"SKYVERN_API_KEY": "env-skyvern-key", "OPENAI_API_KEY": "openai-key"},
            ):
                settings = {"base_url": "https://example.test", "engine": "skyvern",
                            "skyvern_key": saved_key, "openai_key": "saved-openai-key"}
                self.runner.submit(settings, "/", "Click", [], True)
                self.assertEqual(self.done().status, "PASSED")
                self.assertEqual(self.runner._skyvern.call_args.args[1], saved_key or "env-skyvern-key")
        self.runner._browser.assert_not_called()

    def test_reject_overlap_and_clean_cancel(self):
        started = threading.Event()
        cleaned = threading.Event()
        @asynccontextmanager
        async def browser(*args):
            try:
                yield "http://localhost:1234"
            finally:
                cleaned.set()
        async def engine(*args):
            started.set()
            await asyncio.sleep(60)
        self.runner._browser = browser
        self.runner._browser_use = engine
        settings = {"base_url": "http://localhost", "openai_key": "dummy"}
        self.runner.submit(settings, "/", "Click", [], True)
        self.assertTrue(started.wait(5))
        self.assertFalse(self.runner.submit(settings, "/", "Click", [], True))
        self.runner.cancel()
        self.assertEqual(self.done().status, "FAILED")
        self.assertTrue(cleaned.is_set())

    def test_http_failure_stops_agent_and_preserves_first_error(self):
        cancelled = threading.Event()
        @asynccontextmanager
        async def browser(headless, diagnostics, error_event):
            async def error():
                await asyncio.sleep(0.05)
                diagnostics.append(dict(url="http://localhost/broken", step=2, text="HTTP 500"))
                error_event.set()
            task = asyncio.create_task(error())
            try:
                yield "http://localhost:1234"
            finally:
                await task
        async def engine(*args):
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()
        self.runner._browser = browser
        self.runner._browser_use = engine
        self.runner.submit({"base_url": "http://localhost", "openai_key": "dummy"}, "/", "Click", [], True)
        result = self.done()
        self.assertEqual((result.status, result.stopped_at_step, result.error_details), ("FAILED", 2, "HTTP 500"))
        self.assertTrue(cancelled.is_set())


class GitAndUIState(unittest.TestCase):
    def test_history_refreshes_every_minute_until_closed(self):
        from fix_checker.app import DeveloperAppUI
        app = SimpleNamespace(_closing=False, refresh_history=Mock(), after=Mock(),
                              _refresh_periodic=Mock())
        DeveloperAppUI._refresh_periodic(app)
        app.refresh_history.assert_called_once_with()
        app.after.assert_called_once_with(60_000, app._refresh_periodic)
        app._closing = True
        DeveloperAppUI._refresh_periodic(app)
        self.assertEqual(app.after.call_count, 1)
        self.assertEqual(app.refresh_history.call_count, 1)

    def test_legacy_regression_tasks_load_without_path(self):
        from fix_checker.app import DeveloperAppUI
        saved = {"id": "old-task", "name": "Sign in", "path": "/login",
                 "steps": "Open /login and sign in", "enabled": True}
        with patch("fix_checker.app.load_json", return_value=[saved]):
            tasks = DeveloperAppUI._load_tasks(Mock())
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].name, "Sign in")
        self.assertEqual(tasks[0].steps, saved["steps"])
        self.assertFalse(hasattr(tasks[0], "path"))

    def test_skyvern_live_event_opens_viewer(self):
        from fix_checker.app import DeveloperAppUI
        app = SimpleNamespace(_append_log=Mock())
        url = "https://app.skyvern.com/browser-session/pbs_test"
        with patch("fix_checker.app.webbrowser.open_new_tab", return_value=True) as open_tab:
            DeveloperAppUI._handle_step(app, {"kind": "browser_view", "url": url})
        open_tab.assert_called_once_with(url)
        app._append_log.assert_called_once_with(f"Live browser: {url}")

    def test_git_monitor_restart_and_new_commit(self):
        import git
        from fix_checker.git_monitor import GitMonitor
        with tempfile.TemporaryDirectory() as folder:
            repo = git.Repo.init(folder)
            seen = queue.Queue()
            monitor = GitMonitor(lambda *args: seen.put(args), interval=0.05)
            monitor.start(folder)
            monitor.start(folder)
            actor = git.Actor("Test", "test@example.test")
            commit = repo.index.commit("First", author=actor, committer=actor)
            self.assertEqual(seen.get(timeout=5)[0], commit.hexsha)
            monitor.start("")
            self.assertIsNone(monitor.current())
            self.assertFalse(monitor._thread.is_alive())
            repo.close()

    def test_result_is_assigned_to_active_run_not_newest_commit(self):
        from fix_checker.app import DeveloperAppUI
        app = Mock()
        active = RunRecord(title="Active", status="running")
        newest = RunRecord(title="New", status="queued")
        app.active_run, app.current = active, newest
        DeveloperAppUI._finish_run(app, report())
        self.assertEqual(active.status, "passed")
        self.assertEqual(newest.status, "queued")
        self.assertIsNone(app.active_run)

    def test_empty_saved_task_list_stays_empty(self):
        from fix_checker.app import DeveloperAppUI
        with patch("fix_checker.app.load_json", return_value=[]):
            self.assertEqual(DeveloperAppUI._load_tasks(Mock()), [])

    def test_settings_load_provider_keys_separately(self):
        from fix_checker.app import DeveloperAppUI
        app = SimpleNamespace(_defaults=DeveloperAppUI._defaults)
        with patch("fix_checker.app.load_json", return_value={"openai_key": "saved-openai"}), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "env-openai", "SKYVERN_API_KEY": "env-skyvern"}):
            settings = DeveloperAppUI._load_settings(app)
        self.assertEqual(settings["openai_key"], "saved-openai")
        self.assertEqual(settings["skyvern_key"], "env-skyvern")


class SkyvernContract(unittest.IsolatedAsyncioTestCase):
    async def test_live_view_only_creates_session_when_enabled_and_always_closes_it(self):
        from fix_checker.skyvern_worker import run
        for show_browser, cancel in ((False, False), (True, False), (True, True)):
            with self.subTest(show_browser=show_browser, cancel=cancel):
                viewer_url = "https://app.skyvern.com/browser-session/pbs_test"
                client = SimpleNamespace(
                    create_browser_session=AsyncMock(return_value=SimpleNamespace(
                        browser_session_id="pbs_test", app_url=viewer_url)),
                    close_browser_session=AsyncMock(),
                    run_task=AsyncMock(return_value=SimpleNamespace(run_id="tsk_test")),
                    get_run=AsyncMock(return_value=SimpleNamespace(status="completed", step_count=1,
                        output=report().model_dump()), side_effect=asyncio.CancelledError if cancel else None),
                    cancel_run=AsyncMock(), aclose=AsyncMock())
                modules = {"skyvern": SimpleNamespace(Skyvern=Mock(return_value=client),
                    RunStatus=lambda _: SimpleNamespace(is_final=lambda: True))}
                events = []
                with patch.dict("sys.modules", modules):
                    payload = dict(key="dummy", url="https://example.test", prompt="Click",
                                   show_browser=show_browser)
                    if cancel:
                        with self.assertRaises(asyncio.CancelledError):
                            await run(payload, events.append)
                    else:
                        self.assertEqual((await run(payload, events.append)).status, "PASSED")
                if show_browser:
                    self.assertIn({"kind": "browser_view", "url": viewer_url}, events)
                    self.assertEqual(client.run_task.call_args.kwargs["browser_session_id"], "pbs_test")
                    client.close_browser_session.assert_awaited_once_with("pbs_test")
                else:
                    client.create_browser_session.assert_not_awaited()
                    client.close_browser_session.assert_not_awaited()
                    self.assertFalse(any(event["kind"] == "browser_view" for event in events))
                client.aclose.assert_awaited_once()

    async def test_worker_pipe_completion_and_cancellation(self):
        script = """
import asyncio
from fix_checker import skyvern_worker as worker
async def fake_run(payload):
    try:
        if payload.get("wait"):
            await asyncio.sleep(60)
        return worker.TestReport(status="PASSED", stopped_at_step=1,
            stopped_url=payload["url"], failed_test_name="", error_details="")
    finally:
        worker.emit({"kind": "log", "text": "cleanup complete"})
worker.run = fake_run
worker.main()
"""
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-u", "-c", script,
                    cwd=str(Path(__file__).resolve().parent.parent),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                try:
                    payload = dict(key="dummy", url="https://example.test", wait=cancel)
                    commands = json.dumps(payload) + "\n" + ('{"cancel":true}\n' if cancel else "")
                    process.stdin.write(commands.encode())
                    await process.stdin.drain()
                    output = (await asyncio.wait_for(process.stdout.read(), timeout=10)).decode()
                    self.assertEqual(await process.wait(), 0, output)
                    events = [json.loads(line[len("FIX_CHECKER_EVENT "):])
                              for line in output.splitlines() if line.startswith("FIX_CHECKER_EVENT ")]
                    self.assertIn({"kind": "log", "text": "cleanup complete"}, events)
                    self.assertEqual(events[-1]["report"]["status"], "FAILED" if cancel else "PASSED")
                finally:
                    if process.returncode is None:
                        process.kill()
                        await process.wait()
                    process.stdin.close()

    async def test_schema_status_polling_output_and_cleanup(self):
        from fix_checker.skyvern_worker import run
        for status in ("completed", "failed"):
            client = SimpleNamespace(
                run_task=AsyncMock(return_value=SimpleNamespace(run_id="tsk_test")),
                get_run=AsyncMock(return_value=SimpleNamespace(status=status, step_count=4,
                    output=report().model_dump(), failure_reason="Button missing")),
                aclose=AsyncMock(), cancel_run=AsyncMock())
            Skyvern = Mock(return_value=client)
            RunStatus = lambda value: SimpleNamespace(is_final=lambda: True)
            modules = {"skyvern": SimpleNamespace(Skyvern=Skyvern, RunStatus=RunStatus)}
            events = []
            with patch.dict("sys.modules", modules):
                result = await run(dict(key="skyvern-secret", url="https://example.test",
                                       prompt="Click"), events.append)
            self.assertEqual(result.status, "PASSED" if status == "completed" else "FAILED")
            Skyvern.assert_called_once_with(api_key="skyvern-secret")
            self.assertNotIn("browser_address", client.run_task.call_args.kwargs)
            self.assertNotIn("model", client.run_task.call_args.kwargs)
            schema = client.run_task.call_args.kwargs["data_extraction_schema"]
            self.assertEqual(set(schema["required"]), set(report().model_dump()))
            self.assertTrue(events)
            client.aclose.assert_awaited_once()

    async def test_cancel_stops_cloud_run_and_closes_client(self):
        from fix_checker.skyvern_worker import run
        client = SimpleNamespace(
            run_task=AsyncMock(return_value=SimpleNamespace(run_id="tsk_cancel")),
            get_run=AsyncMock(side_effect=asyncio.CancelledError),
            cancel_run=AsyncMock(), aclose=AsyncMock())
        modules = {"skyvern": SimpleNamespace(Skyvern=Mock(return_value=client), RunStatus=Mock())}
        with patch.dict("sys.modules", modules), self.assertRaises(asyncio.CancelledError):
            await run(dict(key="skyvern-secret", url="https://example.test", prompt="Click"))
        client.cancel_run.assert_awaited_once_with("tsk_cancel")
        client.aclose.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
