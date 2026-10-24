"""Data models and small helpers."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TestReport(BaseModel):
    """Structured result the browser agent must return."""

    model_config = ConfigDict(extra="forbid")
    status: Literal["PASSED", "FAILED"]
    stopped_at_step: int = Field(
        ge=0, description="Step number where the agent stopped."
    )
    stopped_url: str = Field(description="URL the agent was on when it stopped.")
    failed_test_name: str = Field(
        description="Name of the test that failed, empty when everything passed."
    )
    error_details: str = Field(
        description="Short explanation of what went wrong."
    )

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value):
        return value.upper() if isinstance(value, str) else value


@dataclass
class RegressionTask:
    """A saved flow the agent replays on every run."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    path: str = "/"
    steps: str = ""
    enabled: bool = True


@dataclass
class RunRecord:
    """One commit test run, kept in the home list and the sidebar history."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str = ""
    description: str = ""
    commit: str = ""
    path: str = "/"
    status: str = "queued"  # queued | running | passed | failed
    started: float = field(default_factory=time.time)
    finished: float = 0.0
    report: dict = field(default_factory=dict)
    tag: str = "manual"


def load_json(path: Path, default: Any) -> Any:
    """Read a JSON file next to the app, falling back to *default*."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def time_ago(ts: float) -> str:
    if not ts:
        return "never"
    secs = max(0, int(time.time() - ts))
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


DEFAULT_TASKS = [
    RegressionTask(
        name="Sign in",
        path="/login",
        steps="Open /login, enter the test account, submit, expect the dashboard to load.",
    ),
    RegressionTask(
        name="Add to cart",
        path="/products",
        steps="Open /products, add the first item to the cart, expect the cart badge to show 1.",
    ),
    RegressionTask(
        name="Checkout",
        path="/checkout",
        steps="Open /checkout with one item in the cart, expect the order summary to appear.",
    ),
]
