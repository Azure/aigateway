import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile


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
        self.session = self.root / "identifying-session-name.jsonl"
        self.session.write_text('{"message": "original session"}\n', encoding="utf-8")
        self.output = self.root / "feedback.zip"

    def bundle(self, **kwargs):
        arguments = {
            "session_files": [self.session], "context_files": [],
            "output": self.output, "agent": "copilot", "sharing": "private",
        }
        arguments.update(kwargs)
        return feedback.create_bundle(**arguments)

    def test_private_export_preserves_content_and_omits_source_paths(self):
        self.bundle()
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.read("session-001.txt"), self.session.read_bytes())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["anonymization"], "none")
            self.assertNotIn(str(self.root), json.dumps(manifest))
            self.assertNotIn(self.session.name, archive.namelist())
            self.assertEqual(set(archive.namelist()), {"session-001.txt", "manifest.json", "REVIEW.txt"})
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)

    def test_issue_requires_anonymization_before_creating_output(self):
        with self.assertRaisesRegex(ValueError, "require --anonymize"):
            self.bundle(sharing="issue")
        self.assertFalse(self.output.exists())

    def test_scrubs_all_selected_files_with_consistent_tokens(self):
        self.session.write_text("Alice works at Contoso. alice@example.com", encoding="utf-8")
        context = self.root / "context.md"
        context.write_text("Alice saw alice@example.com fail.", encoding="utf-8")
        self.bundle(sharing="issue", anonymize=True, context_files=[context],
                    sensitive_values=["Alice", "Contoso"])
        with zipfile.ZipFile(self.output) as archive:
            session = archive.read("session-001.txt").decode()
            context_text = archive.read("context-001.txt").decode()
            self.assertNotIn("Alice", session)
            self.assertNotIn("Contoso", session)
            self.assertNotIn("alice@example.com", session)
            self.assertEqual(session.split()[0], context_text.split()[0])
            manifest = json.loads(archive.read("manifest.json"))
            self.assertTrue(manifest["reviewRequired"])
            self.assertEqual(manifest["anonymization"], "automated-scrub-review-required")

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
            self.bundle()
        self.assertEqual(self.output.read_bytes(), b"existing")

    def test_cli_packages_anonymized_export_without_literal_replacement_file(self):
        self.session.write_text("Alice reported this failure.", encoding="utf-8")
        sensitive = self.root / "private-values.json"
        sensitive.write_text('["Alice"]', encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(Path(feedback.__file__)),
             "--agent", "gemini", "--sharing", "issue", "--anonymize",
             "--session-file", str(self.session),
             "--sensitive-values-file", str(sensitive), "--output", str(self.output)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.output), result.stdout)
        self.assertIn("Nothing uploaded", result.stdout)
        with zipfile.ZipFile(self.output) as archive:
            for name in archive.namelist():
                self.assertNotIn(b"Alice", archive.read(name))
            self.assertNotIn(sensitive.name, archive.namelist())

    def test_cli_rejects_malformed_sensitive_values_without_creating_zip(self):
        sensitive = self.root / "private-values.json"
        sensitive.write_text('{"not": "an array"}', encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(Path(feedback.__file__)),
             "--agent", "other", "--anonymize", "--session-file", str(self.session),
             "--sensitive-values-file", str(sensitive), "--output", str(self.output)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Feedback bundle failed", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_binary_directory_and_symlink_inputs(self):
        binary = self.root / "binary"
        binary.write_bytes(b"not\x00text")
        link = self.root / "link"
        link.symlink_to(self.session)
        for path in (binary, self.root, link):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.bundle(session_files=[path])
                self.assertFalse(self.output.exists())

    def test_rejects_size_limit_and_empty_session_selection(self):
        original_limit = feedback.MAX_FILE_BYTES
        feedback.MAX_FILE_BYTES = 2
        try:
            with self.assertRaisesRegex(ValueError, "per-file limit"):
                self.bundle()
        finally:
            feedback.MAX_FILE_BYTES = original_limit
        with self.assertRaisesRegex(ValueError, "at least one"):
            self.bundle(session_files=[])


if __name__ == "__main__":
    unittest.main()
