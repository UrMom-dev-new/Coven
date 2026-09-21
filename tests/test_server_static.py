from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ServerStaticTests(unittest.TestCase):
    def test_static_assets_support_head_and_no_store_for_code(self):
        source = (ROOT / "coven" / "server.py").read_text(encoding="utf-8")

        self.assertIn("def do_HEAD", source)
        self.assertIn("send_body=False", source)
        self.assertIn('dynamic_suffixes = {".html", ".css", ".js", ".json"}', source)


if __name__ == "__main__":
    unittest.main()
