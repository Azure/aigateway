"""Adopting a release has to move the installers, not only the catalog.

`compile`'s installer-pin check holds `cli/install.sh`, `cli/install.ps1` and
`cli/tests/test_installers.py` to the catalog's version and digest. The first
upgrade this tool performed, b26 to b31, satisfied that by accident: the
release had already moved the installers, so nothing had to know about them.
The next one will not be so lucky, which is what these cover.

Everything here runs on fixtures. No network, no wheel, no installed extension.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "azcli_aigw_apply.py"
spec = importlib.util.spec_from_file_location("azcli_aigw_apply", SCRIPT)
adopt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adopt)

OLD_VERSION, NEW_VERSION = "1.0.0b31", "1.0.0b99"
OLD_DIGEST, NEW_DIGEST = "a" * 64, "b" * 64
# The release the test upgrades *from*. It is a fixture, not a pin, and must
# survive an adoption untouched.
FIXTURE_VERSION, FIXTURE_DIGEST = "1.0.0b6", "c" * 64


@pytest.fixture
def cli_dir(tmp_path: Path) -> Path:
    (tmp_path / "tests").mkdir(parents=True)
    (tmp_path / "install.sh").write_text(
        f'PUBLIC_WHEEL_URL="https://example/cli-v{OLD_VERSION}/aigateway-{OLD_VERSION}'
        f'-py3-none-any.whl"\nEXPECTED_SHA256="{OLD_DIGEST}"\n'
        f'echo "Installs the pinned public aigateway {OLD_VERSION} wheel"\n',
        encoding="utf-8",
    )
    (tmp_path / "install.ps1").write_text(
        f"$PublicWheelUrl = 'https://example/cli-v{OLD_VERSION}/aigateway-{OLD_VERSION}"
        f"-py3-none-any.whl'\n$ExpectedSha256 = '{OLD_DIGEST}'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_installers.py").write_text(
        f'VERSION = "{OLD_VERSION}"\nSHA256 = "{OLD_DIGEST}"\n'
        f'OLD_WHEEL_URL = "cli-v{FIXTURE_VERSION}/aigateway-{FIXTURE_VERSION}'
        f'-py3-none-any.whl"\nOLD_SHA256 = "{FIXTURE_DIGEST}"\n'
        f'assert "{FIXTURE_VERSION}" not in text\n',
        encoding="utf-8",
    )
    return tmp_path


def repin(cli_dir: Path, **kwargs):
    return adopt.repin_installers(
        cli_dir, (OLD_VERSION, OLD_DIGEST), (NEW_VERSION, NEW_DIGEST), **kwargs
    )


class TestTheInstallersFollowTheCatalogue:
    def test_every_installer_carries_the_new_pin(self, cli_dir):
        repin(cli_dir)
        for name in adopt.INSTALLERS:
            text = (cli_dir / name).read_text(encoding="utf-8")
            assert NEW_VERSION in text, f"{name} was not moved to {NEW_VERSION}"
            assert NEW_DIGEST in text, f"{name} does not carry the new digest"

    def test_no_installer_still_names_the_old_release(self, cli_dir):
        repin(cli_dir)
        for name in ("install.sh", "install.ps1"):
            text = (cli_dir / name).read_text(encoding="utf-8")
            assert OLD_VERSION not in text
            assert OLD_DIGEST not in text

    def test_the_upgrade_from_fixture_is_left_alone(self, cli_dir):
        """A version-shaped sweep would rewrite the case that proves upgrading
        works, and the sweep would look like it had succeeded."""
        repin(cli_dir)
        text = (cli_dir / "tests" / "test_installers.py").read_text(encoding="utf-8")
        assert FIXTURE_VERSION in text, "the upgrade-from version was rewritten"
        assert FIXTURE_DIGEST in text, "the upgrade-from digest was rewritten"

    def test_a_dry_run_writes_nothing(self, cli_dir):
        before = {n: (cli_dir / n).read_text(encoding="utf-8") for n in adopt.INSTALLERS}
        report = repin(cli_dir, write=False)
        assert report, "a dry run still reports what it would do"
        for name, text in before.items():
            assert (cli_dir / name).read_text(encoding="utf-8") == text

    def test_a_diverged_installer_stops_the_adoption(self, cli_dir):
        """Already off the catalog's version means the two had diverged. Which
        of them is right is not something this can work out, so it stops."""
        (cli_dir / "install.sh").write_text("PUBLIC_WHEEL_URL=cli-v9.9.9b9\n", encoding="utf-8")
        with pytest.raises(adopt.Abort, match="diverged"):
            repin(cli_dir)

    def test_a_missing_installer_stops_the_adoption(self, cli_dir):
        (cli_dir / "install.ps1").unlink()
        with pytest.raises(adopt.Abort, match="missing"):
            repin(cli_dir)

    def test_the_report_names_every_file_it_touched(self, cli_dir):
        report = repin(cli_dir)
        assert len(report) == len(adopt.INSTALLERS)
        assert all(line.startswith("cli/") for line in report)
