"""Finding the Azure CLI, and saying so when it is not there.

Regression: on Windows the CLI is `az.cmd`, a batch file. CreateProcess appends
only `.exe` to a bare name, so `subprocess.run(["az", ...])` raised
FileNotFoundError on a machine with a working, logged-in CLI -- and the failure
surfaced three layers up as "API Management service not found".
"""

import subprocess

import pytest

from migrate_apim import azcli
from migrate_apim.arm import ArmAuthError, ArmClient
from migrate_apim.collect import Collector, CollectOptions
from fake_arm import SERVICE


@pytest.fixture(autouse=True)
def forget_the_cached_path():
    azcli.az_executable(refresh=True)
    yield
    azcli.az_executable(refresh=True)


class TestResolvingAz:
    def test_a_windows_batch_file_is_what_gets_run(self, monkeypatch):
        monkeypatch.setattr(azcli.shutil, "which", lambda _n: r"C:\Program Files\az\wbin\az.cmd")
        azcli.az_executable(refresh=True)
        assert azcli.az_argv(["az", "account", "show"]) == [
            r"C:\Program Files\az\wbin\az.cmd", "account", "show"
        ]

    def test_a_posix_path_is_substituted_the_same_way(self, monkeypatch):
        monkeypatch.setattr(azcli.shutil, "which", lambda _n: "/usr/bin/az")
        azcli.az_executable(refresh=True)
        assert azcli.az_argv(["az", "--version"]) == ["/usr/bin/az", "--version"]

    def test_an_unresolvable_name_is_left_alone_for_the_caller_to_fail_on(self, monkeypatch):
        monkeypatch.setattr(azcli.shutil, "which", lambda _n: None)
        azcli.az_executable(refresh=True)
        assert azcli.az_argv(["az", "--version"]) == ["az", "--version"]
        assert azcli.az_available() is False

    def test_a_command_that_is_not_az_is_untouched(self, monkeypatch):
        monkeypatch.setattr(azcli.shutil, "which", lambda _n: "/usr/bin/az")
        azcli.az_executable(refresh=True)
        assert azcli.az_argv(["bicep", "build"]) == ["bicep", "build"]


class TestAnAbsentCliIsFatal:
    """No token means no request, so it is not one collection's bad luck."""

    def test_token_acquisition_says_the_cli_is_missing(self, monkeypatch):
        def _missing(*_args, **_kwargs):
            raise FileNotFoundError(2, "No such file or directory", "az")

        monkeypatch.setattr(subprocess, "run", _missing)
        with pytest.raises(ArmAuthError, match="not on PATH"):
            ArmClient()._access_token()

    def test_a_failed_login_is_an_auth_error_not_a_read_error(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda *_a, **_k: subprocess.CompletedProcess([], 1, "", "Please run 'az login'"),
        )
        with pytest.raises(ArmAuthError, match="az login"):
            ArmClient()._access_token()

    def test_the_collector_reraises_it_instead_of_recording_a_coverage_entry(self, monkeypatch):
        """The bug this fixes: `_get` caught it, so the cause never reached the operator."""
        def _missing(*_args, **_kwargs):
            raise FileNotFoundError(2, "No such file or directory", "az")

        monkeypatch.setattr(subprocess, "run", _missing)
        collector = Collector(ArmClient(), SERVICE, CollectOptions(cognitive_api_version="2025-06-01"))
        with pytest.raises(ArmAuthError, match="not on PATH"):
            collector.run()

    def test_the_cli_reports_it_on_one_line_rather_than_a_traceback(self, monkeypatch, capsys):
        from migrate_apim.cli import main

        def _missing(*_args, **_kwargs):
            raise FileNotFoundError(2, "No such file or directory", "az")

        monkeypatch.setattr(subprocess, "run", _missing)
        code = main(["collect", "--apim", "apim-demo", "-g", "rg", "--subscription", "sub", "-o", "-"])
        assert code == 1
        assert "not on PATH" in capsys.readouterr().err
