from pathlib import Path
import unittest

from coven.desktop import DesktopBridge


ROOT = Path(__file__).resolve().parents[1]


class DesktopStaticTests(unittest.TestCase):
    def test_desktop_bridge_token_is_one_time(self):
        bridge = DesktopBridge("token-123")

        self.assertEqual(bridge.start_session(), "token-123")
        self.assertEqual(bridge.start_session(), "")

    def test_desktop_self_test_validates_packaged_app_surface(self):
        source = (ROOT / "coven" / "desktop.py").read_text(encoding="utf-8")

        self.assertIn("from coven.server import build_server", source)
        self.assertIn("--self-test", source)
        self.assertIn("coven-approved-reference.png", source)
        self.assertIn("--self-test-log", source)
        self.assertIn("sanctuary-art", source)
        self.assertIn("Prepare project brief", source)
        self.assertIn("/api/voice/status", source)
        self.assertIn("Cache-Control", source)
        self.assertIn('getattr(sys, "frozen", False)', source)
        self.assertIn("os._exit(code)", source)

    def test_windows_build_runs_packaged_executable_self_test(self):
        build_script = (ROOT / "scripts" / "build-windows.ps1").read_text(encoding="utf-8")
        installer_script = (ROOT / "scripts" / "build-installer.ps1").read_text(encoding="utf-8")
        smoke_script = (ROOT / "scripts" / "smoke-windows.ps1").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
        launcher = (ROOT / "scripts" / "start-coven.ps1").read_text(encoding="utf-8")

        self.assertIn('python-version: "3.12"', workflow)
        self.assertIn("smoke-windows.ps1", build_script)
        self.assertIn("--self-test", smoke_script)
        self.assertIn("Approved reference image", build_script)
        self.assertIn("smoke-windows.ps1", workflow)
        self.assertIn("self-test failed", smoke_script)
        self.assertIn("$SelfTest", launcher)
        self.assertIn("ISCC.exe", installer_script)
        self.assertIn("Build installer artifact", workflow)
        self.assertIn("Coven-Windows-Installer", workflow)

    def test_pyinstaller_spec_collects_webview_backend_modules(self):
        spec = (ROOT / "packaging" / "Coven.spec").read_text(encoding="utf-8")

        self.assertIn("ROOT = Path(SPECPATH).resolve().parent", spec)
        self.assertIn("pyinstaller_runtime_hook.py", spec)
        self.assertIn("disable_windowed_traceback=True", spec)
        self.assertIn("collect_submodules(\"webview.platforms\")", spec)
        self.assertIn("hiddenimports=hiddenimports", spec)
        self.assertIn("packaging/voice", spec)


if __name__ == "__main__":
    unittest.main()
