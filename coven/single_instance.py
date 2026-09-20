"""Best-effort single-instance guard.

Windows uses a named mutex scoped to the current user session. Other platforms use
an exclusive lock file so development runs do not accidentally spawn duplicate
desktop shells.
"""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import os
from pathlib import Path
import sys


ERROR_ALREADY_EXISTS = 183


@dataclass
class SingleInstance:
    name: str
    lock_path: Path
    acquired: bool = False
    _handle: int | None = None
    _fd: int | None = None

    def acquire(self) -> bool:
        if os.name == "nt":
            return self._acquire_windows_mutex()
        return self._acquire_lock_file()

    def release(self) -> None:
        if os.name == "nt" and self._handle:
            ctypes.windll.kernel32.ReleaseMutex(self._handle)
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None
        self.acquired = False

    def _acquire_windows_mutex(self) -> bool:
        mutex_name = f"Local\\{self.name}"
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, mutex_name)
        if not handle:
            return False
        already_exists = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
        self._handle = handle
        self.acquired = not already_exists
        return self.acquired

    def _acquire_lock_file(self) -> bool:
        import fcntl

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        self._fd = fd
        self.acquired = True
        return True

    def __enter__(self) -> "SingleInstance":
        if not self.acquire():
            raise RuntimeError("Coven is already running for this user.")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def current_user_instance(name: str, lock_path: Path) -> SingleInstance:
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    safe = "".join(char if char.isalnum() else "_" for char in user)
    return SingleInstance(f"{name}_{safe}", lock_path)
