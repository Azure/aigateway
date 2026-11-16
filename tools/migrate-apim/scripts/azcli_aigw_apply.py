#!/usr/bin/env python3
"""Adopt one `az aigateway` release as the one the capability catalog describes.

The catalog is a claim about a single CLI release, and the claim is spread over
more than one place: the catalog filename, the `cliEvidence` block inside it,
the surface snapshot beside it, and `targetCapabilities` in `rules.json`. Moving
to a new release means changing all of them to agree, which is exactly the kind
of repetitive edit that goes wrong quietly -- a digest updated but a filename
left behind still compiles, and then the snapshot is a record of a wheel nobody
pinned.

So this script does the whole move or none of it:

    python scripts/azcli_aigw_apply.py --version 1.0.0b33

It downloads the released wheel, records its digest, installs it into a
throwaway extension directory, re-exports the surface through
`azcli_aigw_export.py`, renames the catalog, rewrites `cliEvidence`, repoints
`rules.json`, and removes the snapshot of the release being left behind.

Two things it deliberately will not do.

It does not write `surfaceDelta`. That field says what changed between the old
release and the new one in terms a reader can act on, and a diff of two option
lists is not that. It is blanked and reported, so the move is not finished until
a human writes it.

It does not decide the move is correct. `migrate-apim compile` does, offline,
and the script runs it at the end: a catalog that claims a command the new wheel
does not have fails there, which is the whole point of adopting a release
deliberately rather than floating to latest.

Needs an Azure CLI on PATH, because the surface can only be read from a real
installed extension. Without one, pass `--surface` a snapshot exported
elsewhere, or run with `--dry-run` to see what would change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPABILITIES = ROOT / "capabilities"
EXPORTER = ROOT / "scripts" / "azcli_aigw_export.py"
RELEASE_URL = "https://github.com/Azure/aigateway/releases/download/cli-v{v}/aigateway-{v}-py3-none-any.whl"
REPO_BLOB = "https://github.com/Azure/aigateway/blob/{rev}/cli/{page}"


class Abort(RuntimeError):
    """Something the operator has to resolve; printed without a traceback."""


def sole_catalog() -> Path:
    found = sorted(CAPABILITIES.glob("aigateway-*.json"))
    if len(found) != 1:
        raise Abort(
            f"expected one aigateway-*.json in {CAPABILITIES}, found "
            f"{[p.name for p in found]}"
        )
    return found[0]


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def resolve_revision(version: str, given: str | None) -> str:
    """The commit the release was cut from, for the doc links in cliEvidence.

    Taken from the release tag rather than from HEAD: the links are supposed to
    point at the docs as they stood for that release, and HEAD has usually moved
    on by the time anyone adopts it.
    """
    if given:
        return given
    for ref in (f"cli-v{version}", f"refs/tags/cli-v{version}"):
        if revision := git("rev-list", "-n", "1", ref):
            return revision
    raise Abort(
        f"no tag cli-v{version} in this clone, so the docs revision cannot be "
        f"resolved. Fetch tags, or pass --revision <sha>."
    )


def fetch_wheel(version: str, url: str | None, into: Path) -> Path:
    url = url or RELEASE_URL.format(v=version)
    target = into / f"aigateway-{version}-py3-none-any.whl"
    print(f"  fetching {url}")
    try:
        with urllib.request.urlopen(url) as response, target.open("wb") as out:
            shutil.copyfileobj(response, out)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise Abort(
                f"no published wheel at {url}. {version} is not a released "
                f"version: tag and publish it, or adopt one that exists."
            ) from exc
        raise Abort(f"could not fetch {url}: {exc}") from exc
    return target


def digest(wheel: Path) -> str:
    sha = hashlib.sha256()
    with wheel.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def export_surface(wheel: Path, out: Path, workdir: Path) -> None:
    """Install into a directory of its own and read the surface back out.

    Isolated so that adopting a release never disturbs, or depends on, whatever
    extensions the operator already has installed.
    """
    if not shutil.which("az"):
        raise Abort(
            "no Azure CLI on PATH, and the surface can only be read from a real "
            "installed extension. Install it, or pass --surface a snapshot "
            "exported on a machine that has one."
        )
    env = {
        **os.environ,
        "AZURE_EXTENSION_DIR": str(workdir / "ext"),
        "AZURE_CONFIG_DIR": str(workdir / "cfg"),
    }
    print("  installing the extension in isolation")
    subprocess.run(
        ["az", "extension", "add", "--source", str(wheel), "--yes"],
        env=env, check=True, capture_output=True, text=True,
    )
    print("  exporting the command surface")
    subprocess.run(
        [sys.executable, str(EXPORTER), "--wheel", str(wheel), "--out", str(out)],
        cwd=ROOT, env=env, check=True,
    )


def rewrite_catalog(catalog: Path, version: str, sha: str, revision: str) -> dict:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    evidence = data["cliEvidence"]
    previous = evidence.get("documentedVersion", "?")
    evidence["revision"] = revision
    evidence["documentedVersion"] = version
    evidence["wheelSha256"] = sha
    evidence["releaseNotes"] = f"https://github.com/Azure/aigateway/releases/tag/cli-v{version}"
    evidence["quickstart"] = REPO_BLOB.format(rev=revision, page="README.md")
    evidence["commandReference"] = REPO_BLOB.format(rev=revision, page="command-reference.md")
    # Prose about what moved between two releases, which only a reader of both
    # can write. Left empty on purpose rather than carried over: a stale delta
    # describing the previous move reads as though this one was reviewed.
    evidence["surfaceDelta"] = ""
    catalog.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"previous": previous}


def repoint_rules(version: str) -> None:
    rules = CAPABILITIES / "rules.json"
    data = json.loads(rules.read_text(encoding="utf-8"))
    data["targetCapabilities"] = f"aigateway-{version}"
    rules.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="CLI release to adopt, e.g. 1.0.0b33")
    parser.add_argument("--wheel", type=Path, help="Use this wheel instead of downloading one")
    parser.add_argument("--wheel-url", help="Download from here instead of the release asset")
    parser.add_argument("--surface", type=Path, help="Use this exported snapshot instead of exporting")
    parser.add_argument("--revision", help="Docs revision; defaults to the cli-v<version> tag")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change, write nothing")
    args = parser.parse_args(argv)

    version = args.version.removeprefix("cli-v")
    catalog = sole_catalog()
    current = json.loads(catalog.read_text(encoding="utf-8"))["cliEvidence"]["documentedVersion"]
    if current == version and not args.dry_run:
        raise Abort(f"the catalog already documents {version}; nothing to adopt.")

    revision = resolve_revision(version, args.revision)
    print(f"Adopting {current} -> {version} (docs at {revision[:12]})")

    if args.dry_run:
        print("  would rename  " + f"{catalog.name} -> aigateway-{version}.json")
        print("  would write   " + f"capabilities/cli-surface-{version}.json")
        print("  would repoint rules.json targetCapabilities")
        print("  would blank   cliEvidence.surfaceDelta, for a human to write")
        return 0

    with tempfile.TemporaryDirectory(prefix="aigw-adopt-") as tmp:
        workdir = Path(tmp)
        snapshot = CAPABILITIES / f"cli-surface-{version}.json"
        if args.surface:
            sha = json.loads(args.surface.read_text(encoding="utf-8"))["wheelSha256"]
            shutil.copyfile(args.surface, snapshot)
        else:
            wheel = args.wheel or fetch_wheel(version, args.wheel_url, workdir)
            sha = digest(wheel)
            export_surface(wheel, snapshot, workdir)

    moved = rewrite_catalog(catalog, version, sha, revision)
    adopted = catalog.with_name(f"aigateway-{version}.json")
    if adopted != catalog:
        catalog.rename(adopted)
    repoint_rules(version)
    stale = CAPABILITIES / f"cli-surface-{moved['previous']}.json"
    if stale.exists() and stale != snapshot:
        stale.unlink()

    print(f"  wrote {adopted.name} and {snapshot.name}")
    print("\nChecking the catalog against the release it now claims:")
    checked = subprocess.run(
        [sys.executable, "-m", "migrate_apim", "compile"],
        cwd=ROOT, check=False,
    )
    print(
        "\nStill to do by hand: cliEvidence.surfaceDelta is empty. Say what this "
        f"release changes against {moved['previous']}, in terms a reader can act on."
    )
    return checked.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
