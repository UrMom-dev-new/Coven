"""Runtime diagnostics for frozen Coven startup."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time
import traceback


def _write_startup_log(message: str) -> None:
    log_path = os.environ.get("COVEN_SELF_TEST_LOG")
    if not log_path:
        return
    try:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")
    except OSError:
        return


def _log_uncaught_exception(exc_type, exc, tb) -> None:
    _write_startup_log("uncaught exception during frozen startup")
    for line in traceback.format_exception(exc_type, exc, tb):
        _write_startup_log(line.rstrip())
    sys.__excepthook__(exc_type, exc, tb)


_write_startup_log("pyinstaller runtime hook loaded")
sys.excepthook = _log_uncaught_exception
