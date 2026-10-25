"""Real Tk and real Chromium smoke checks; no paid LLM calls."""
import asyncio
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import customtkinter as ctk

from fix_checker.agent_runner import BrowserAgentRunner
from fix_checker.app import DeveloperAppUI
from fix_checker.models import RegressionTask, RunRecord
from fix_checker.models import SuiteReport, TaskResult, TestReport


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/broken":
            self.send_response(500)
            body = b"Broken page"
        else:
            self.send_response(200)
            body = b'<button id="save" onclick="this.textContent=\'Saved\'">Save</button>'
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def desktop():
    with patch.object(DeveloperAppUI, "_load_settings", return_value=DeveloperAppUI._defaults()), \
         patch.object(DeveloperAppUI, "_load_tasks", return_value=[RegressionTask(name="Test", steps="Click")]), \
         patch.object(DeveloperAppUI, "_load_history", return_value=[]), \
         patch.object(DeveloperAppUI, "save_state"):
        app = DeveloperAppUI()
        app.withdraw()
        try:
            for page in app.pages:
                app.show_page(page)
                app.update_idletasks()
            assert app.set_key_label.cget("text") == "Skyvern API key"
            assert app.ai_model.cget("text") == "Skyvern"
            assert app.set_model.cget("state") == "disabled"
            app.set_key.insert(0, "skyvern-draft")
            app.set_engine.set("browser-use")
            app._change_engine("browser-use")
            assert app.set_key_label.cget("text") == "OpenAI API key"
            assert app.ai_model.cget("text") == "browser-use"
            assert app.settings["engine"] == "browser-use"
            assert "logged without failing the task" in app.set_engine_note.cget("text")
            assert app.set_key.get() == ""
            assert app.set_model.cget("state") == "normal"
            app.set_key.insert(0, "openai-draft")
            app.set_engine.set("skyvern")
            app._change_engine("skyvern")
            assert app.set_key.get() == "skyvern-draft"
            assert app.ai_model.cget("text") == "Skyvern"
            assert app.settings["engine"] == "skyvern"
            assert "if the requested flow works, it passes" in app.set_engine_note.cget("text")
            app.save_settings()
            assert app.settings["skyvern_key"] == "skyvern-draft"
            assert app.settings["openai_key"] == "openai-draft"
            app.refresh_settings()
            assert app.set_key.get() == "skyvern-draft"
            app.show_page("Run Agent")
            assert app.run_headless.cget("state") == "normal"
            print("PASS: provider labels, separate key drafts, save/reload and model availability")

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            assert not hasattr(app, "run_path")
            assert not hasattr(app, "run_fix") and not hasattr(app, "current_fix")
            assert "Target path" not in [w.cget("text") for w in descendants(app.pages["Run Agent"])
                                          if isinstance(w, ctk.CTkLabel)]
            assert "Fix + trajectory" not in [w.cget("text") for w in descendants(app.pages["Run Agent"])
                                               if isinstance(w, ctk.CTkLabel)]
            assert all("Current fix" not in w.cget("text") for w in descendants(app.run_checks)
                       if isinstance(w, ctk.CTkCheckBox))
            saved_tasks = app.tasks
            app.tasks = []
            with patch.object(app.runner, "submit", return_value=True) as submit:
                app.launch_agent()
                submit.assert_not_called()
                queued = RunRecord(title="No selected tasks", tag="commit")
                app.history.insert(0, queued)
                app.launch_agent(queued)
                assert submit.call_args.args[1] == []
                app._finish_run(BrowserAgentRunner._failure("Select at least one regression task."))
                assert queued.status == "failed"
            app.history.clear()
            app.tasks = saved_tasks
            app.history.append(RunRecord(title="Refresh fixture", started=time.time(), status="passed"))
            app.refresh_history()
            fixture = app.history[-1]
            cached = app._home_rows[fixture.id]
            app.refresh_home()
            assert app._home_rows[fixture.id] is cached
            fixture.status = "failed"
            app.refresh_home()
            assert cached["status"].cget("text") == "FAILED"
            app.home_status.set("passed")
            app.refresh_home()
            assert cached["frame"].winfo_exists() and cached["position"] is None
            app.home_status.set("All statuses")
            app.refresh_home()
            assert app._home_rows[fixture.id] is cached and cached["position"] == 0
            print("PASS: Home reuses cards, updates status and filters without rebuilding rows")
            app.home_search.insert(0, "Refresh fixture")
            app.set_repo.insert(0, "unsaved repository draft")
            with patch("fix_checker.models.time.time", return_value=time.time() + 61):
                app._refresh_periodic()
            assert "1m ago" in [w.cget("text") for w in descendants(app.hist_list) if isinstance(w, ctk.CTkLabel)]
            assert "1m ago" in [w.cget("text") for w in descendants(app.home_list) if isinstance(w, ctk.CTkLabel)]
            assert app.home_search.get() == "Refresh fixture"
            assert app.set_repo.get() == "unsaved repository draft"
            print("PASS: minute refresh updates sidebar and home ages without clearing drafts or filters")

            app.settings["base_url"] = "http://localhost:3000/app/checks?mode=test"
            for engine in ("skyvern", "browser-use"):
                app.settings["engine"] = engine
                app.refresh_run()
                for show in (False, True):
                    app.run_headless.select() if show else app.run_headless.deselect()
                    app._save_browser_visibility()
                    with patch.object(app.runner, "submit", return_value=True) as submit:
                        app.launch_agent()
                    assert submit.call_args.kwargs["headless"] == (not show)
                    assert submit.call_args.args[1] == [task for task in app.tasks if task.enabled]
                    assert app.active_run.path == app.settings["base_url"]
                    assert app.settings["show_browser"] == show
                    assert app.run_headless.cget("state") == "disabled"
                    app._finish_run(TestReport(status="PASSED", stopped_at_step=1,
                        stopped_url="http://localhost", failed_test_name="", error_details=""))
                    assert app.run_headless.cget("state") == "normal"
            print("PASS: live switch controls the next run for both engines and is locked during a run")
            print("PASS: runs start at the configured site URL without a Target path field")

            app.add_task()
            app.update()
            dialog = next(w for w in app.winfo_children() if isinstance(w, ctk.CTkToplevel))
            fields = [w for w in descendants(dialog) if isinstance(w, ctk.CTkEntry)]
            assert len(fields) == 1, "Task dialog must only have the name entry"
            fields[0].insert(0, "New regression")
            steps = next(w for w in descendants(dialog) if isinstance(w, ctk.CTkTextbox))
            steps.insert("1.0", "Open the products page and click Save")
            save = next(w for w in descendants(dialog) if isinstance(w, ctk.CTkButton) and w.cget("text") == "Save task")
            save.invoke()
            assert app.tasks[-1].name == "New regression"
            assert not hasattr(app.tasks[-1], "path")
            for child in app.winfo_children():
                if child.winfo_toplevel() == child:
                    child.destroy()
            print("PASS: all desktop pages and regression task editor opened")

            # Bulk deletion updates the same history used by the sidebar and pending runs.
            app.home_search.delete(0, "end")
            active = RunRecord(title="Keep active", status="running")
            old = RunRecord(title="Delete this history", status="failed")
            waiting = RunRecord(title="Delete waiting run")
            app.history = [active, old, waiting]
            app.pending_runs = [waiting]
            app.active_run = active
            app.current = old
            app.refresh_history()
            app.select_all_history()
            assert app._history_selected == {old.id, waiting.id}
            assert app._home_rows[active.id]["checkbox"].cget("state") == "disabled"
            app.delete_selected_history()
            assert app.history == [active] and app.pending_runs == []
            sidebar_text = [w.cget("text") for w in descendants(app.hist_list) if isinstance(w, ctk.CTkLabel)]
            assert "Delete this history" not in sidebar_text and "Delete waiting run" not in sidebar_text
            assert "Keep active" in sidebar_text
            app.active_run = None
            app.refresh_home()
            app.select_all_history()
            app.delete_selected_history()
            assert app.history == [] and app._home_rows == {} and app.current is None
            print("PASS: select-all deletion clears Home and sidebar, removes queued runs, protects active run")

            app.tasks = [RegressionTask(name=f"Task {i}", steps="Click Save") for i in range(2)]
            app.show_page("Run Agent")
            app.deiconify()
            app.update()
            sizes = (app.run_checks._parent_canvas.winfo_height(), app.run_log.winfo_height())
            app.tasks.extend(RegressionTask(name=f"Task {i}", steps="Click Save") for i in range(2, 40))
            app.refresh_run()
            app.update()
            assert (app.run_checks._parent_canvas.winfo_height(), app.run_log.winfo_height()) == sizes
            assert app.run_checks._parent_canvas.yview()[1] < 1
            app.run_checks._parent_canvas.yview_moveto(1)
            assert app.run_checks._parent_canvas.yview()[0] > 0
            app.geometry("1280x950")
            app.update()
            assert app.run_checks._parent_canvas.winfo_height() > sizes[0]
            assert app.run_log.winfo_height() > sizes[1]
            app.geometry("1080x700")
            app.update()
            assert app.run_checks._parent_canvas.winfo_height() >= 150
            assert app.run_log.winfo_height() >= 140
            print("PASS: regression tasks and live log fill the available space and remain scrollable with 40 tasks")

            app.tasks = app.tasks[:2]
            app.refresh_run()
            result = SuiteReport(status="FAILED", stopped_at_step=1, stopped_url="http://localhost",
                failed_test_name="First", error_details="1/2 passed; 1 failed.", task_results=[
                    TaskResult(status="FAILED", stopped_at_step=1, stopped_url="http://localhost",
                        failed_test_name="First", error_details="Missing button", task_id="first", task_name="First"),
                    TaskResult(status="PASSED", stopped_at_step=2, stopped_url="http://localhost",
                        failed_test_name="", error_details="", task_id="second", task_name="Second")])
            record = RunRecord(status="failed", report=result.model_dump())
            app._show_result(record)
            assert len(app._verdict_rows) == 2
            verdict_text = [w.cget("text") for w in descendants(app.task_verdicts) if isinstance(w, ctk.CTkLabel)]
            assert "PASSED" in verdict_text and "FAILED" in verdict_text and "Missing button" in verdict_text
            print("PASS: each task has a separate verdict in the result panel")
        finally:
            app._on_close()
            app.runner.thread.join(timeout=10)
            app._await_shutdown()


