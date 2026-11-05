"""Exercise canonical installers with real wheel bytes and isolated Azure CLI state.

Set CLI_TEST_WHEEL to a local copy of the pinned wheel, or download it publicly.
Set CLI_TEST_REAL_AZ=1 to also exercise real Azure CLI clean/upgrade/reinstall paths.
Set CLI_TEST_OLD_WHEEL to a local b6 wheel to avoid downloading the older release.
Requires Bash and PowerShell on PATH. No Azure login or resource access is used.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.request


CLI = Path(__file__).resolve().parents[1]
VERSION = "1.0.0b22"
SHA256 = "3363ee0efde6ec22f445fd11f2b6b625867c1ab49b8ab76108f6e1bfa920060a"
URL = (
    "https://github.com/Azure/ai-gateway/releases/download/"
    f"cli-v{VERSION}/aigateway-{VERSION}-py3-none-any.whl"
)
OLD_URL = (
    "https://github.com/Azure/ai-gateway/releases/download/"
    "cli-v1.0.0b6/aigateway-1.0.0b6-py3-none-any.whl"
)
OLD_SHA256 = "77a604d0f301f330602f430f22130b99af904dc627f44d3d035bf61c6354fe76"

CURL = r"""#!/usr/bin/env python3
import os, pathlib, shutil, sys
args = sys.argv[1:]
assert args[-1] == os.environ["TEST_URL"], args
assert "--fail" in args and "--location" in args, args
assert args[args.index("--proto") + 1] == "=https", args
if os.environ.get("TEST_DOWNLOAD_FAIL"):
    sys.stderr.write("test download failure\n")
    sys.exit(22)
