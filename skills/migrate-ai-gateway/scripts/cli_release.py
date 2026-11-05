"""Published CLI authority: no local source builds, stale packages or silent fallbacks."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from core import MigrationError, safe_path, unique_keys


REPOSITORY = "Azure/aigateway"
RELEASES_URL = "https://api.github.com/repos/" + REPOSITORY + "/releases"
TAG = re.compile(r"cli-v(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?")


class NoReleaseRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MigrationError("CLI release metadata redirected unexpectedly; verify the authoritative repository.")


def release_page(page):
    path = f"repos/{REPOSITORY}/releases?per_page=100&page={page}"
    if shutil.which("gh"):
        try:
            result = subprocess.run(
                ["gh", "api", "--hostname", "github.com", path],
                capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MigrationError("Cannot verify the latest published CLI release; no older package was accepted.") from exc
        if result.returncode:
            raise MigrationError("Cannot verify CLI releases through GitHub; check connectivity/authentication before continuing.")
        data = result.stdout
    else:
        request = Request(RELEASES_URL + f"?per_page=100&page={page}",
                          headers={"Accept": "application/vnd.github+json", "User-Agent": "ai-gateway-migration"})
        try:
            with build_opener(NoReleaseRedirect()).open(request, timeout=30) as response:
                data = response.read(2 * 1024 * 1024 + 1)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise MigrationError("Cannot verify the latest CLI release; no stale/offline fallback is allowed.") from exc
    if len(data) > 2 * 1024 * 1024:
        raise MigrationError("CLI release metadata exceeds the reviewed processing limit.")
    try:
        return json.loads(data, object_pairs_hook=unique_keys)
    except (ValueError, UnicodeError) as exc:
        raise MigrationError("Malformed published CLI release metadata.") from exc


def latest_release(fetch=release_page):
    """Include preview releases: GitHub's /releases/latest omits them."""
    candidates = []
    for page in range(1, 11):
        releases = fetch(page)
        if not isinstance(releases, list):
            raise MigrationError("Published CLI releases must be an array.")
        for release in releases:
            if not isinstance(release, dict):
                raise MigrationError("Malformed CLI release record.")
            if release.get("draft") is True:
                continue
            tag = release.get("tag_name")
            if not isinstance(tag, str) or not tag.startswith("cli-v"):
                if any(isinstance(asset, dict) and str(asset.get("name", "")).startswith("aigateway-")
                       and str(asset.get("name", "")).endswith(".whl") for asset in release.get("assets") or []):
                    raise MigrationError("CLI release naming changed; review the official release instead of selecting an older one.")
                continue
            match = TAG.fullmatch(tag)
            if not match or not isinstance(release.get("published_at"), str) or not release["published_at"]:
                raise MigrationError("Unreviewed CLI release tag/publication; verify the repository instead of falling back.")
            key = (*map(int, match.group(1, 2, 3)),
                   {"a": 0, "b": 1, "rc": 2, None: 3}[match[4]], int(match[5] or 0))
            candidates.append((key, release))
        if len(releases) < 100:
            break
    else:
        raise MigrationError("Release enumeration is incomplete; cannot assert which CLI is latest.")
    if not candidates:
        raise MigrationError("No published official CLI release found; no local build was substituted.")
    release = max(candidates, key=lambda item: item[0])[1]
    version = release["tag_name"].removeprefix("cli-v")
    name = f"aigateway-{version}-py3-none-any.whl"
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise MigrationError("Latest CLI release omitted its assets.")
    wheels = [asset for asset in assets if isinstance(asset, dict) and asset.get("name") == name]
    if len(wheels) != 1:
        raise MigrationError("Latest CLI wheel is unavailable/ambiguous; do not install an older release.")
    asset = wheels[0]
    expected_url = f"https://github.com/{REPOSITORY}/releases/download/{release['tag_name']}/{name}"
    checksum = asset.get("digest")
    if (asset.get("browser_download_url") != expected_url or not isinstance(checksum, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", checksum)):
        raise MigrationError("Latest CLI asset URL/checksum is not an authoritative install contract.")
    return {"repository": REPOSITORY, "tag": release["tag_name"], "version": version,
            "wheelName": name, "wheelUrl": expected_url, "wheelSha256": checksum.removeprefix("sha256:")}


def require_current_cli(version, release):
    if version != release["version"]:
        raise MigrationError(
            f"Installed CLI is not the latest official release ({release['version']}). "
            "Obtain approval to install its verified published wheel, then recollect capabilities.")


def verify_installed_release(package, release):
    """Compare installed Python files against the verified published wheel, not a checkout."""
    package = safe_path(package)
    wheel = safe_path(package.parent / release["wheelName"])
    if (not wheel.is_file() or wheel.stat().st_size > 32 * 1024 * 1024
            or hashlib.sha256(wheel.read_bytes()).hexdigest() != release["wheelSha256"]):
        raise MigrationError("Cannot establish official installed-wheel provenance; reinstall the verified latest release.")
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = [name for name in archive.namelist()
                     if name.startswith("azext_aigateway/") and name.endswith(".py")]
            if not names or len(names) != len(set(names)):
                raise MigrationError("Published CLI wheel has ambiguous Python sources.")
            installed = {file.relative_to(package).as_posix() for file in package.rglob("*.py")}
            if installed != {name.removeprefix("azext_aigateway/") for name in names}:
                raise MigrationError("Installed CLI differs from the official package; local source overlays are not allowed.")
            for name in names:
                file = safe_path(package / name.removeprefix("azext_aigateway/"))
                if file.read_bytes() != archive.read(name):
                    raise MigrationError("Installed CLI was locally modified; reinstall the official current package.")
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise MigrationError("Cannot verify the installed released CLI artifact.") from exc
    return release["wheelSha256"]
