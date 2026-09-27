"""Own one interactive GovDash browser with a persistent, Coven-only profile.

No cookies, tokens, passwords, page contents, or general browser-control API are
exposed to the renderer or to Hermes. The user completes SSO/MFA in the browser.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import queue
import re
import shutil
import threading
from urllib.parse import urlsplit
import uuid


def persistent_browser_options(profile: Path, executable: str):
    return {"user_data_dir": str(profile), "executable_path": executable, "headless": False,
            "no_viewport": True, "accept_downloads": True, "chromium_sandbox": True, "timeout": 15000,
            "args": ["--no-first-run", "--disable-background-mode"]}


class GovDashBrowser:
    def __init__(self, root: Path):
        self.root = root
        self.download_dir = root.parent / "govdash-downloads"
        self._lock = threading.RLock()
        self._commands = queue.Queue(maxsize=4)
        self._thread = None
        self._stopping = False
        self._context = None
        self._driver = None
        self._state = {"state": "closed", "authState": "not_checked", "lastOpenedAt": None,
                       "message": "Open GovDash to sign in or resume your saved session."}

    def has_profile(self):
        return any((self.root / browser).is_dir() for browser in ("edge", "chrome"))

    def status(self):
        with self._lock:
            return {**self._state, "savedProfile": self.has_profile(), "downloadsFolder": str(self.download_dir)}

    def _set(self, **values):
        with self._lock:
            self._state.update(values)

    def open(self, browser_id, executable, url):
        if browser_id not in {"edge", "chrome"}:
            raise ValueError("Unsupported browser.")
        with self._lock:
            if self._stopping:
                raise ValueError("Coven is closing.")
            if self._state["state"] == "open":
                self._enqueue("focus", None)
                return self.status()
            if self._state["state"] not in {"closed", "error"}:
                raise ValueError("Wait for the current GovDash browser action to finish.")
            self._set(state="opening", authState="not_checked", message="Opening your dedicated GovDash browser…")
            self._enqueue("open", (browser_id, executable, url))
            return self.status()

    def close_window(self):
        with self._lock:
            if self._state["state"] in {"closed", "error"}:
                return self.status()
            if self._state["state"] not in {"open", "opening"}:
                raise ValueError("Wait for the current GovDash browser action to finish.")
            self._set(state="closing", message="Closing GovDash and keeping its browser profile…")
            self._enqueue("close", None)
            return self.status()

    def forget(self):
        with self._lock:
            if self._state["state"] not in {"closed", "error"}:
                raise ValueError("Close the Coven GovDash window before forgetting its sign-in.")
            self._set(state="forgetting", authState="not_checked", message="Removing this connection’s saved browser data…")
            self._enqueue("forget", None)
            return self.status()

    def shutdown(self):
        with self._lock:
            self._stopping = True
            thread = self._thread
            if thread is None:
                return
        # The queue is bounded and actions run on a single browser-owner thread.
        while True:
            try:
                self._commands.get_nowait()
            except queue.Empty:
                break
        self._commands.put_nowait(("shutdown", None))
        thread.join(timeout=20)

    def _enqueue(self, command, payload):
        if self._stopping:
            raise ValueError("Coven is closing.")
        try:
            self._commands.put_nowait((command, payload))
        except queue.Full as exc:
            raise ValueError("A browser action is already queued. Try again shortly.") from exc
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="coven-govdash-browser", daemon=True)
            self._thread.start()

    def _run(self):
        try:
            while True:
                try:
                    command, payload = self._commands.get(timeout=0.1)
                except queue.Empty:
                    # Pump Playwright events on its owning thread, including a
                    # user closing the browser. Never inspect session secrets.
                    try:
                        if self._context and self._context.pages:
                            self._context.pages[0].wait_for_timeout(100)
                    except Exception:
                        try:
                            self._close_context()
                        except Exception:
                            self._set(state="error", message="The GovDash browser stopped responding. Close its window and retry.")
                    continue
                if command == "shutdown":
                    break
                try:
                    if command == "open":
                        self._open(*payload)
                    elif command == "focus" and self._context and self._context.pages:
                        self._context.pages[0].bring_to_front()
                    elif command == "close":
                        self._close_context()
                    elif command == "forget":
                        self._forget_profiles()
                except ImportError:
                    self._set(state="error", message="The browser component is missing. Repair or reinstall the Coven desktop app.")
                except Exception:
                    # Browser exceptions can contain URLs with SSO query tokens.
                    # Keep diagnostics generic rather than returning raw traces.
                    self._set(state="error", message="The browser action could not finish. Close any remaining Coven GovDash windows, check the selected browser, and retry. Managed-device policy may require your IT administrator.")
        finally:
            try:
                self._close_context()
            except Exception:
                self._set(state="error", message="The GovDash browser could not close cleanly. Close its window before trying again.")
            finally:
                if self._driver:
                    try:
                        self._driver.stop()
                    except Exception:
                        pass
                    self._driver = None

    def _open(self, browser_id, executable, url):
        from playwright.sync_api import sync_playwright

        self._close_context(update=False)
        if self._driver is None:
            self._driver = sync_playwright().start()
        profile = self.root / browser_id
        if profile.is_symlink():
            raise ValueError("A linked browser profile cannot be used for GovDash.")
        profile.mkdir(parents=True, exist_ok=True)
        context = self._driver.chromium.launch_persistent_context(**persistent_browser_options(profile, executable))
        self._context = context
        context.on("close", lambda *_: self._closed(context))
        context.on("page", self._watch_downloads)
        # The initial GovDash address is validated by LinkedApps. Subsequent
        # interactive SSO navigation stays in the same isolated browser profile.
        page = context.pages[0] if context.pages else context.new_page()
        self._watch_downloads(page)
        page.on("framenavigated", lambda frame: self._navigation(frame, page, url))
        self._set(state="open", message="GovDash is open. Check your account in that window; its session is kept for the next launch.",
                  lastOpenedAt=datetime.now(timezone.utc).isoformat())
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            # Keep the window available for normal retry, SSO, or network errors.
            self._set(message="GovDash is open, but the initial page did not finish loading. Check the browser window or retry there.")

    def _watch_downloads(self, page):
        page.on("download", self._save_download)

    def _save_download(self, download):
        try:
            # Unique names avoid overwriting earlier review documents. These
            # files are outside the session profile and survive Forget sign-in.
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", download.suggested_filename).strip(" .")[:160] or "download"
            self.download_dir.mkdir(parents=True, exist_ok=True)
            destination = self.download_dir / f"{uuid.uuid4().hex[:8]}-{name}"
            download.save_as(str(destination))
            if os.name == "nt":
                # Preserve Windows' normal treatment of Internet downloads,
                # including Office Protected View, without storing signed URLs.
                try:
                    Path(str(destination) + ":Zone.Identifier").write_text("[ZoneTransfer]\nZoneId=3\n", encoding="utf-8")
                except OSError:
                    destination.unlink(missing_ok=True)
                    raise
            self._set(message=f"Downloaded {name}. Use Open downloads folder in Settings to find it.")
        except Exception:
            self._set(message="The download could not be saved. Retry in GovDash and check free disk space.")

    def _navigation(self, frame, page, target):
        if frame != page.main_frame:
            return
        try:
            parsed = urlsplit(frame.url)
            login = parsed.hostname != urlsplit(target).hostname or parsed.path.rstrip("/").endswith("/login")
            # Leaving a login URL is not proof of successful authentication.
            self._set(authState="sign_in_required" if login else "not_checked")
        except ValueError:
            self._set(authState="not_checked")

    def _closed(self, context):
        if self._context is context:
            self._context = None
            self._set(state="closed", authState="not_checked", message="GovDash window closed. Its browser profile is kept for the next launch.")

    def _close_context(self, *, update=True):
        context = self._context
        if context is not None:
            context.close()
            self._context = None
        if update:
            self._set(state="closed", authState="not_checked", message="GovDash window closed. Its browser profile is kept for the next launch.")

    def _forget_profiles(self):
        self._close_context(update=False)
        # Delete only these fixed app-owned profiles, never a caller-supplied path.
        # A failure (including locked files) stays visible and never reports logout.
        for browser in ("edge", "chrome"):
            profile = self.root / browser
            if profile.is_symlink():
                profile.unlink()
            elif profile.exists():
                shutil.rmtree(profile)
        self._set(state="closed", authState="not_checked", lastOpenedAt=None,
                  message="Saved GovDash sign-in was forgotten on this computer. Open GovDash to sign in again.")