shutil.copyfile(os.environ["TEST_WHEEL"], args[args.index("--output") + 1])
print(os.environ.get("TEST_EFFECTIVE_URL", args[-1]), end="")
"""

AZ = r"""#!/usr/bin/env python3
import hashlib, json, os, pathlib, subprocess, sys
args = sys.argv[1:]
with open(os.environ["TEST_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
if os.environ.get("TEST_REAL_AZ"):
    sys.exit(subprocess.call([os.environ["TEST_REAL_AZ"], *args]))
state_path = pathlib.Path(os.environ["TEST_STATE"])
state = json.loads(state_path.read_text())
if args[:2] == ["extension", "list"]:
    if os.environ.get("TEST_LIST_FAIL"):
        sys.stderr.write("test extension list failure\n")
        sys.exit(7)
    query = args[args.index("--query") + 1]
    print(("aigateway" if query.endswith(".name") else state.get("version", ""))
          if state.get("version") else "")
elif args[:2] == ["extension", "remove"]:
    if os.environ.get("TEST_REMOVE_FAIL"):
        sys.stderr.write("test remove failure\n")
        sys.exit(8)
    state = {}
elif args[:2] == ["extension", "add"]:
    wheel = pathlib.Path(args[args.index("--source") + 1])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == os.environ["TEST_SHA256"]
    assert "--upgrade" in args and "--yes" in args, args
    if os.environ.get("TEST_ADD_FAIL"):
        sys.stderr.write("test installation failure\n")
        sys.exit(9)
    # Match Azure CLI: --upgrade does not replace equal versions.
    if state.get("version") != "1.0.0b22":
        state = {"version": "1.0.0b22", "official": True}
elif args[:2] == ["aigateway", "version"]:
    values = {"extensionName": os.environ.get("TEST_NAME", "aigateway"),
              "extensionVersion": os.environ.get("TEST_VERSION", state["version"]),
              "apiVersion": os.environ.get("TEST_API", "2025-09-01-preview")}
    print(values[args[args.index("--query") + 1]] if "--query" in args
          else json.dumps(values))
else:
    raise AssertionError(args)
state_path.write_text(json.dumps(state))
"""

POWERSHELL = r"""
$ErrorActionPreference = 'Stop'
function Invoke-WebRequest {
    param($Uri, $OutFile, $UseBasicParsing, $MaximumRedirection,
          $ErrorAction, $SslProtocol)
    if ([string]$Uri -ne $env:TEST_URL) { throw "Unexpected wheel URL: $Uri" }
    if ($env:TEST_DOWNLOAD_FAIL) { throw 'test download failure' }
    [System.IO.File]::Copy($env:TEST_WHEEL, $OutFile)
}
if ($env:TEST_PIPELINE) {
    Get-Content -LiteralPath $env:TEST_SCRIPT -Raw | Invoke-Expression
} else {
    & $env:TEST_SCRIPT @args
}
"""


def get_wheel(variable, url, target, digest):
    if os.environ.get(variable):
        shutil.copyfile(os.environ[variable], target)
    else:
        urllib.request.urlretrieve(url, target)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != digest:
        raise AssertionError(f"{target.name}: expected {digest}, got {actual}")


class Installers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bash = shutil.which("bash")
        cls.pwsh = shutil.which("pwsh")
        if not cls.bash or not cls.pwsh:
            raise RuntimeError("Both bash and pwsh are required to test both installers.")
        cls.real_az = shutil.which("az")
        cls.assets = tempfile.TemporaryDirectory(prefix="aigateway-test-assets-")
        cls.addClassCleanup(cls.assets.cleanup)
        cls.wheel = Path(cls.assets.name) / URL.rsplit("/", 1)[-1]
        get_wheel("CLI_TEST_WHEEL", URL, cls.wheel, SHA256)
        if os.environ.get("CLI_TEST_REAL_AZ") == "1":
            if not cls.real_az:
                raise RuntimeError("Real Azure CLI validation requested, but az is missing.")
            cls.old_wheel = Path(cls.assets.name) / OLD_URL.rsplit("/", 1)[-1]
            get_wheel("CLI_TEST_OLD_WHEEL", OLD_URL, cls.old_wheel, OLD_SHA256)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aigateway-installer-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name, content in (("az", AZ), ("curl", CURL)):
            path = self.bin / name
            path.write_text(content)
            path.chmod(0o755)
        self.ps = self.root / "run.ps1"
        self.ps.write_text(POWERSHELL)
        self.state = self.root / "state.json"
        self.state.write_text("{}")
        self.log = self.root / "az.jsonl"
        self.env = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("AIGATEWAY_INSTALL_", "TEST_", "AZURE_"))
        }
        self.env.update(
            PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
            AZURE_CONFIG_DIR=str(self.root / "config"),
            AZURE_EXTENSION_DIR=str(self.root / "extensions"),
            AZURE_EXTENSION_USE_DYNAMIC_INSTALL="no",
            AZURE_CORE_COLLECT_TELEMETRY="no",
            TEST_WHEEL=str(self.wheel),
            TEST_SHA256=SHA256,
            TEST_URL=URL,
            TEST_STATE=str(self.state),
            TEST_LOG=str(self.log),
            TMPDIR=str(self.root),
        )

    def run_installer(self, shell, *args, pipeline=False):
        script = CLI / ("install.sh" if shell == "bash" else "install.ps1")
        env = dict(self.env, TEST_SCRIPT=str(script))
        if shell == "bash":
            command = [self.bash, str(script), *args]
            if pipeline:
                command = [self.bash, "-c", 'cat "$TEST_SCRIPT" | bash']
        else:
            command = [self.pwsh, "-NoLogo", "-NoProfile", "-File", str(self.ps), *args]
            if pipeline:
                env["TEST_PIPELINE"] = "1"
        return subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("successfully", result.stdout)
        self.assertFalse(list(self.root.glob("aigateway-install*")), "Temporary downloads leaked")

    def test_release_pins(self):
        for filename in ("install.sh", "install.ps1"):
            text = (CLI / filename).read_text()
            self.assertIn(URL, text)
            self.assertIn(SHA256, text)
            self.assertNotIn("1.0.0b6", text)
            self.assertEqual(len(re.findall(r"https://github.com/.+\.whl", text)), 1)

    def test_clean_upgrade_and_same_version(self):
        for shell in ("bash", "powershell"):
            for version in ("", "1.0.0b6", VERSION):
                with self.subTest(shell=shell, version=version):
                    self.state.write_text(json.dumps({"version": version, "official": False}))
                    self.log.unlink(missing_ok=True)
                    self.assert_success(self.run_installer(shell, pipeline=True))
                    state = json.loads(self.state.read_text())
                    self.assertEqual(state, {"version": VERSION, "official": True})
                    removals = [c for c in self.calls() if c[:2] == ["extension", "remove"]]
                    self.assertEqual(len(removals), int(version == VERSION))

    def test_download_and_checksum_failures_preserve_installation(self):
        bad_wheel = self.root / self.wheel.name
        bad_wheel.write_bytes(self.wheel.read_bytes() + b"corrupted")
        for shell in ("bash", "powershell"):
            for failure in ("download", "checksum", "html", "empty"):
                with self.subTest(shell=shell, failure=failure):
                    self.state.write_text(json.dumps({"version": VERSION, "official": False}))
                    self.log.unlink(missing_ok=True)
                    self.env.pop("TEST_DOWNLOAD_FAIL", None)
                    self.env["TEST_WHEEL"] = str(self.wheel)
                    if failure == "download":
                        self.env["TEST_DOWNLOAD_FAIL"] = "1"
                    else:
                        bad_wheel.write_bytes({
                            "checksum": self.wheel.read_bytes() + b"corrupted",
                            "html": b"<!doctype html><html>Sign in</html>",
                            "empty": b"",
                        }[failure])
                        self.env["TEST_WHEEL"] = str(bad_wheel)
                    result = self.run_installer(shell)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertNotIn("successfully", result.stdout)
                    self.assertEqual(self.calls(), [], "Must verify before any extension mutation")
                    self.assertEqual(json.loads(self.state.read_text())["version"], VERSION)
                    self.assertFalse(list(self.root.glob("aigateway-install*")))

    def test_native_failures_and_version_mismatch(self):
        for shell in ("bash", "powershell"):
            for variable, message in (
                ("TEST_LIST_FAIL", "test extension list failure"),
                ("TEST_REMOVE_FAIL", "test remove failure"),
                ("TEST_ADD_FAIL", "test installation failure"),
                ("TEST_NAME", "is not"),
                ("TEST_VERSION", "does not match"),
                ("TEST_API", "does not match"),
            ):
                with self.subTest(shell=shell, variable=variable):
                    self.state.write_text(json.dumps({"version": VERSION}))
                    self.log.unlink(missing_ok=True)
                    self.env[variable] = "wrong" if variable in ("TEST_NAME", "TEST_VERSION", "TEST_API") else "1"
                    result = self.run_installer(shell)
                    self.env.pop(variable)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn(message, result.stdout + result.stderr)
                    self.assertNotIn("successfully", result.stdout)
                    if variable in ("TEST_LIST_FAIL", "TEST_REMOVE_FAIL"):
                        self.assertFalse(any(c[:2] == ["extension", "add"] for c in self.calls()))

    def test_options_and_overrides(self):
        for shell in ("bash", "powershell"):
            with self.subTest(shell=shell):
                help_arg = "--help" if shell == "bash" else "-Help"
                result = self.run_installer(shell, help_arg)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(VERSION, result.stdout)
                result = self.run_installer(shell, "--source" if shell == "bash" else "-Source")
                self.assertNotEqual(result.returncode, 0)
                self.env["AIGATEWAY_INSTALL_SOURCE"] = "untrusted"
                result = self.run_installer(shell)
                self.env.pop("AIGATEWAY_INSTALL_SOURCE")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("overrides are not supported", result.stdout + result.stderr)
                self.assertEqual(self.calls(), [])

    def test_uninstall(self):
        for shell in ("bash", "powershell"):
            for installed in (False, True):
                with self.subTest(shell=shell, installed=installed):
                    self.state.write_text(json.dumps({"version": VERSION} if installed else {}))
                    self.log.unlink(missing_ok=True)
                    result = self.run_installer(shell, "--uninstall" if shell == "bash" else "-Uninstall")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(json.loads(self.state.read_text()))
                    self.assertFalse(any(c[:2] == ["extension", "add"] for c in self.calls()))

    def test_missing_azure_cli(self):
        (self.bin / "az").unlink()
        self.env["PATH"] = str(self.bin)
        for shell in ("bash", "powershell"):
            with self.subTest(shell=shell):
                result = self.run_installer(shell)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not found", result.stdout + result.stderr)
                self.assertEqual(self.calls(), [])

    @unittest.skipUnless(os.environ.get("CLI_TEST_REAL_AZ") == "1", "Opt-in real Azure CLI installs")
    def test_real_cli_clean_upgrade_and_same_version(self):
        self.env["TEST_REAL_AZ"] = self.real_az
        for shell in ("bash", "powershell"):
            with self.subTest(shell=shell):
                extensions = Path(self.env["AZURE_EXTENSION_DIR"])
                if extensions.exists():
                    shutil.rmtree(extensions)
                self.assert_success(self.run_installer(shell, pipeline=True))
                # Use a real older release to exercise Azure CLI's upgrade implementation.
                for args in (
                    ["extension", "remove", "--name", "aigateway"],
                    ["extension", "add", "--source", str(self.old_wheel), "--yes"],
                ):
                    subprocess.run([self.real_az, *args], env=self.env, check=True,
                                   capture_output=True, text=True, timeout=180)
                self.assert_success(self.run_installer(shell))
                marker = extensions / "aigateway" / "stale-build-marker"
                marker.write_text("Must not survive same-version reinstall")
                self.assert_success(self.run_installer(shell))
                self.assertFalse(marker.exists())
                installed_wheel = extensions / "aigateway" / self.wheel.name
                self.assertEqual(hashlib.sha256(installed_wheel.read_bytes()).hexdigest(), SHA256)
                version = subprocess.run(
                    [self.real_az, "aigateway", "version", "-o", "json"],
                    env=self.env, check=True, capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(json.loads(version.stdout)["extensionVersion"], VERSION)


if __name__ == "__main__":
    unittest.main()
