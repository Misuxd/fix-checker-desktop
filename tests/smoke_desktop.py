"""Real Tk and real Chromium smoke checks; no paid LLM calls."""
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from fix_checker.agent_runner import BrowserAgentRunner
from fix_checker.app import DeveloperAppUI
from fix_checker.models import RegressionTask
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
            assert app.run_headless.cget("state") == "disabled"
            print("PASS: provider labels, separate key drafts, save/reload and model availability")
            app.add_task()
            app.update()
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
