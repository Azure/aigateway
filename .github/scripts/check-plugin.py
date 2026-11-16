#!/usr/bin/env python3
"""Check that every agent host can actually load the plugin.

Version 3.1.0 shipped with five of its ten command and skill files unloadable in
GitHub Copilot CLI (issue #49). Nothing was broken about the content: the
frontmatter simply leaned on a lenient YAML parser. ``description`` values
carrying an unquoted ``": "`` abort a strict parse, and an ``argument-hint``
beginning with ``[`` is read as a flow sequence, so the host gets a list where it
wants a string. Claude Code accepted all of it, which is why the break reached a
release unnoticed.

So this script checks the two halves of what a host needs:

* every command and skill the manifests promise parses, and parses to the types a
  loader expects;
* every manifest promises the same thing, because the plugin is published through
  five of them and a version bump that misses one ships a lie.

The guard against parser differences is quoting, not parseability. A quoted
scalar is a string under every YAML implementation regardless of what it
contains, so quoting is what gets enforced here; the strict parse layered on top
is the second opinion.

PyYAML gives that second opinion when it is installed and is skipped when it is
not, matching how ``migrate-apim validate`` treats ``jsonschema``. The quoting
rules alone are enough to catch everything issue #49 reported, so the script is
worth running either way.

Run it from anywhere::

    python3 .github/scripts/check-plugin.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # optional, see module docstring
    yaml = None

REPO = Path(__file__).resolve().parents[2]

# Every manifest that publishes this plugin. Each entry is the file and the
# dotted path to its version, since marketplace.json nests its own.
MANIFESTS = {
    ".claude-plugin/plugin.json": "version",
    ".claude-plugin/marketplace.json": "plugins.0.version",
    ".cursor-plugin/plugin.json": "version",
    ".github/plugin/plugin.json": "version",
    "gemini-extension.json": "version",
}

# The manifests that serve the markdown surface. They must agree with each other
# exactly: these are the same files handed to different hosts.
MARKDOWN_MANIFESTS = [
    ".claude-plugin/plugin.json",
    ".cursor-plugin/plugin.json",
    ".github/plugin/plugin.json",
]

# Frontmatter values that must be quoted. These are the ones that carry prose or
# punctuation, so they are the ones a plain scalar silently changes the type of.
MUST_QUOTE = ("description", "argument-hint", "version")

REQUIRED_KEYS = {"command": ("description",), "skill": ("name", "description")}

failures: list[str] = []


def fail(where: str, message: str) -> None:
    failures.append(f"{where}: {message}")


def dotted(data: object, path: str) -> object:
    """Resolve 'plugins.0.version' against parsed JSON."""
    for part in path.split("."):
        if isinstance(data, list):
            data = data[int(part)]
        elif isinstance(data, dict):
            data = data.get(part)
        else:
            return None
    return data


def split_frontmatter(text: str) -> list[str] | None:
    """Return the frontmatter lines, or None when the block is missing."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[4:end].split("\n")


def quoted_value(raw: str) -> bool:
    """True when the value is a quoted scalar that closes cleanly.

    Checked on the raw source rather than on parsed output: the point is that the
    file does not depend on how forgiving the reader is.
    """
    raw = raw.strip()
    if len(raw) < 2 or raw[0] not in "\"'" or raw[-1] != raw[0]:
        return False
    body = raw[1:-1]
    if raw[0] == '"':
        # An unescaped double quote would close the scalar early.
        return not re.search(r'(?<!\\)"', body)
    return "'" not in body.replace("''", "")


def check_markdown(rel: str, kind: str) -> None:
    path = REPO / rel
    if not path.is_file():
        fail(rel, "listed in a manifest but missing from disk")
        return

    text = path.read_text(encoding="utf-8")
    lines = split_frontmatter(text)
    if lines is None:
        fail(rel, "no '---' frontmatter block")
        return

    seen: dict[str, str] = {}
    for n, line in enumerate(lines, start=2):  # line 1 is the opening '---'
        if not line.strip() or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z][\w-]*):(.*)$", line)
        if not match:
            continue
        key, raw = match.group(1), match.group(2).strip()
        seen[key] = raw
        if key in MUST_QUOTE and not quoted_value(raw):
            fail(f"{rel}:{n}", f"{key} must be wrapped in quotes, got {raw!r}")

    for key in REQUIRED_KEYS[kind]:
        if key not in seen:
            fail(rel, f"missing required key '{key}'")

    if kind == "skill":
        expected = path.parent.name
        if seen.get("name", "").strip("\"'") != expected:
            fail(rel, f"name must match its directory '{expected}'")

    if yaml is None:
        return

    try:
        data = yaml.safe_load("\n".join(lines))
    except yaml.YAMLError as exc:
        fail(rel, f"strict YAML parse failed: {str(exc).splitlines()[0]}")
        return
    if not isinstance(data, dict):
        fail(rel, "frontmatter is not a mapping")
        return
    for key in MUST_QUOTE + ("name",):
        if key in data and not isinstance(data[key], str):
            got = type(data[key]).__name__
            fail(rel, f"{key} parses as {got}, not str: {data[key]!r}")


def main() -> int:
    manifests: dict[str, dict] = {}
    for rel in MANIFESTS:
        path = REPO / rel
        if not path.is_file():
            fail(rel, "manifest missing")
            continue
        try:
            manifests[rel] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(rel, f"invalid JSON: {exc}")

    # One version across every manifest. A bump that misses one publishes a
    # version that does not match what is in the package.
    versions = {
        rel: dotted(manifests[rel], key)
        for rel, key in MANIFESTS.items()
        if rel in manifests
    }
    if len(set(versions.values())) > 1:
        listed = ", ".join(f"{rel}={ver!r}" for rel, ver in sorted(versions.items()))
        fail("manifests", f"versions disagree: {listed}")

    # The markdown hosts must be offered an identical plugin.
    for field in ("commands", "skills"):
        listings = {
            rel: tuple(manifests[rel].get(field, []))
            for rel in MARKDOWN_MANIFESTS
            if rel in manifests
        }
        if len(set(listings.values())) > 1:
            fail("manifests", f"{field} lists differ across {', '.join(listings)}")

    # Everything promised must exist, including the Gemini .toml surface.
    for rel, data in manifests.items():
        for entry in data.get("commands", []) + data.get("skills", []):
            target = REPO / entry.lstrip("./")
            if not target.exists():
                fail(rel, f"lists '{entry}', which does not exist")

    base = manifests.get(".claude-plugin/plugin.json", {})
    for entry in base.get("commands", []):
        check_markdown(entry.lstrip("./"), "command")
    for entry in base.get("skills", []):
        check_markdown(f"{entry.strip('./')}/SKILL.md", "skill")

    strict = "with" if yaml else "without"
    checked = len(base.get("commands", [])) + len(base.get("skills", []))
    if failures:
        print(f"Plugin check FAILED ({len(failures)} problem(s)):\n")
        for line in failures:
            print(f"  {line}")
        print(f"\nChecked {checked} file(s) and {len(MANIFESTS)} manifest(s), {strict} PyYAML.")
        return 1

    print(f"Plugin OK: {checked} file(s) and {len(MANIFESTS)} manifest(s) checked, {strict} PyYAML.")
    if yaml is None:
        print("Install PyYAML to add the strict-parse check: pip install pyyaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
