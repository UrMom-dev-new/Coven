import json
import subprocess
import sys
from unittest import mock
import unittest

from coven.configuration import load_app_config
from coven.processes import background_process_options
from coven.runtime import RuntimeInspector
from coven.voice import _ensure_whisper_server


class BackgroundProcessTests(unittest.TestCase):
    def test_no_windows_flags_on_other_platforms(self):
        with mock.patch("coven.processes.sys.platform", "linux"):
            self.assertEqual(background_process_options(), {})

    def test_runtime_probe_hides_console_and_preserves_diagnostics(self):
        inspector = RuntimeInspector(load_app_config())
        command = [r"C:\Users\Test User\AppData\Local\hermes.exe", "--version"]
        with (
            mock.patch("coven.processes.sys.platform", "win32"),
            mock.patch("coven.processes.subprocess.CREATE_NO_WINDOW", 0x08000000, create=True),
            mock.patch("coven.runtime.subprocess.run") as run,
        ):
            run.return_value = subprocess.CompletedProcess(command, 0, "Hermes test\n", "")
            self.assertEqual(inspector._run_capture(command, timeout=2)["output"], "Hermes test")
            self.assertEqual(run.call_args.args[0], command)
            self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)
            self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
            self.assertTrue(run.call_args.kwargs["capture_output"])
            self.assertFalse(run.call_args.kwargs.get("shell", False))

            run.return_value = subprocess.CompletedProcess(command, 1, "", "probe failed\n")
            failed = inspector._run_capture(command, timeout=2)
            self.assertFalse(failed["ok"])
            self.assertEqual(failed["error"], "probe failed")

            run.side_effect = subprocess.TimeoutExpired(command, 2)
            self.assertEqual(inspector._run_capture(command, timeout=2)["error"], "timed out")

    def test_whisper_server_is_hidden_and_reused(self):
        job = {
            "runtimeExecutable": r"C:\Users\Test User\AppData\Local\whisper-server.exe",
            "modelPath": r"C:\Users\Test User\AppData\Local\voice model.bin",
            "threads": 2,
            "language": "en",
        }
        with (
            mock.patch("coven.processes.sys.platform", "win32"),
            mock.patch("coven.processes.subprocess.CREATE_NO_WINDOW", 0x08000000, create=True),
            mock.patch("coven.voice.subprocess.Popen") as popen,
            mock.patch("coven.voice._free_loopback_port", return_value=12345),
            mock.patch("coven.voice.urllib.request.urlopen") as urlopen,
        ):
            popen.return_value.poll.return_value = None
            urlopen.return_value.__enter__.return_value.status = 200
            server = _ensure_whisper_server(None, job)
            command = popen.call_args.args[0]
            self.assertEqual(command[0], job["runtimeExecutable"])
            self.assertEqual(command[command.index("-m") + 1], job["modelPath"])
            self.assertEqual(popen.call_args.kwargs["creationflags"], 0x08000000)
            self.assertEqual(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
            self.assertFalse(popen.call_args.kwargs.get("shell", False))
            self.assertIs(_ensure_whisper_server(server, job), server)
            popen.assert_called_once()

    @unittest.skipUnless(sys.platform == "win32", "Requires a real Windows process")
    def test_windows_child_has_no_console_and_cannot_read_user_input(self):
        script = (
            "import ctypes,json,sys; "
            "ctypes.windll.kernel32.GetConsoleWindow.restype = ctypes.c_void_p; "
            "print(json.dumps({'console': ctypes.windll.kernel32.GetConsoleWindow(), "
            "'stdin': sys.stdin.read()}))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
            **background_process_options(),
        )
        payload = json.loads(result.stdout)
        self.assertFalse(payload["console"])
        self.assertEqual(payload["stdin"], "")


if __name__ == "__main__":
    unittest.main()
