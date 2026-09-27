import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest import mock

from coven.configuration import load_app_config
from coven.govdash_browser import GovDashBrowser, persistent_browser_options
from coven.integrations import IntegrationManager
from coven.linked_apps import LinkedApps, GOVDASH_URL, govdash_url, local_program
import test_connection_settings as settings_tests


class LinkedAppTests(unittest.TestCase):
    def test_only_published_https_govdash_addresses_are_saved(self):
        self.assertEqual(govdash_url("https://dashboard.govdash.us/login"), GOVDASH_URL)
        for value in ["http://dashboard.govdash.us", "https://dashboard.govdash.us.evil.test", "https://evil.test",
                      "https://user:secret@dashboard.govdash.us", "https://dashboard.govdash.us/?token=secret",
                      "https://dashboard.govdash.us/auth/callback", "https://dashboard.govdash.us:1234", {}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                govdash_url(value)

    def test_program_paths_reject_arguments_wrong_programs_and_relative_paths(self):
        with TemporaryDirectory() as tmp:
            word = Path(tmp) / "WINWORD.EXE"
            word.touch()
            self.assertEqual(local_program(f'"{word}"', "WINWORD.EXE"), str(word.resolve()))
            self.assertEqual(local_program(tmp, "WINWORD.EXE"), str(word.resolve()))
            for value in [str(word) + " /anything", "WINWORD.EXE", str(word.with_name("missing.exe")), {}]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    local_program(value, "WINWORD.EXE")

    def test_office_links_persist_and_open_exact_selected_app_without_shell(self):
        with TemporaryDirectory() as tmp, mock.patch("coven.linked_apps.find_windows_program", return_value=""):
            root = Path(tmp)
            word = root / "Office with spaces" / "WINWORD.EXE"
            word.parent.mkdir()
            word.touch()
            links = LinkedApps(root / "coven")
            links.save_office({"enabled": True, "paths": {"word": str(word)}})
            loaded = LinkedApps(root / "coven")
            with mock.patch("coven.linked_apps.sys.platform", "win32"), mock.patch("coven.linked_apps.subprocess.Popen") as launch:
                self.assertTrue(loaded.status()["office"]["apps"][0]["linked"])
                loaded.open_office("word")
                self.assertEqual(launch.call_args.args[0], [str(word.resolve())])
                self.assertFalse(launch.call_args.kwargs.get("shell", False))
            self.assertIsNone(loaded.status()["office"]["authenticated"])
            loaded.unlink_office()
            self.assertEqual(loaded.saved["office"]["paths"]["word"], str(word.resolve()))
            with self.assertRaises(ValueError):
                loaded.open_office("word")

    def test_govdash_preferences_survive_restart_but_never_claim_authentication(self):
        with TemporaryDirectory() as tmp, mock.patch("coven.linked_apps.find_windows_program", return_value=""):
            root = Path(tmp)
            edge = root / "msedge.exe"
            edge.touch()
            links = LinkedApps(root / "coven")
            links.save_govdash({"enabled": True, "url": GOVDASH_URL, "browser": "edge", "executable": str(edge)})
            loaded = LinkedApps(root / "coven")
            status = loaded.status()["govdash"]
            self.assertEqual(status["executable"], str(edge.resolve()))
            self.assertIsNone(status["authenticated"])
            self.assertFalse(status["session"]["savedProfile"])
            (loaded.browser.root / "edge").mkdir(parents=True)
            self.assertTrue(loaded.status()["govdash"]["session"]["savedProfile"])
            loaded.unlink_govdash()
            self.assertFalse(loaded.status()["govdash"]["enabled"])
            self.assertTrue(loaded.browser.has_profile())
            with self.assertRaises(ValueError):
                loaded.save_govdash({"enabled": True, "url": "https://dashboard-transition.govdash.us", "executable": str(edge)})

    def test_configuration_does_not_count_as_operational_agent_integration(self):
        with TemporaryDirectory() as tmp, mock.patch("coven.linked_apps.find_windows_program", return_value=""):
            manager = IntegrationManager(load_app_config())
            manager.linked_apps = LinkedApps(Path(tmp))
            self.assertFalse(manager.office_status()["operational"])
            self.assertFalse(manager.govdash_status()["operational"])
            self.assertIsNone(manager.govdash_status()["authenticated"])

    def test_corrupt_saved_links_do_not_stop_the_app(self):
        with TemporaryDirectory() as tmp, mock.patch("coven.linked_apps.find_windows_program", return_value=""):
            root = Path(tmp)
            (root / "connections").mkdir()
            for payload in [{"office": "bad"}, {"govdash": {"browser": "invalid"}}, {"office": {"enabled": "yes"}}]:
                (root / "connections/linked-apps.json").write_text(json.dumps(payload))
                links = LinkedApps(root)
                self.assertTrue(links.load_error)
                self.assertFalse(links.status()["office"]["enabled"])

    def test_forget_removes_only_fixed_profile_folders_and_preserves_downloads(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = GovDashBrowser(root / "profiles")
            for name in ["edge", "chrome", "unrelated"]:
                (browser.root / name).mkdir(parents=True)
                (browser.root / name / "fixture").write_text("test session")
            browser.download_dir.mkdir()
            artifact = browser.download_dir / "proposal.docx"
            artifact.write_text("keep document")
            browser.forget()
            deadline = time.monotonic() + 2
            while browser.status()["state"] == "forgetting" and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            self.assertEqual(browser.status()["state"], "closed")
            self.assertFalse(browser.has_profile())
            self.assertTrue((browser.root / "unrelated" / "fixture").is_file())
            self.assertEqual(artifact.read_text(), "keep document")
            browser.shutdown()

    def test_forget_is_blocked_while_browser_open_and_delete_failure_is_not_success(self):
        with TemporaryDirectory() as tmp:
            browser = GovDashBrowser(Path(tmp) / "profiles")
            browser._set(state="open")
            with self.assertRaises(ValueError):
                browser.forget()
            browser._set(state="closed")
            (browser.root / "edge").mkdir(parents=True)
            with mock.patch("coven.govdash_browser.shutil.rmtree", side_effect=PermissionError("locked")):
                browser.forget()
                deadline = time.monotonic() + 2
                while browser.status()["state"] == "forgetting" and time.monotonic() < deadline:
                    threading.Event().wait(0.01)
                self.assertEqual(browser.status()["state"], "error")
                self.assertTrue(browser.has_profile())
            browser.shutdown()

    def test_browser_launch_keeps_sandbox_without_tcp_debugging_or_storage_exports(self):
        options = persistent_browser_options(Path("test-only-profile"), "msedge.exe")
        self.assertTrue(options["chromium_sandbox"])
        self.assertFalse(options["headless"])
        self.assertFalse(any("remote-debugging-port" in argument or "no-sandbox" in argument for argument in options["args"]))
        self.assertNotIn("storage_state", options)

    def test_navigation_does_not_treat_a_dashboard_url_as_verified_login(self):
        with TemporaryDirectory() as tmp:
            browser = GovDashBrowser(Path(tmp))
            frame = mock.Mock(url="https://dashboard.govdash.us/")
            page = mock.Mock(main_frame=frame)
            browser._navigation(frame, page, GOVDASH_URL)
            self.assertEqual(browser.status()["authState"], "not_checked")
            frame.url = "https://dashboard.govdash.us/login?callback_token=private-fixture"
            browser._navigation(frame, page, GOVDASH_URL)
            self.assertEqual(browser.status()["authState"], "sign_in_required")
            self.assertNotIn("private-fixture", json.dumps(browser.status()))

    def test_download_filename_cannot_escape_or_overwrite_existing_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = GovDashBrowser(root / "profiles")
            browser.download_dir.mkdir()
            existing = browser.download_dir / "proposal.docx"
            existing.write_text("original")
            download = mock.Mock(suggested_filename="../../outside\\proposal.docx")
            download.save_as.side_effect = lambda name: Path(name).write_text("downloaded fixture")
            browser._save_download(download)
            saved = Path(download.save_as.call_args.args[0])
            self.assertEqual(saved.parent, browser.download_dir)
            self.assertEqual(existing.read_text(), "original")
            self.assertEqual(saved.read_text(), "downloaded fixture")


class LinkedAppsHTTPTests(unittest.TestCase):
    setUp = settings_tests.SettingsHTTPTests.setUp
    tearDown = settings_tests.SettingsHTTPTests.tearDown
    request = settings_tests.SettingsHTTPTests.request

    def test_app_routes_require_authentication_and_intent(self):
        self.assertEqual(self.request("/api/setup/apps", authenticated=False)[0], 401)
        for path in ["office", "office/open", "office/unlink", "govdash", "govdash/open", "govdash/close", "govdash/forget", "govdash/unlink", "govdash/downloads", "detect"]:
            self.assertEqual(self.request("/api/setup/apps/" + path, {}, intent=False)[0], 403)

    def test_linked_apps_and_adapter_share_workspace_and_integration_state(self):
        self.assertIs(self.server.agent_adapter.integrations, self.server.integrations)
        self.server.apply_hermes()
        self.assertIs(self.server.agent_adapter.integrations, self.server.integrations)
        self.assertIs(self.server.integrations.linked_apps, self.server.linked_apps)

    def test_bad_app_requests_return_errors_without_launching(self):
        with mock.patch("coven.linked_apps.subprocess.Popen") as launch:
            for app in ["shell", {}, None]:
                self.assertEqual(self.request("/api/setup/apps/office/open", {"app": app})[0], 400)
            self.assertEqual(self.request("/api/setup/apps/govdash", {"browser": {}})[0], 400)
            self.assertEqual(self.request("/api/setup/apps/govdash", {"url": "https://evil.test/"})[0], 400)
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
