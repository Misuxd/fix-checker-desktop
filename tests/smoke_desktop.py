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
from fix_checker.models import TestReport


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
            assert app.set_model.cget("state") == "disabled"
            app.set_key.insert(0, "skyvern-draft")
            app.set_engine.set("browser-use")
            app._change_engine("browser-use")
            assert app.set_key_label.cget("text") == "OpenAI API key"
            assert app.set_key.get() == ""
            assert app.set_model.cget("state") == "normal"
            app.set_key.insert(0, "openai-draft")
            app.set_engine.set("skyvern")
            app._change_engine("skyvern")
            assert app.set_key.get() == "skyvern-draft"
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
            assert "Target path" not in [w.cget("text") for w in descendants(app.pages["Run Agent"])
                                          if isinstance(w, ctk.CTkLabel)]
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

            app.run_fix.insert("1.0", "Click Save")
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
                    assert submit.call_args.args[1] is None
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
    finally:
        server.shutdown()
        server.server_close()
        runner.close()
        runner.thread.join(timeout=10)


if __name__ == "__main__":
    desktop()
    asyncio.run(browser())
