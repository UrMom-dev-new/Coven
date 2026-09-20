"""Native desktop shell for Coven using pywebview/WebView2 when available."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import sys
import threading
import time
import webbrowser

from .paths import APP_NAME, local_app_data, runtime_dir, webview_user_data_dir
from .server import build_server
from .single_instance import current_user_instance


class DesktopBridge:
    def __init__(self, token: str):
        self._token = token
        self._used = False

    def start_session(self) -> str:
        if self._used:
            return ""
        self._used = True
        return self._token


def allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_ready(port: int, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def start_owned_server(port: int, data_dir: Path, config: Path | None, token: str):
    server = build_server("127.0.0.1", port, data_dir, config_path=config, auth_token=token)
    thread = threading.Thread(target=server.serve_forever, name="coven-http", daemon=True)
    thread.start()
    return server, thread


def detect_webview2() -> tuple[bool, str]:
    if os.name != "nt":
        return False, "WebView2 availability can only be checked on Windows."
    try:
        import winreg

        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        ]
        for hive, path in keys:
            try:
                with winreg.OpenKey(hive, path):
                    return True, "WebView2 Evergreen Runtime was found in the registry."
            except FileNotFoundError:
                continue
    except Exception as exc:  # pragma: no cover - Windows-only branch
        return False, f"WebView2 registry check failed: {exc}"
    return False, "WebView2 Evergreen Runtime was not found."


def run_desktop(args: argparse.Namespace) -> int:
    app_data = local_app_data()
    data_dir = args.data_dir or app_data / "state"
    data_dir.mkdir(parents=True, exist_ok=True)
    lock = current_user_instance(APP_NAME, runtime_dir() / "instance.lock")
    if not lock.acquire():
        print("Coven is already running for this Windows user.")
        return 2

    token = args.auth_token or os.environ.get("COVEN_DEV_AUTH_TOKEN") or os.urandom(24).hex()
    port = args.port or allocate_port()
    server = None
    try:
        server, _thread = start_owned_server(port, data_dir, args.config, token)
        if not wait_for_ready(port):
            raise RuntimeError("The local Coven service did not become ready.")

        url = f"http://127.0.0.1:{port}/"
        if args.browser:
            print(f"Coven development browser URL: {url}")
            print("Development browser unlock token:")
            print(token)
            webbrowser.open(url)
            while True:
                time.sleep(3600)

        try:
            import webview
        except ImportError as exc:
            raise RuntimeError("pywebview is not installed. Install the pinned desktop dependencies or use --browser.") from exc

        ok, message = detect_webview2()
        if os.name == "nt" and not ok:
            print(message)
            print("Install Microsoft Edge WebView2 Evergreen Runtime, then launch Coven again.")
            return 3

        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        webview.settings["REMOTE_DEBUGGING_PORT"] = args.remote_debugging_port or None
        os.environ.setdefault("PYWEBVIEW_GUI", "edgechromium" if os.name == "nt" else "")
        os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", str(webview_user_data_dir()))

        bridge = DesktopBridge(token)
        window = webview.create_window(
            "Coven",
            url,
            js_api=bridge,
            width=1280,
            height=820,
            min_size=(980, 680),
            confirm_close=True,
            background_color="#080b10",
        )
        webview.start(gui="edgechromium" if os.name == "nt" else None, debug=args.debug)
        return 0
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        lock.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch Coven desktop.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--auth-token", default=None)
    parser.add_argument("--browser", action="store_true", help="Use the authenticated development browser instead of pywebview.")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--remote-debugging-port", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        return run_desktop(args)
    except Exception as exc:
        print(f"Coven startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
