"""Skyvern runs in its own dependency environment; events stream to the GUI."""
from __future__ import annotations

import asyncio
import json
import sys

from .models import TestReport


def emit(event):
    print("FIX_CHECKER_EVENT " + json.dumps(event, default=str), flush=True)


async def run(payload, send=emit):
    from skyvern import Skyvern, RunStatus
    from skyvern.schemas.llm import LLMConfig
    config = LLMConfig(
        model_name="openai/" + payload["model"], required_env_vars=[],
        supports_vision=True, add_assistant_prefix=False,
        litellm_params={"api_key": payload["key"]}, temperature=None,
        max_tokens=None, max_completion_tokens=8192, reasoning_effort="none",
    )
    client = Skyvern.local(llm_config=config, use_in_memory_db=True)
    run_id = None
    completed = False
    try:
        task = await client.run_task(
            prompt=payload["prompt"], url=payload["url"], browser_address=payload["address"],
            max_steps=100, data_extraction_schema=TestReport.model_json_schema(),
            wait_for_completion=False,
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
        await client.aclose()


def main():
    payload = json.loads(sys.stdin.readline())
    try:
        report = asyncio.run(run(payload))
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}".replace(payload["key"], "[redacted]")
        report = TestReport(status="FAILED", stopped_at_step=0, stopped_url=payload["url"],
                            failed_test_name="Skyvern execution", error_details=text)
    emit({"kind": "done", "report": report.model_dump()})


if __name__ == "__main__":
    main()
