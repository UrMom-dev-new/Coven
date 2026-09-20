from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PresentationStaticTests(unittest.TestCase):
    def test_canvas_game_module_exists_and_uses_visibility_pause(self):
        source = (ROOT / "public" / "src" / "game.js").read_text(encoding="utf-8")
        self.assertIn("requestAnimationFrame", source)
        self.assertIn("visibilitychange", source)
        self.assertIn("coven-select-witch", source)

    def test_voice_boundary_exists(self):
        source = (ROOT / "coven" / "voice.py").read_text(encoding="utf-8")
        self.assertIn("VoiceStatus", source)
        self.assertIn("unconfigured", source)


if __name__ == "__main__":
    unittest.main()
