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

        self.assertIn("--self-test", source)
        self.assertIn("coven-approved-reference.png", source)
        self.assertIn("sanctuary-art", source)
        self.assertIn("Prepare project brief", source)
        self.assertIn("Cache-Control", source)

    def test_windows_build_runs_packaged_executable_self_test(self):
        build_script = (ROOT / "scripts" / "build-windows.ps1").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
        launcher = (ROOT / "scripts" / "start-coven.ps1").read_text(encoding="utf-8")

        self.assertIn('python-version: "3.12"', workflow)
        self.assertIn("--self-test", build_script)
        self.assertIn("Approved reference image", build_script)
        self.assertIn("--self-test", workflow)
        self.assertIn("self-test failed", workflow)
        self.assertIn("$SelfTest", launcher)

    def test_pyinstaller_spec_collects_webview_backend_modules(self):
        spec = (ROOT / "packaging" / "Coven.spec").read_text(encoding="utf-8")

        self.assertIn("ROOT = Path(SPECPATH).resolve().parent", spec)
        self.assertIn("collect_submodules(\"webview.platforms\")", spec)
        self.assertIn("hiddenimports=hiddenimports", spec)


if __name__ == "__main__":
    unittest.main()
