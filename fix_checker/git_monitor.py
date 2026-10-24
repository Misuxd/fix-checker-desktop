"""Watches a local Git repo for new commits."""
from __future__ import annotations

import threading
from typing import Callable, Optional, Tuple

try:
    import git  # GitPython
except ImportError:  # pragma: no cover - optional dependency
    git = None


class GitMonitor:
    """Polls HEAD for a new commit hash and reports the commit subject."""

    def __init__(
        self, on_commit: Callable[[str, str], None], interval: float = 3.0
    ) -> None:
        self.on_commit = on_commit
        self.interval = interval
        self.repo_path: Optional[str] = None
        self._last: Optional[str] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def available(self) -> bool:
        return git is not None

    def start(self, repo_path: Optional[str] = None) -> None:
        """Begin polling. Safe to call again after the path changes."""
        self.stop()
        self.repo_path = repo_path
        if not self.repo_path or git is None:
            return
        self._stop = threading.Event()
        self._last = self._head()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def current(self) -> Optional[Tuple[str, str]]:
        """Return (sha, subject) for HEAD, or None when the repo is unreadable."""
        sha = self._head()
        if not sha:
            return None
        return sha, self._subject(sha)

    def _repo(self):
        if not self.repo_path:
            raise ValueError("No repository selected")
        return git.Repo(self.repo_path, search_parent_directories=False)

    def _head(self) -> Optional[str]:
        try:
            return self._repo().head.commit.hexsha
        except Exception:
            return None

    def _subject(self, sha: str) -> str:
        try:
            message = self._repo().commit(sha).message.strip()
            return message.splitlines()[0] if message else sha[:7]
        except Exception:
            return sha[:7]

    def _loop(self) -> None:
        stop = self._stop
        while not stop.wait(self.interval):
            sha = self._head()
            if sha and sha != self._last:
                self.on_commit(sha, self._subject(sha))
            if sha:
                self._last = sha
