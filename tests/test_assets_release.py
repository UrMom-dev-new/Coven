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


if __name__ == "__main__":
    unittest.main()
