from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendStaticTests(unittest.TestCase):
    def test_app_does_not_use_dynamic_inner_html(self):
        source = (ROOT / "public" / "src" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", source)

    def test_failure_overlay_has_explicit_hidden_rule(self):
        css = (ROOT / "public" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("[hidden]", css)
        self.assertIn("display: none !important", css)

    def test_auth_page_does_not_place_token_in_url(self):
        source = (ROOT / "public" / "src" / "auth.js").read_text(encoding="utf-8")
        self.assertNotIn("location.search", source)
        self.assertNotIn("URLSearchParams", source)

    def test_auth_page_waits_for_pywebview_api(self):
        source = (ROOT / "public" / "src" / "auth.js").read_text(encoding="utf-8")
        self.assertIn("pywebviewready", source)
        self.assertIn("refreshDesktopUnlock", source)

    def test_voice_uses_local_backend_not_browser_speech_recognition(self):
        source = (ROOT / "public" / "src" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn("SpeechRecognition", source)
        self.assertNotIn("webkitSpeechRecognition", source)
        self.assertIn("/api/voice/start", source)
        self.assertIn("encodeWav", source)

    def test_setup_wizard_uses_backend_secret_storage(self):
        source = (ROOT / "public" / "src" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")

        self.assertIn("/api/setup/provider", source)
        self.assertIn("/api/setup/workspace", source)
        self.assertIn("choose_folder", source)
        self.assertIn("providerApiKey", html)
        self.assertNotIn("localStorage", source[source.find("saveProviderCredential") : source.find("removeProviderCredential")])


if __name__ == "__main__":
    unittest.main()
