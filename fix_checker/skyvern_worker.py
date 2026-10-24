"""Skyvern runs in its own dependency environment; events stream to the GUI."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading

from .models import TestReport


def emit(event):
    print("FIX_CHECKER_EVENT " + json.dumps(event, default=str), flush=True)


async def run(payload, send=emit):
    from skyvern import Skyvern, RunStatus
    client = Skyvern(api_key=payload["key"])
    run_id = None
    session_id = None
    completed = False
    try:
        browser_options = {}
        if payload.get("show_browser"):
            session = await client.create_browser_session(timeout=15)
            session_id = session.browser_session_id
            browser_options["browser_session_id"] = session_id
            viewer_url = session.app_url or f"https://app.skyvern.com/browser-session/{session_id}"
            send({"kind": "browser_view", "url": viewer_url})
        task = await client.run_task(
            prompt=payload["prompt"], url=payload["url"],
            max_steps=100, data_extraction_schema=TestReport.model_json_schema(),
            wait_for_completion=False,
            **browser_options,
        )
        run_id = task.run_id
        seen = set()
        while True:
            task = await client.get_run(run_id)
            text = f"Skyvern: {task.status}; steps: {getattr(task, 'step_count', None)}"
            if text not in seen:
                seen.add(text)
                send({"kind": "log", "text": text, "step": getattr(task, "step_count", 0)})
            if RunStatus(task.status).is_final():
                completed = True
                break
            await asyncio.sleep(2)
        status = str(getattr(task.status, "value", task.status)).lower()
        if status != "completed":
            return TestReport(
                status="FAILED", stopped_at_step=getattr(task, "step_count", 0) or 0,
                stopped_url=payload["url"], failed_test_name="Skyvern execution",
                error_details=getattr(task, "failure_reason", None) or f"Skyvern {status}",
            )
        value = task.output
        report = TestReport.model_validate_json(value) if isinstance(value, str) else TestReport.model_validate(value)
        return report
    finally:
        if run_id and not completed:
            try:
                await client.cancel_run(run_id)
            except Exception:
                pass
        try:
            if session_id:
                await client.close_browser_session(session_id)
        finally:
            await client.aclose()


async def run_with_cancel(payload):
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(run(payload))

    def listen():
        # Any follow-up input or parent disconnect requests cancellation. Read the
        # raw pipe so a waiting daemon thread holds no buffered stdin lock on exit.
        os.read(sys.stdin.fileno(), 1)
        if not loop.is_closed():
            loop.call_soon_threadsafe(task.cancel)

    threading.Thread(target=listen, daemon=True).start()
    return await task


def main():
    payload = json.loads(sys.stdin.buffer.raw.readline())
    try:
        report = asyncio.run(run_with_cancel(payload))
    except asyncio.CancelledError:
        report = TestReport(status="FAILED", stopped_at_step=0, stopped_url=payload["url"],
                            failed_test_name="Skyvern execution", error_details="Run cancelled.")
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}".replace(payload["key"], "[redacted]")
        report = TestReport(status="FAILED", stopped_at_step=0, stopped_url=payload["url"],
                            failed_test_name="Skyvern execution", error_details=text)
    emit({"kind": "done", "report": report.model_dump()})


if __name__ == "__main__":
    main()
