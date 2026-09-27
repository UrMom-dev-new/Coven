import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


spec = importlib.util.spec_from_file_location("publish_windows_main", Path(__file__).resolve().parents[1] / "scripts" / "publish-windows-main.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class WindowsReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "portable" / "Coven"
        self.bundle.mkdir(parents=True)
        (self.bundle / "Coven.exe").write_bytes(b"executable fixture")
        self.info = {"version": "0.4.0-beta", "commit": "a" * 40, "runId": "123", "repository": "test/Coven",
                     "executableSha256": release.sha256(self.bundle / "Coven.exe")}
        (self.bundle / "build-info.json").write_text(json.dumps(self.info), encoding="utf-8-sig")
        self.installer = self.root / "installer" / "Coven-Setup-x64.exe"
        self.installer.parent.mkdir()
        self.installer.write_bytes(b"installer fixture")
        self.checksum = self.installer.with_suffix(".exe.sha256")
        self.checksum.write_text(f"{release.sha256(self.installer)}  {self.installer.name}\n")

    def prepare(self, **overrides):
        return release.prepare_assets(self.root, self.root / "output", **{
            "commit": self.info["commit"], "run_id": "123", "repository": "test/Coven", **overrides})

    def test_portable_and_manifest_identify_the_tested_binaries(self):
        _, assets = self.prepare()
        self.assertEqual(len(assets), 5)
        with zipfile.ZipFile(self.root / "output/Coven-Portable-x64.zip") as archive:
            self.assertEqual(archive.read("Coven/Coven.exe"), b"executable fixture")
            self.assertEqual(json.loads(archive.read("Coven/build-info.json").decode("utf-8-sig"))["commit"], self.info["commit"])
        manifest = json.loads((self.root / "output/Coven-build-info.json").read_text())
        for name, digest in manifest["artifacts"].items():
            self.assertEqual(release.sha256(self.root / "output" / name), digest)
        self.assertEqual(manifest["artifacts"][self.installer.name], release.sha256(self.installer))

    def test_wrong_commit_run_or_changed_executable_cannot_publish(self):
        for overrides in ({"commit": "b" * 40}, {"run_id": "456"}, {"repository": "another/repo"}):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, "provenance"):
                self.prepare(**overrides)
        (self.bundle / "Coven.exe").write_bytes(b"changed executable")
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.prepare()

    def test_changed_installer_cannot_publish(self):
        self.installer.write_bytes(b"changed installer")
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.prepare()
