"""Bounded background reconciliation for live Hermes runs."""

from __future__ import annotations

import threading
import time
from typing import Any


class TaskReconciler:
    def __init__(self, adapter: Any, *, interval_seconds: float = 4.0):
        self.adapter = adapter
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None
        self.last_run_at: float | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="coven-reconciler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def snapshot(self) -> dict[str, object]:
        return {
            "running": self._thread is not None and self._thread.is_alive() and not self._stop.is_set(),
            "intervalSeconds": self.interval_seconds,
            "lastRunAt": self.last_run_at,
            "lastError": self.last_error,
        }

    def tick(self) -> None:
        if not hasattr(self.adapter, "refresh_tasks"):
            return
        try:
            self.adapter.refresh_tasks()
            self.last_error = None
        except Exception as exc:  # pragma: no cover - defensive service boundary
            self.last_error = str(exc)
        finally:
            self.last_run_at = time.time()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.interval_seconds)
