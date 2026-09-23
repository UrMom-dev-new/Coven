from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ServerStaticTests(unittest.TestCase):
    def test_static_assets_support_head_and_no_store_for_code(self):
        source = (ROOT / "coven" / "server.py").read_text(encoding="utf-8")

        self.assertIn("def do_HEAD", source)
        self.assertIn("send_body=False", source)
        self.assertIn('dynamic_suffixes = {".html", ".css", ".js", ".json"}', source)
        self.assertIn("daemon_threads = True", source)
        self.assertIn("if sys.stderr is None", source)

    def test_voice_audio_uses_bounded_binary_endpoint(self):
        source = (ROOT / "coven" / "server.py").read_text(encoding="utf-8")

        self.assertIn("def _read_binary", source)
        self.assertIn("/api/voice/start", source)
        self.assertIn('path.endswith("/audio")', source)
        self.assertIn("max_audio_bytes", source)


if __name__ == "__main__":
    unittest.main()
