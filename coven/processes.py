"""Launch options for non-interactive background tools."""

from __future__ import annotations

import subprocess
import sys


def background_process_options() -> dict[str, int]:
    """Prevent console tools from opening windows beside the desktop app.

    Redirecting stdout/stderr alone does not prevent Windows from allocating a
    console for a child of a windowed executable. Keep this policy local to
    background tools; file pickers and other intentional UI are unaffected.
    """
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