async def browser():
    from playwright.async_api import async_playwright
    from browser_use import Browser
    server = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    runner = BrowserAgentRunner()
    errors = []
    try:
        for headless in (True, False):
            async with runner._browser(headless, []) as address:
                async with async_playwright() as pw:
                    remote = await pw.chromium.connect_over_cdp(address)
                    session = await remote.new_browser_cdp_session()
                    version = await session.send("Browser.getVersion")
                    assert ("HeadlessChrome" in version["userAgent"]) == headless
                    await remote.close()
        print("PASS: real Chromium launches visibly with live mode on and headless with it off")
        async with runner._browser(True, errors) as address:
            # Verify the engine can attach to the very same local browser.
            session = Browser(cdp_url=address)
            await session.start()
            await session.stop()
            async with async_playwright() as pw:
                remote = await pw.chromium.connect_over_cdp(address)
                context = remote.contexts[0]
                page = await context.new_page()
                url = f"http://127.0.0.1:{server.server_port}"
                await page.goto(url)
                await page.click("#save")
                assert await page.locator("#save").inner_text() == "Saved"
                assert not errors, errors
                await page.goto(url + "/broken")
                await page.wait_for_timeout(100)
                assert any("HTTP 500" in e["text"] for e in errors), errors
                await page.evaluate("console.error('Console smoke error')")
                await page.wait_for_timeout(100)
                assert any("Console smoke error" in e["text"] for e in errors), errors
                await remote.close()
            errors.clear()
            calls = []
            async def fake_llm(self, messages, output_format=None, **kwargs):
                from browser_use.llm.views import ChatInvokeCompletion
                calls.append(output_format)
                if len(calls) == 1:
                    action = {"evaluate": {"code": "document.querySelector('#save').click(); document.querySelector('#save').textContent"}}
                else:
                    data = TestReport(status="PASSED", stopped_at_step=2, stopped_url=url,
                                      failed_test_name="", error_details="").model_dump()
                    action = {"done": {"success": True, "data": data}}
                value = output_format.model_validate({"evaluation_previous_goal": "Success",
                    "memory": "Local smoke test", "next_goal": "Verify save", "action": [action]})
                return ChatInvokeCompletion(completion=value, usage=None)
            with patch("browser_use.ChatOpenAI.ainvoke", fake_llm):
                result = await runner._browser_use({"model": "gpt-6-luna"}, "dummy", f"Open {url}, click Save, verify Saved", address)
            assert result.status == "PASSED", result
            assert len(calls) == 2, len(calls)
            assert not errors, errors
        print("PASS: Chromium click, browser-use attach, HTTP 500 and console diagnostics")
        print("PASS: full browser-use agent with simulated LLM, real actions and structured report")

        async def task_engine(settings, key, prompt, address):
            async with async_playwright() as pw:
                remote = await pw.chromium.connect_over_cdp(address)
                try:
                    page = await remote.contexts[0].new_page()
                    if settings["task_name"] == "Broken page":
                        await page.goto(url + "/broken")
                        assert await page.locator("#save").count() == 0
                        return TestReport(status="FAILED", stopped_at_step=1, stopped_url=page.url,
                            failed_test_name="Broken page", error_details="Requested Save button missing (HTTP 500 page).")
                    else:
                        await page.goto(url)
                        await page.click("#save")
                        assert await page.locator("#save").inner_text() == "Saved"
                        if settings["task_name"] == "Working flow with console bug":
                            await page.evaluate("console.error('Unrelated fixture bug')")
                            await page.evaluate("fetch('/broken').then(response => response.status)")
                            await page.evaluate("setTimeout(() => { throw new Error('Unrelated page exception'); }, 0)")
                            await page.wait_for_timeout(100)
                        return TestReport(status="PASSED", stopped_at_step=1, stopped_url=url,
                                          failed_test_name="", error_details="")
                finally:
                    await remote.close()
        runner._browser_use = task_engine
        runner.submit(dict(base_url=url, openai_key="dummy"), [
            RegressionTask(name="Broken page", steps="Open the broken page and verify the Save button exists"),
            RegressionTask(name="Working flow with console bug", steps="Click Save and verify Saved"),
            RegressionTask(name="Working page", steps="Click Save and verify Saved"),
        ], True)
        await asyncio.wait_for(asyncio.wrap_future(runner._job), timeout=30)
        events = []
        while not runner.steps.empty():
            events.append(runner.steps.get_nowait())
        suite = next(event["report"] for event in events if event["kind"] == "done")
        assert [result.status for result in suite.task_results] == ["FAILED", "PASSED", "PASSED"]
        assert "HTTP 500" in suite.task_results[0].error_details
        log = "\n".join(event.get("text", "") for event in events if event["kind"] == "log")
        assert "Unrelated fixture bug" in log and "Unrelated page exception" in log and "HTTP 500" in log
        print("PASS: an unmet requested outcome fails; the queue continues with passing tasks")
        print("PASS: a working Save flow passes despite console/page errors and a failed background request; diagnostics stay in the log")
    finally:
        server.shutdown()
        server.server_close()
        runner.close()
        runner.thread.join(timeout=10)


if __name__ == "__main__":
    desktop()
    asyncio.run(browser())
