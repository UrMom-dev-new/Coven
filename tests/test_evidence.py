from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import unittest

from coven.evidence import validate_artifacts


class EvidenceTests(unittest.TestCase):
    def test_model_reported_existence_is_not_trusted_without_workspace_roots(self):
        result = validate_artifacts(
            [{"path": "/tmp/claimed.txt", "exists": True}],
            allowed_roots=(),
        )

        self.assertEqual(result[0]["state"], "reported")
        self.assertIn("No permitted workspace roots", result[0]["notes"][0])

    def test_file_under_allowed_root_is_inspected_and_validated(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "artifact.txt"
            data = b"review output"
            target.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()

            result = validate_artifacts(
                [{"path": str(target), "expectedSha256": digest, "expectedSize": len(data)}],
                allowed_roots=(root,),
            )

            self.assertEqual(result[0]["state"], "validated")
            self.assertEqual(result[0]["sha256"], digest)
            self.assertEqual(result[0]["size"], len(data))

    def test_bad_expected_size_fails_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "artifact.txt"
            target.write_text("review output", encoding="utf-8")

            result = validate_artifacts(
                [{"path": str(target), "expectedSize": "not-a-number"}],
                allowed_roots=(root,),
            )

            self.assertEqual(result[0]["state"], "inspected")
            self.assertIn("did not match", result[0]["notes"][0])

    def test_path_outside_allowed_root_is_not_inspected(self):
        with TemporaryDirectory() as allowed, TemporaryDirectory() as other:
            target = Path(other) / "artifact.txt"
            target.write_text("outside", encoding="utf-8")

            result = validate_artifacts(
                [{"path": str(target), "exists": True}],
                allowed_roots=(Path(allowed).resolve(),),
            )

            self.assertEqual(result[0]["state"], "reported")
            self.assertIn("outside configured permitted workspace roots", result[0]["notes"][0])


if __name__ == "__main__":
    unittest.main()
