"""User-scoped links to installed Office apps and a separate GovDash browser."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from urllib.parse import urlsplit

from .govdash_browser import GovDashBrowser


OFFICE_APPS = {"word": ("Word", "WINWORD.EXE"), "excel": ("Excel", "EXCEL.EXE"),
               "powerpoint": ("PowerPoint", "POWERPNT.EXE")}
BROWSERS = {"edge": ("Microsoft Edge", "msedge.exe"), "chrome": ("Google Chrome", "chrome.exe")}
GOVDASH_URL = "https://dashboard.govdash.us/"


def govdash_url(value):
    if not isinstance(value, str):
        raise ValueError("Enter your GovDash HTTPS address.")
    parsed = urlsplit(value.strip())
    # GovDash's published dashboard hosts. Credentials, callback tokens, and
    # arbitrary destinations never become persisted browser launch arguments.
    if (parsed.scheme != "https" or parsed.hostname not in {"dashboard.govdash.us", "dashboard-transition.govdash.us"}
            or parsed.username or parsed.password or parsed.port not in {None, 443}
            or parsed.query or parsed.fragment or parsed.path.rstrip("/") not in {"", "/login"}):
        raise ValueError("Use https://dashboard.govdash.us/ (or the official transition dashboard), without sign-in callback parameters.")
    return f"https://{parsed.hostname}/"


def local_program(value, expected_name):
    if not isinstance(value, str):
        raise ValueError("Choose a local program file.")
    raw = os.path.expandvars(value.strip().strip('"'))
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if path.is_dir():
        path /= expected_name
    if (not path.is_absolute() or str(path).startswith(("\\\\", "//")) or not path.is_file()
            or path.name.casefold() != expected_name.casefold()):
        raise ValueError(f"Choose the installed {expected_name} file on this computer.")
    return str(path.resolve())


def find_windows_program(name):
    """Read registered app paths without starting Office or opening a console."""
    if sys.platform != "win32":
        return ""
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}", 0, winreg.KEY_READ | view) as key:
                    found = local_program(winreg.QueryValueEx(key, None)[0], name)
                    if found:
                        return found
            except (OSError, ValueError):
                continue
    # Click-to-Run and per-user browser installs are not always registered.
    bases = [os.environ.get(key, "") for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    for base in filter(None, bases):
        for relative in (f"Microsoft Office/root/Office16/{name}", f"Microsoft Office/Office16/{name}",
                         f"Microsoft/Edge/Application/{name}", f"Google/Chrome/Application/{name}"):
            path = Path(base) / relative
            if path.is_file():
                return str(path.resolve())
    return ""


class LinkedApps:
    def __init__(self, data_dir: Path, *, browser=None):
        self.root = data_dir / "connections"
        self.path = self.root / "linked-apps.json"
        self.lock = threading.RLock()
        self.browser = browser or GovDashBrowser(self.root / "govdash-profiles")
        self.load_error = ""
        self.detected = {}
        try:
            self.saved = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self.saved, dict):
                raise ValueError("Invalid links")
            office, govdash = self.saved.get("office", {}), self.saved.get("govdash", {})
            if not isinstance(office, dict) or not isinstance(govdash, dict):
                raise ValueError("Invalid links")
            paths = office.get("paths", {})
            if not isinstance(paths, dict) or any(key not in OFFICE_APPS or not isinstance(value, str) for key, value in paths.items()):
                raise ValueError("Invalid Office paths")
            if not isinstance(office.get("enabled", False), bool) or not isinstance(govdash.get("enabled", False), bool):
                raise ValueError("Invalid link state")
            if (not isinstance(govdash.get("browser", "edge"), str) or govdash.get("browser", "edge") not in BROWSERS
                    or not isinstance(govdash.get("executable", ""), str)):
                raise ValueError("Invalid browser")
            if govdash.get("url"):
                govdash_url(govdash["url"])
        except FileNotFoundError:
            self.saved = {}
        except (ValueError, OSError):
            self.saved = {}
            self.load_error = "Saved app links could not be read. Choose your apps and save the links again."
        self.detect()

    def detect(self):
        found = {key: find_windows_program(name) for key, (_, name) in {**OFFICE_APPS, **BROWSERS}.items()}
        with self.lock:
            self.detected = found
        return found

    def status(self):
        with self.lock:
            office = self.saved.get("office", {})
            govdash = self.saved.get("govdash", {})
            apps = []
            for key, (label, filename) in OFFICE_APPS.items():
                path = office.get("paths", {}).get(key, "") or self.detected.get(key, "")
                available = bool(path and Path(path).is_file()) and sys.platform == "win32"
                apps.append({"id": key, "label": label, "filename": filename, "path": path,
                             "available": available, "linked": available and office.get("enabled", False)})
            browser_id = govdash.get("browser", "edge")
            browser_path = govdash.get("executable", "") or self.detected.get(browser_id, "")
            return {"office": {"enabled": office.get("enabled", False), "apps": apps,
                               "authentication": "office_managed", "authenticated": None,
                               "note": "Office keeps its own Microsoft sign-in. Open an app to sign in or check its account. Coven does not read Office passwords or tokens."},
                    "govdash": {"enabled": govdash.get("enabled", False), "url": govdash.get("url", GOVDASH_URL),
                                "browser": browser_id, "executable": browser_path,
                                "browserAvailable": bool(browser_path and Path(browser_path).is_file()) and sys.platform == "win32",
                                "session": self.browser.status(), "authenticated": None,
                                "note": "Sign in directly in the GovDash window. Its browser profile is kept for the next launch; GovDash and your identity provider control session expiry."},
                    "detected": dict(self.detected), "windows": sys.platform == "win32", "error": self.load_error}

    def save_office(self, payload):
        enabled = payload.get("enabled", True)
        paths = payload.get("paths", {})
        if not isinstance(enabled, bool) or not isinstance(paths, dict) or set(paths) - set(OFFICE_APPS):
            raise ValueError("Choose valid Office apps to link.")
        validated = {key: local_program(paths.get(key, ""), filename) for key, (_, filename) in OFFICE_APPS.items()}
        if enabled and not any(validated.values()) and not any(self.detected.get(key) for key in OFFICE_APPS):
            raise ValueError("No desktop Office apps were found. Install Office or Browse to an existing installation.")
        with self.lock:
            self._save("office", {"enabled": enabled, "paths": validated})
        return self.status()

    def open_office(self, app_id):
        if not isinstance(app_id, str) or app_id not in OFFICE_APPS:
            raise ValueError("Choose Word, Excel, or PowerPoint.")
        with self.lock:
            app = next(item for item in self.status()["office"]["apps"] if item["id"] == app_id)
            if not app["linked"]:
                raise ValueError("Save the Office link first, and check that the app is installed on Windows.")
            executable = local_program(app["path"], OFFICE_APPS[app_id][1])
            # Intentional interactive application, with no shell or document args.
            subprocess.Popen([executable], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"message": f"Opened {app['label']}. Use its Account menu to check or change the Microsoft sign-in."}

    def unlink_office(self):
        with self.lock:
            self._save("office", {**self.saved.get("office", {}), "enabled": False})
        return self.status()

    def save_govdash(self, payload):
        enabled = payload.get("enabled", True)
        browser_id = payload.get("browser", "edge")
        if not isinstance(enabled, bool) or not isinstance(browser_id, str) or browser_id not in BROWSERS:
            raise ValueError("Choose Microsoft Edge or Google Chrome.")
        url = govdash_url(payload.get("url", GOVDASH_URL))
        executable = local_program(payload.get("executable", ""), BROWSERS[browser_id][1])
        with self.lock:
            if self.browser.status()["state"] not in {"closed", "error"}:
                raise ValueError("Close the Coven GovDash window before changing its connection.")
            if enabled and not (executable or self.detected.get(browser_id)):
                raise ValueError("Install Microsoft Edge or Google Chrome, or Browse to its executable.")
            previous = self.saved.get("govdash", {})
            if previous.get("url") and previous["url"] != url and self.browser.has_profile():
                raise ValueError("Forget the saved GovDash sign-in before changing dashboard addresses.")
            self._save("govdash", {"enabled": enabled, "browser": browser_id, "executable": executable, "url": url})
        return self.status()

    def open_govdash(self):
        with self.lock:
            settings = self.status()["govdash"]
            if not settings["enabled"] or not settings["browserAvailable"]:
                raise ValueError("Save a GovDash browser connection first. This feature requires Windows and an installed browser.")
            executable = local_program(settings["executable"], BROWSERS[settings["browser"]][1])
            return self.browser.open(settings["browser"], executable, govdash_url(settings["url"]))

    def unlink_govdash(self):
        with self.lock:
            if self.browser.status()["state"] not in {"closed", "error"}:
                raise ValueError("Close the GovDash window before unlinking it.")
            self._save("govdash", {**self.saved.get("govdash", {}), "enabled": False})
        return self.status()

    def open_downloads(self):
        if sys.platform != "win32":
            raise ValueError("Open downloads is available in the Windows desktop app.")
        self.browser.download_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.browser.download_dir))
        return {"message": "Opened Coven’s GovDash downloads folder."}

    def _save(self, section, values):
        updated = {**self.saved, section: values}
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        self.saved = updated
        self.load_error = ""

    def close(self):
        self.browser.shutdown()
