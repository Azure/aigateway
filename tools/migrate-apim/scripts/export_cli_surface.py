#!/usr/bin/env python3
"""Export the `az aigateway` command surface of one installed extension release.

The capability catalog is a claim about a CLI release. `migrate-apim compile`
checks that claim offline, against the snapshot this script writes; the snapshot
is what ties the claim to a real wheel. Keeping the two apart is deliberate:
the compile step must run on every change without an Azure CLI or a network,
and this step must run against the real thing.

Run it against an extension installed into an isolated extension directory, so
the operator's own install is never touched:

    AZURE_EXTENSION_DIR=/tmp/ext AZURE_CONFIG_DIR=/tmp/azcfg \\
      python scripts/export_cli_surface.py --wheel aigateway-1.0.0b31-py3-none-any.whl \\
      --out capabilities/cli-surface-1.0.0b31.json

The command tree is walked through `--help`, which is the only interface the
Azure CLI offers without importing its internals. Help *text* is a poor source
of truth if read loosely -- `az aigateway model-provider create --help` mentions
"--kind, and --custom or --foundry" in its summary prose, and a parser that
takes any line beginning with `--` reads `foundry.` as an option. So the parser
here is anchored on structure, not on the characters: only lines indented
exactly four spaces inside a section whose heading ends in "Arguments", and only
the declaration half of the line, before the help separator. `--self-test`
pins that behaviour against commands whose real surface is known.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Arguments the Azure CLI adds to every command. They are not part of what the
# extension offers, they move between azure-cli-core releases, and the catalog
# never declares them, so leaving them out keeps the snapshot stable across core
# upgrades -- a snapshot that churns on an unrelated upgrade is one nobody
# trusts enough to regenerate.
GLOBAL_ARGUMENTS = frozenset({
    "acquire-policy-token", "change-reference", "debug", "help", "ids",
    "only-show-errors", "output", "query", "subscription", "verbose",
})

ROOT = "aigateway"

# A command or subgroup entry in a group listing: four spaces, a name, " : ".
_ENTRY = re.compile(r"^ {4}(\S+)\s*:")
# An option declaration: four spaces, then the flags, up to the help separator.
_OPTION_LINE = re.compile(r"^ {4}(--\S.*?)(?:\s{2,}:|\s:\s|$)")
_SECTION = re.compile(r"^(\S.*?):?\s*$")


class ExportError(RuntimeError):
    pass


def _run(argv: list[str]) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        raise ExportError("the az CLI is not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ExportError(f"`{' '.join(argv)}` timed out") from exc
    if proc.returncode != 0:
        raise ExportError(f"`{' '.join(argv)}` failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


def _help(path: list[str]) -> str:
    return _run(["az", ROOT, *path, "--help"])


def _sections(text: str) -> dict[str, list[str]]:
    """Help output split by its column-0 headings.

    Headings are the only reliable landmark: everything else in the body is
    free text that may itself start with a dash.
    """
    sections: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        if line and not line[0].isspace():
            current = _SECTION.match(line).group(1).strip()
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return sections


def _entries(lines: list[str]) -> list[str]:
    return [m.group(1) for line in lines if (m := _ENTRY.match(line))]


def parse_options(help_text: str) -> tuple[list[str], list[str]]:
    """The options a command declares, and which of them the CLI marks required.

    Only "* Arguments" sections are read, so the summary prose above them -- the
    place where flags are *mentioned* rather than declared -- cannot contribute.
    """
    options: set[str] = set()
    required: set[str] = set()
    for heading, lines in _sections(help_text).items():
        if not heading.endswith("Arguments"):
            continue
        for line in lines:
            match = _OPTION_LINE.match(line)
            if not match:
                continue
            declaration = match.group(1)
            names = [
                token.lstrip("-")
                for token in declaration.split()
                if token.startswith("--")
            ]
            names = [name for name in names if name not in GLOBAL_ARGUMENTS]
            options.update(names)
            if "[Required]" in line:
                required.update(names)
    return sorted(options), sorted(required)


def walk(path: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Every leaf command under `az aigateway`, with the options it exposes."""
    path = path or []
    sections = _sections(_help(path))
    surface: dict[str, dict[str, Any]] = {}
    for name in _entries(sections.get("Subgroups", [])):
        surface.update(walk([*path, name]))
    for name in _entries(sections.get("Commands", [])):
        command = [*path, name]
        options, required = parse_options(_help(command))
        surface[" ".join(command)] = {"options": options, "required": required}
    return surface


