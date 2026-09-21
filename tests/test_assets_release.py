import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AssetReleaseTests(unittest.TestCase):
    def test_asset_manifest_paths_exist_or_are_runtime_generated(self):
        manifest = json.loads((ROOT / "public" / "assets" / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["assets"])
        for asset in manifest["assets"]:
            path = asset["path"]
            if path.startswith("generated-by"):
                self.assertTrue((ROOT / path.removeprefix("generated-by-")).exists())
            elif "*" in path:
                matches = list((ROOT / "public").glob(path.removeprefix("/").replace("*", "*")))
                self.assertTrue(matches, path)
            else:
                self.assertTrue((ROOT / "public" / path.removeprefix("/")).exists(), path)

    def test_windows_packaging_files_exist(self):
        for path in [
            "coven/desktop.py",
            "packaging/Coven.spec",
            "packaging/installer/Coven.iss",
            "scripts/build-windows.ps1",
            ".github/workflows/windows-build.yml",
        ]:
            self.assertTrue((ROOT / path).exists(), path)

    def test_python_package_discovery_is_explicit(self):
        source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("[build-system]", source)
        self.assertIn("[tool.setuptools.packages.find]", source)
        self.assertIn('include = ["coven*"]', source)
        self.assertIn('exclude = ["config*", "docs*", "packaging*", "public*", "scripts*", "tests*"]', source)

    def test_windows_build_script_stops_on_native_command_failure(self):
        source = (ROOT / "scripts" / "build-windows.ps1").read_text(encoding="utf-8")

        self.assertIn('$PSNativeCommandUseErrorActionPreference = $true', source)


if __name__ == "__main__":
    unittest.main()
