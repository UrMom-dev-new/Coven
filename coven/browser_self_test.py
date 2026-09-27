"""Optional Windows packaging check using a local session fixture, never GovDash."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

from .govdash_browser import GovDashBrowser
from .linked_apps import find_windows_program


def check_persistent_browser():
    executable = find_windows_program("msedge.exe")
    if not executable:
        raise RuntimeError("Microsoft Edge is required for this optional browser packaging check.")
    reports = []
    visits = []
    lock = threading.Lock()
    nonce = uuid.uuid4().hex
    class FixtureHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == f"/{nonce}/report":
                with lock:
                    reports.append({"cookie": "coven_fixture=saved" in (self.headers.get("Cookie") or ""),
                                    "storage": parse_qs(parsed.query).get("storage", [""])[0]})
                self.send_response(204)
                self.end_headers()
                return
            if parsed.path != f"/{nonce}":
                self.send_response(404)
                self.end_headers()
                return
            with lock:
                visits.append("coven_fixture=saved" in (self.headers.get("Cookie") or ""))
            html = ("<!doctype html><title>Coven session persistence test</title><p>Local test fixture. No service credentials are used.</p>"
                    f"<script>fetch('/{nonce}/report?storage='+encodeURIComponent(localStorage.getItem('coven_fixture')||''));"
                    "localStorage.setItem('coven_fixture','saved');</script>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Set-Cookie", "coven_fixture=saved; Max-Age=3600; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

    def wait_until(predicate, browser, *, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if browser.status()["state"] == "error":
                raise RuntimeError(browser.status()["message"])
            threading.Event().wait(0.1)
        raise RuntimeError("Browser profile check timed out.")

    fixture = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    browser = None
    temporary = tempfile.TemporaryDirectory(prefix="coven-browser-check-")
    try:
        root = Path(temporary.name)
        url = f"http://127.0.0.1:{fixture.server_port}/{nonce}"
        browser = GovDashBrowser(root / "profiles")
        browser.open("edge", executable, url)
        wait_until(lambda: len(reports) >= 1, browser)
        browser.close_window()
        wait_until(lambda: browser.status()["state"] == "closed", browser)
        browser.shutdown()
        # A new service instance models an entire Coven restart.
        browser = GovDashBrowser(root / "profiles")
        browser.open("edge", executable, url)
        wait_until(lambda: len(reports) >= 2, browser)
        assert visits[1] and reports[1]["storage"] == "saved", json.dumps(reports)
        browser.close_window()
        wait_until(lambda: browser.status()["state"] == "closed", browser)
        browser.forget()
        wait_until(lambda: browser.status()["state"] == "closed" and not browser.has_profile(), browser)
        browser.open("edge", executable, url)
        wait_until(lambda: len(reports) >= 3, browser)
        assert not visits[2] and reports[2]["storage"] == "", json.dumps(reports)
        browser.close_window()
        wait_until(lambda: browser.status()["state"] == "closed", browser)
        browser.shutdown()
        browser = None
    finally:
        if browser is not None:
            browser.shutdown()
        temporary.cleanup()
        fixture.shutdown()
        fixture.server_close()
        thread.join(timeout=2)
