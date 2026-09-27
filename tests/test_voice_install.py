import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest import mock
import zipfile

from coven.voice import VOICE_MODEL_PROFILES
from coven.voice_install import (VoiceInstaller, InstallCancelled, download_verified, extract_runtime,
                                 RUNTIME_SHA256, RUNTIME_URL, RUNTIME_VERSION)


class Response(io.BytesIO):
    headers = {}
    def geturl(self):
        return "https://trusted.example/file"


class VoiceInstallTests(unittest.TestCase):
    def test_download_rejects_hash_mismatch_oversize_and_cancellation(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "download.bin"
            cancel = threading.Event()
            expected = hashlib.sha256(b"known bytes").hexdigest()
            for data, limit, cancelled, error in [(b"wrong bytes", 100, False, ValueError),
                                                (b"known bytes", 2, False, ValueError),
                                                (b"known bytes", 100, True, InstallCancelled)]:
                cancel.set() if cancelled else cancel.clear()
                with mock.patch("urllib.request.urlopen", return_value=Response(data)), self.assertRaises(error):
                    download_verified("https://trusted.example/file", path, expected, "sha256", cancel, lambda *_: None, limit=limit)
            cancel.clear()
            with mock.patch("urllib.request.urlopen", return_value=Response(b"known bytes")):
                download_verified("https://trusted.example/file", path, expected, "sha256", cancel, lambda *_: None, limit=100)
            self.assertEqual(path.read_bytes(), b"known bytes")

    def test_runtime_zip_rejects_traversal_and_requires_server(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "runtime.zip"
            for unsafe in ["../outside.exe", "..\\outside.exe", "/outside.exe", "C:/outside.exe", "Release/harmless.txt"]:
                with zipfile.ZipFile(archive, "w") as package:
                    package.writestr(unsafe, b"fixture")
                with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                    extract_runtime(archive, root / "stage")
            self.assertFalse((root / "outside.exe").exists())

    def test_failed_or_cancelled_install_does_not_activate_or_replace_working_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "previous-model.bin"
            old.write_bytes(b"working model")
            activate = mock.Mock()
            installer = VoiceInstaller(root, activate)
            for error, state in [(ValueError("bad hash"), "error"), (InstallCancelled("Cancelled"), "cancelled")]:
                with mock.patch("coven.voice_install.download_verified", side_effect=error):
                    installer._install("tiny.en-q5_1")
                self.assertEqual(installer.status()["state"], state)
                self.assertEqual(old.read_bytes(), b"working model")
                self.assertFalse(list(root.glob("download-*")))
                activate.assert_not_called()

    def test_activation_happens_only_after_both_verified_downloads_and_keeps_dlls(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            def fake_download(url, destination, *_args, **_kwargs):
                if url == RUNTIME_URL:
                    with zipfile.ZipFile(destination, "w") as package:
                        package.writestr("Release/whisper-server.exe", b"runtime fixture")
                        package.writestr("Release/whisper.dll", b"dependency fixture")
                else:
                    destination.write_bytes(b"verified model fixture")
            activate = mock.Mock()
            installer = VoiceInstaller(root, activate)
            with mock.patch("coven.voice_install.download_verified", side_effect=fake_download) as download:
                installer._install("tiny.en-q5_1")
            self.assertEqual(download.call_count, 2)
            activated = activate.call_args.args[0]
            exe = Path(activated["runtimeExecutable"])
            self.assertTrue(exe.is_file())
            self.assertTrue(exe.with_name("whisper.dll").is_file())
            self.assertTrue((Path(activated["modelDir"]) / VOICE_MODEL_PROFILES["tiny.en-q5_1"].filename).is_file())
            self.assertEqual(installer.status()["state"], "completed")
            # If settings activation fails, staged files are cleaned up.
            before = set(root.iterdir())
            installer.activate = mock.Mock(side_effect=ValueError("settings unavailable"))
            with mock.patch("coven.voice_install.download_verified", side_effect=fake_download):
                installer._install("tiny.en-q5_1")
            self.assertEqual(installer.status()["state"], "error")
            self.assertEqual(set(root.iterdir()), before)

    def test_shipping_manifest_matches_installer_pins(self):
        manifest = json.loads((Path(__file__).resolve().parents[1] / "packaging/voice/whispercpp-runtime.json").read_text())
        self.assertEqual(manifest["runtime"]["pinnedRelease"], RUNTIME_VERSION)
        self.assertEqual(manifest["runtime"]["sha256"], RUNTIME_SHA256)
        self.assertEqual(manifest["runtime"]["source"], RUNTIME_URL)


if __name__ == "__main__":
    unittest.main()
