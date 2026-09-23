"""Native desktop shell for Coven using pywebview/WebView2 when available."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from urllib import error as urllib_error, request as urllib_request

from coven.paths import APP_NAME, local_app_data, runtime_dir, webview_user_data_dir
from coven.server import build_server
from coven.single_instance import current_user_instance


class DesktopBridge:
    def __init__(self, token: str):
        self._token = token
        self._used = False

    def start_session(self) -> str:
        if self._used:
            return ""
        self._used = True
        return self._token

    def choose_folder(self) -> str:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(title="Choose a Coven work folder")
            root.destroy()
            return selected or ""
        except Exception:
            return ""


class DesktopSelfTestError(RuntimeError):
    """Raised when the packaged desktop smoke path fails."""


def _append_self_test_log(log_path: Path | None, message: str) -> None:
    if log_path is None:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")
    except OSError:
        return


def _self_test_print(message: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    try:
        print(message, file=stream)
    except Exception:
        return


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


def _http_request(
    method: str,
    url: str,
    *,
    payload: dict[str, object] | None = None,
    cookie: str | None = None,
    timeout: float = 5.0,
) -> tuple[int, dict[str, str], bytes]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
        headers["X-Coven-Intent"] = "ui-action"
    if cookie:
        headers["Cookie"] = cookie
    req = urllib_request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib_request.urlopen(req, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib_error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def _header(headers: dict[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def _json_body(body: bytes, context: str) -> dict[str, object]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DesktopSelfTestError(f"{context} returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise DesktopSelfTestError(f"{context} returned an unexpected JSON payload.")
    return payload


def run_self_test(args: argparse.Namespace) -> int:
    log_path = args.self_test_log
    _append_self_test_log(log_path, "starting desktop self-test")
    previous_demo_mode = os.environ.get("COVEN_DEMO_MODE")
    os.environ["COVEN_DEMO_MODE"] = "1"
    token = args.auth_token or os.urandom(24).hex()
    port = args.port or allocate_port()
    _append_self_test_log(log_path, f"using port {port}")
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    data_dir = args.data_dir
    if data_dir is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="coven-desktop-self-test-")
        data_dir = Path(temp_dir.name)
    data_dir.mkdir(parents=True, exist_ok=True)
    _append_self_test_log(log_path, f"using data dir {data_dir}")

    server = None
    try:
        _append_self_test_log(log_path, "starting loopback service")
        server, _thread = start_owned_server(port, data_dir, args.config, token)
        _append_self_test_log(log_path, "waiting for loopback service readiness")
        if not wait_for_ready(port, timeout=args.self_test_timeout):
            raise DesktopSelfTestError("The local Coven service did not become ready.")

        base_url = f"http://127.0.0.1:{port}"
        _append_self_test_log(log_path, "checking health endpoint")
        status, _headers, body = _http_request("GET", f"{base_url}/api/health")
        if status != 200 or _json_body(body, "Health check").get("ok") is not True:
            raise DesktopSelfTestError("Health check failed.")

        _append_self_test_log(log_path, "bootstrapping authenticated session")
        status, headers, body = _http_request("POST", f"{base_url}/api/auth/session", payload={"token": token})
        if status != 201 or _json_body(body, "Auth session").get("authenticated") is not True:
            raise DesktopSelfTestError("Desktop auth session bootstrap failed.")
        cookie = _header(headers, "Set-Cookie").split(";", 1)[0]
        if not cookie:
            raise DesktopSelfTestError("Auth session did not return a session cookie.")

        _append_self_test_log(log_path, "checking authenticated app shell")
        status, _headers, body = _http_request("GET", f"{base_url}/", cookie=cookie)
        shell = body.decode("utf-8", errors="replace")
        required_markers = ["sanctuary-art", "portrait-crop", "journal-tabs", "workspaceMode"]
        if status != 200 or any(marker not in shell for marker in required_markers):
            raise DesktopSelfTestError("Authenticated app shell did not include required UI markers.")

        _append_self_test_log(log_path, "checking seeded demo tasks")
        status, _headers, body = _http_request("GET", f"{base_url}/api/tasks", cookie=cookie)
        tasks_payload = _json_body(body, "Task list")
        tasks = tasks_payload.get("tasks")
        if status != 200 or not isinstance(tasks, list) or not any(
            isinstance(task, dict) and task.get("title") == "Prepare project brief" for task in tasks
        ):
            raise DesktopSelfTestError("Seeded demo quest journal was not available.")

        _append_self_test_log(log_path, "checking local voice status boundary")
        status, _headers, body = _http_request("GET", f"{base_url}/api/voice/status", cookie=cookie)
        voice_payload = _json_body(body, "Voice status")
        voice = voice_payload.get("voice")
        if status != 200 or not isinstance(voice, dict) or voice.get("engine") != "whisper.cpp":
            raise DesktopSelfTestError("Local voice status boundary was not available.")

        _append_self_test_log(log_path, "checking first-run setup status boundary")
        status, _headers, body = _http_request("GET", f"{base_url}/api/setup/status", cookie=cookie)
        setup_payload = _json_body(body, "Setup status")
        setup = setup_payload.get("setup")
        if status != 200 or not isinstance(setup, dict) or not setup.get("version"):
            raise DesktopSelfTestError("First-run setup status boundary was not available.")

        _append_self_test_log(log_path, "checking approved reference image asset")
        status, headers, _body = _http_request("HEAD", f"{base_url}/assets/reference/coven-approved-reference.png")
        content_type = _header(headers, "Content-Type")
        content_length = int(_header(headers, "Content-Length") or "0")
        if status != 200 or content_type != "image/png" or content_length < 1_000_000:
            raise DesktopSelfTestError("Approved reference image asset was not served from the bundle.")

        _append_self_test_log(log_path, "checking stylesheet cache policy")
        status, headers, _body = _http_request("HEAD", f"{base_url}/styles.css")
        if status != 200 or _header(headers, "Cache-Control") != "no-store":
            raise DesktopSelfTestError("Dynamic static asset cache policy is not active.")

        _append_self_test_log(log_path, "desktop self-test passed")
        _self_test_print("Coven desktop self-test passed.")
        return 0
    except Exception as exc:
        _append_self_test_log(log_path, f"desktop self-test failed: {exc}")
        _self_test_print(f"Coven desktop self-test failed: {exc}", error=True)
        return 1
    finally:
        if server is not None:
            _append_self_test_log(log_path, "shutting down loopback service")
            server.shutdown()
            server.server_close()
            _append_self_test_log(log_path, "loopback service closed")
        if temp_dir is not None:
            temp_dir.cleanup()
            _append_self_test_log(log_path, "temporary data dir removed")
        if previous_demo_mode is None:
            os.environ.pop("COVEN_DEMO_MODE", None)
        else:
            os.environ["COVEN_DEMO_MODE"] = previous_demo_mode
        _append_self_test_log(log_path, "desktop self-test cleanup complete")


def detect_webview2() -> tuple[bool, str]:
    if os.name != "nt":
        return False, "WebView2 availability can only be checked on Windows."
    try:
        import winreg

        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}", 0),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}", winreg.KEY_WOW64_64KEY),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}", 0),
        ]
        for hive, path, view in keys:
            try:
                with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view) as key:
                    value, _kind = winreg.QueryValueEx(key, "pv")
                    version = str(value or "").strip()
                    if version and version != "0.0.0.0":
                        return True, f"WebView2 Evergreen Runtime {version} was found."
            except FileNotFoundError:
                continue
            except OSError:
                continue
    except Exception as exc:  # pragma: no cover - Windows-only branch
        return False, f"WebView2 registry check failed: {exc}"
    return False, "WebView2 Evergreen Runtime was not found."


def native_notice(title: str, message: str) -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, title, 0x00000010)
            return
        except Exception:
            pass
    _self_test_print(f"{title}: {message}", error=True)


def run_desktop(args: argparse.Namespace) -> int:
    if args.demo:
        os.environ["COVEN_DEMO_MODE"] = "1"
    app_data = local_app_data()
    data_dir = args.data_dir or app_data / "state"
    data_dir.mkdir(parents=True, exist_ok=True)
    lock = current_user_instance(APP_NAME, runtime_dir() / "instance.lock")
    if not lock.acquire():
        native_notice("Coven is already running", "Coven is already open for this Windows user. Use the existing window, or close it before launching again.")
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
            native_notice(
                "Coven needs WebView2",
                f"{message}\n\nInstall the Microsoft Edge WebView2 Evergreen Runtime, then launch Coven again. The Coven installer can be repaired after WebView2 is installed.",
            )
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
    parser.add_argument("--demo", action="store_true", help="Run with the isolated demo namespace.")
    parser.add_argument("--self-test", action="store_true", help="Boot the local desktop service, validate bundled assets, then exit.")
    parser.add_argument("--self-test-timeout", type=float, default=8.0)
    parser.add_argument("--self-test-log", type=Path, default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--remote-debugging-port", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            code = run_self_test(args)
            if getattr(sys, "frozen", False):
                os._exit(code)
            return code
        return run_desktop(args)
    except Exception as exc:
        native_notice("Coven startup failed", f"{exc}\n\nTry launching Coven again, or reinstall/repair the app from the Windows installer.")
        print(f"Coven startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
