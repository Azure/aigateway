"""Published-release freshness and installed-artifact checks; no network or installation."""

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cli_release import latest_release, require_current_cli, verify_installed_release
from core import MigrationError
from gateway import inspect_cli


def release(version, *, draft=False):
    name = f"aigateway-{version}-py3-none-any.whl"
    tag = "cli-v" + version
    return {
        "tag_name": tag, "draft": draft, "prerelease": "b" in version,
        "published_at": "2026-01-01T00:00:00Z",
        "assets": [{"name": name, "digest": "sha256:" + "a" * 64,
                    "browser_download_url": f"https://github.com/Azure/aigateway/releases/download/{tag}/{name}"}],
    }


class PublishedCliTests(unittest.TestCase):
    def test_previews_and_numeric_versions_are_considered_not_stable_latest_only(self):
        selected = latest_release(lambda page: [
            release("1.0.0b9"), release("1.0.0b15"), release("1.0.0b99", draft=True),
            {"tag_name": "plugin-v9", "draft": False, "assets": []}])
        self.assertEqual(selected["version"], "1.0.0b15")
        selected = latest_release(lambda page: [release("1.0.0rc2"), release("1.0.0")])
        self.assertEqual(selected["version"], "1.0.0")

    def test_release_enumeration_is_complete_and_does_not_assume_api_order(self):
        first = [release("1.0.0b14") for _ in range(100)]
        pages = []
        def fetch(page):
            pages.append(page)
            return first if page == 1 else [release("1.0.0b15")]
        self.assertEqual(latest_release(fetch)["version"], "1.0.0b15")
        self.assertEqual(pages, [1, 2])
        with self.assertRaises(MigrationError):
            latest_release(lambda page: first)

    def test_missing_latest_assets_or_checksum_never_fall_back_to_an_older_release(self):
        for field, value in (("assets", []), ("tag_name", "cli-v1.0.0.dev16")):
            latest = release("1.0.0b16")
            latest[field] = value
            with self.subTest(field=field), self.assertRaises(MigrationError):
                latest_release(lambda page: [release("1.0.0b15"), latest])
        for field, value in (("digest", None), ("browser_download_url", "https://other.example/package.whl")):
            latest = release("1.0.0b16")
            latest["assets"][0][field] = value
            with self.subTest(field=field), self.assertRaises(MigrationError):
                latest_release(lambda page: [release("1.0.0b15"), latest])
        renamed = release("2.0.0")
        renamed["tag_name"] = "v2.0.0"
        with self.assertRaises(MigrationError):
            latest_release(lambda page: [release("1.0.0b15"), renamed])

    def test_stale_and_unpublished_local_builds_are_not_accepted(self):
        current = latest_release(lambda page: [release("1.0.0b15")])
        require_current_cli("1.0.0b15", current)
        for version in ("1.0.0b14", "1.0.0b99", "local-build"):
            with self.subTest(version=version), self.assertRaises(MigrationError):
                require_current_cli(version, current)
        with patch("gateway.run_az", return_value={"extensionName": "aigateway", "extensionVersion": "1.0.0b14"}) as run, \
                patch("gateway.latest_release", return_value=current), self.assertRaises(MigrationError):
            inspect_cli()
        self.assertEqual(run.call_count, 1)

    def test_unavailable_release_metadata_does_not_use_cached_or_local_source(self):
        with patch("gateway.run_az", return_value={"extensionName": "aigateway", "extensionVersion": "1.0.0b15"}), \
                patch("gateway.latest_release", side_effect=MigrationError("Unavailable.")), \
                self.assertRaises(MigrationError):
            inspect_cli()

    def test_installed_python_files_must_match_the_official_verified_wheel(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "azext_aigateway"
            package.mkdir()
            source = b"VALUE = 1\n"
            (package / "__init__.py").write_bytes(source)
            wheel = root / "aigateway-1.0.0b15-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("azext_aigateway/__init__.py", source)
            published = {"wheelName": wheel.name, "wheelSha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
            self.assertEqual(verify_installed_release(package, published), published["wheelSha256"])
            (package / "__init__.py").write_bytes(b"VALUE = 2\n")
            with self.assertRaises(MigrationError):
                verify_installed_release(package, published)
            (package / "__init__.py").write_bytes(source)
            (package / "local_overlay.py").write_text("VALUE = 3\n")
            with self.assertRaises(MigrationError):
                verify_installed_release(package, published)
            (package / "local_overlay.py").unlink()
            published["wheelSha256"] = "0" * 64
            with self.assertRaises(MigrationError):
                verify_installed_release(package, published)

    def test_reissued_unreviewed_wheel_is_not_accepted_by_version_alone(self):
        current = latest_release(lambda page: [release("1.0.0b15")])
        with patch("gateway.run_az", return_value={"extensionName": "aigateway", "extensionVersion": "1.0.0b15"}), \
                patch("gateway.latest_release", return_value=current), self.assertRaises(MigrationError):
            inspect_cli()


if __name__ == "__main__":
    unittest.main()