def installed_version() -> str:
    try:
        return json.loads(_run(["az", ROOT, "version", "-o", "json"]))["extensionVersion"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise ExportError("`az aigateway version` did not report an extensionVersion") from exc


def _digest(wheel: Path) -> str:
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _core_version() -> str:
    try:
        return json.loads(_run(["az", "version", "-o", "json"]))["azure-cli-core"]
    except (ExportError, json.JSONDecodeError, KeyError):
        return "unknown"


def export(wheel_sha256: str) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "kind": "aigatewayCliSurface",
        "extensionVersion": installed_version(),
        "wheelSha256": wheel_sha256,
        "generatedBy": {"method": "help-sections", "azureCliCore": _core_version()},
        "commands": dict(sorted(walk().items())),
    }


# --------------------------------------------------------------- self-test

# Facts about the b31 surface that any correct parser must reproduce. They exist
# to catch a parser that silently loosens -- the prose-scraping failure mode
# reads `foundry.` as an option of `model-provider create`, and a parser that
# over-tightens drops the resource-id arguments entirely.
SELF_TEST = {
    "model-provider import": {
        "present": ["foundry-resource-id", "gateway-name", "name", "provider-name", "resource-group"],
        "absent": ["foundry", "custom", "import-models"],
    },
    "model-provider create": {
        "present": ["kind", "foundry", "foundry-resource-id", "custom", "import-models"],
        "absent": ["foundry.", "sources"],
    },
    "mcp create": {
        "present": ["endpoints", "url", "mcp", "open-api", "transport", "namespace", "versions"],
        "absent": ["credentials)", "sources"],
    },
    "policy set": {
        "present": ["token-limit", "ip-filter-mode"],
        "absent": ["content-"],
    },
}


def self_test() -> list[str]:
    failures = []
    for command, expectations in SELF_TEST.items():
        options, _ = parse_options(_help(command.split()))
        for name in expectations["present"]:
            if name not in options:
                failures.append(f"{command}: expected option --{name}, parser did not find it")
        for name in expectations["absent"]:
            if name in options:
                failures.append(f"{command}: parser invented option --{name}")
    if "mcp import" in walk():
        failures.append("mcp import: the walker found a command that does not exist")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wheel", help="Path to the released wheel, to record its SHA-256")
    parser.add_argument("--wheel-sha256", help="The digest, when the wheel itself is not at hand")
    parser.add_argument("--out", type=Path, help="Where to write the snapshot")
    parser.add_argument("--self-test", action="store_true",
                        help="Check the help parser against known commands and exit")
    args = parser.parse_args(argv)

    if "AZURE_EXTENSION_DIR" not in os.environ:
        print("warning: AZURE_EXTENSION_DIR is unset, so this reads the operator's own "
              "extension install rather than an isolated one", file=sys.stderr)

    try:
        if args.self_test:
            failures = self_test()
            for failure in failures:
                print(f"  {failure}", file=sys.stderr)
            print("help parser self-test: " + ("failed" if failures else "passed"),
                  file=sys.stderr)
            return 1 if failures else 0

        if args.wheel:
            digest = _digest(Path(args.wheel))
        elif args.wheel_sha256:
            digest = args.wheel_sha256
        else:
            parser.error("one of --wheel or --wheel-sha256 is required")
        snapshot = export(digest)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    text = json.dumps(snapshot, indent=2, sort_keys=False) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}: {len(snapshot['commands'])} commands for "
              f"{snapshot['extensionVersion']}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
