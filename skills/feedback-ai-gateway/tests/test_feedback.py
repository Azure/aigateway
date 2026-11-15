import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "feedback", Path(__file__).parents[1] / "scripts" / "feedback.py"
)
feedback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(feedback)


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.summary = self.root / "session-summary.md"
        self.summary.write_text(
            "# Friction\nUser struggled with authentication.\n# Completed\nSetup gateway.\n",
            encoding="utf-8"
        )
        self.output = self.root / "anonymized-summary.md"

    def anonymize(self, **kwargs):
        arguments = {
            "summary_file": self.summary, "output": self.output,
            "sensitive_values": (),
        }
        arguments.update(kwargs)
        return feedback.anonymize_summary(**arguments)

    def test_anonymizes_summary_and_writes_to_output(self):
        output, replacements = self.anonymize()
        self.assertTrue(output.exists())
        self.assertEqual(output.resolve(), self.output.resolve())
        content = output.read_text(encoding="utf-8")
        self.assertIn("Friction", content)
        self.assertIn("Completed", content)
        self.assertEqual(replacements, 0)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)

    def test_scrubs_with_consistent_tokens(self):
        self.summary.write_text(
            "User alice@example.com works at Contoso. alice@example.com failed.",
            encoding="utf-8"
        )
        output, replacements = self.anonymize(sensitive_values=["Contoso"])
        content = output.read_text(encoding="utf-8")
        self.assertNotIn("Contoso", content)
        self.assertNotIn("alice@example.com", content)
        self.assertGreater(replacements, 0)

    def test_common_credentials_and_identifiers_are_scrubbed(self):
        samples = [
            'Authorization: Bearer abc123',
            '{"api_key": "top-secret-value"}',
            "AccountKey=storage-secret;",
            "password='two word secret'",
            "-----BEGIN PRIVATE KEY-----\nprivate-material\n-----END PRIVATE KEY-----",
            "ghp_abcdefghijklmnopqrstuvwxyz",
            "eyJheader.eyJpayload.signature",
            "/subscriptions/sub/resourceGroups/team/providers/Microsoft.ApiManagement/service/name",
            "https://private.example.com/path?sig=signed-value",
            "user@example.com",
            "12345678-1234-1234-1234-123456789abc",
            "/home/alice/project/export.json",
            "C:\\Users\\Alice\\project\\export.json",
            "10.1.2.3",
            "2001:db8::1",
        ]
        scrubber = feedback.Anonymizer()
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertNotEqual(scrubber.scrub(sample), sample)
        self.assertNotIn("abc123", scrubber.scrub(samples[0]))
        self.assertNotIn("top-secret-value", scrubber.scrub(samples[1]))
        self.assertNotIn("two word secret", scrubber.scrub(samples[3]))

    def test_refuses_overwrite_without_changing_existing_output(self):
        self.output.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            self.anonymize()
        self.assertEqual(self.output.read_bytes(), b"existing")

    def test_cli_anonymizes_summary_with_sensitive_values(self):
        self.summary.write_text("Alice reported this failure.", encoding="utf-8")
        sensitive = self.root / "private-values.json"
        sensitive.write_text('["Alice"]', encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(Path(feedback.__file__)),
             "--summary-file", str(self.summary),
             "--sensitive-values-file", str(sensitive),
             "--output", str(self.output)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.output), result.stdout)
        self.assertIn("Nothing uploaded", result.stdout)
        content = self.output.read_text(encoding="utf-8")
        self.assertNotIn("Alice", content)
        self.assertNotIn(sensitive.name, content)

    def test_cli_rejects_malformed_sensitive_values_without_creating_output(self):
        sensitive = self.root / "private-values.json"
        sensitive.write_text('{"not": "an array"}', encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(Path(feedback.__file__)),
             "--summary-file", str(self.summary),
             "--sensitive-values-file", str(sensitive),
             "--output", str(self.output)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Anonymization failed", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_binary_directory_and_symlink_inputs(self):
        binary = self.root / "binary"
        binary.write_bytes(b"not\x00text")
        link = self.root / "link"
        link.symlink_to(self.summary)
        for path in (binary, self.root, link):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.anonymize(summary_file=path)
                self.assertFalse(self.output.exists())

    def test_rejects_size_limit_and_missing_file(self):
        original_limit = feedback.MAX_FILE_BYTES
        feedback.MAX_FILE_BYTES = 2
        try:
            with self.assertRaisesRegex(ValueError, "per-file limit"):
                self.anonymize()
        finally:
            feedback.MAX_FILE_BYTES = original_limit


if __name__ == "__main__":
    unittest.main()
