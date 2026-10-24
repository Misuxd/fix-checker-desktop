import asyncio
import json
import queue
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
            [RegressionTask(name="SELECTED", path="/x", steps="Click"),
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
                return item["report"]

    def test_missing_key_emits_one_failure_and_completes(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            self.assertTrue(self.runner.submit({"base_url": "http://localhost"}, "/", "click", [], True))
            result = self.done()
        self.assertEqual(result.status, "FAILED")
        self.assertIn("API key", result.error_details)

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


class SkyvernContract(unittest.IsolatedAsyncioTestCase):
    async def test_schema_status_polling_output_and_cleanup(self):
        from fix_checker.skyvern_worker import run
        for status in ("completed", "failed"):
            client = SimpleNamespace(
                run_task=AsyncMock(return_value=SimpleNamespace(run_id="tsk_test")),
                get_run=AsyncMock(return_value=SimpleNamespace(status=status, step_count=4,
                    output=report().model_dump(), failure_reason="Button missing")),
                aclose=AsyncMock(), cancel_run=AsyncMock())
            Skyvern = Mock(local=Mock(return_value=client))
            RunStatus = lambda value: SimpleNamespace(is_final=lambda: True)
            modules = {"skyvern": SimpleNamespace(Skyvern=Skyvern, RunStatus=RunStatus),
                       "skyvern.schemas.llm": SimpleNamespace(LLMConfig=Mock())}
            events = []
            with patch.dict("sys.modules", modules):
                result = await run(dict(model="gpt-6-luna", key="dummy", url="http://localhost",
                                        address="http://localhost:9222", prompt="Click"), events.append)
            self.assertEqual(result.status, "PASSED" if status == "completed" else "FAILED")
            schema = client.run_task.call_args.kwargs["data_extraction_schema"]
            self.assertEqual(set(schema["required"]), set(report().model_dump()))
            self.assertTrue(events)
            client.aclose.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
