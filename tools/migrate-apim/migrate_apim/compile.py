"""Check that a capability catalog and its rules are executable.

The catalog is a claim about one `az aigateway` release: these commands exist,
they take these options. The rules are a claim about the planner: these shapes
map to those capabilities. Both claims used to be unverifiable, and both were
wrong -- the catalog declared `az aigateway mcp import`, which exists in no
release, and `model-provider import --foundry`, where the flag is
`--foundry-resource-id`; the rules carried eight entries no selection site
could ever choose, five of them matching on keys no collector emits.

Neither defect could fail a test. The suite injects a probe, so a fabricated
command answers whatever the fake says, and a rule nobody selects is a rule
nobody notices.

This module decides both questions without an Azure CLI and without a network,
by compiling the two data files against a *snapshot* of a real CLI release
(`capabilities/cli-surface-<version>.json`, written by
`scripts/export_cli_surface.py`). The snapshot carries the wheel digest, and the
catalog carries the same digest in `cliEvidence`, so a snapshot cannot be
silently paired with a release it did not come from. Offline here, authoritative
there, and the digest is the join.

Diagnostics accumulate rather than raising, so one run reports everything wrong
instead of the first thing wrong.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import dispatch
from .capability import CAPABILITIES_DIR, DEFAULT_CATALOG

# Importing these registers every selection site in dispatch.REGISTRY. The
# import is the point: the contract checked below is the one the planner runs.
from . import plan as _plan  # noqa: F401  (imported for its selector declarations)

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    check: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity}: [{self.check}] {self.message}"


class Compilation:
    """The diagnostics from one compile, and whether it passed."""

    def __init__(self) -> None:
        self.diagnostics: list[Diagnostic] = []

    def error(self, check: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(ERROR, check, message))

    def warn(self, check: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(WARNING, check, message))

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == WARNING]

    def ok(self, *, strict: bool = False) -> bool:
        return not self.errors and not (strict and self.warnings)


# ----------------------------------------------------------- the catalog

def check_capabilities(catalog: dict[str, Any], surface: dict[str, Any], out: Compilation) -> None:
    """Every declared command and option has to exist in the snapshot."""
    commands = surface.get("commands") or {}
    for capability in catalog.get("capabilities") or []:
        cid = capability.get("id", "<unnamed>")
        for field in ("command", "read"):
            path = " ".join(capability.get(field) or [])
            if not path:
                continue
            if path not in commands:
                out.error(
                    "command-exists",
                    f"{cid}: `az aigateway {path}` ({field}) is not in the "
                    f"{surface.get('extensionVersion', '?')} surface",
                )
        path = " ".join(capability.get("command") or [])
        available = set((commands.get(path) or {}).get("options") or [])
        if path not in commands:
            continue
        for option in capability.get("required") or []:
            if option not in available:
                out.error(
                    "required-option-exists",
                    f"{cid}: `az aigateway {path}` exposes no --{option}, "
                    f"which the catalog marks required",
                )
        for option in capability.get("options") or []:
            if option not in available:
                out.error(
                    "option-exists",
                    f"{cid}: `az aigateway {path}` exposes no --{option}",
                )
        missing = set(capability.get("required") or []) - set(capability.get("options") or [])
        if missing:
            out.error(
                "required-subset-of-options",
                f"{cid}: required {sorted(missing)} not listed in its options",
            )


# -------------------------------------------------------------- the pins

_PIN = re.compile(r"1\.0\.0b\d+")


def check_pins(
    catalog: dict[str, Any],
    catalog_path: Path,
    rules: dict[str, Any],
    surface: dict[str, Any],
    out: Compilation,
    *,
    cli_dir: Path | None = None,
) -> None:
    """One release, named the same way everywhere it is named.

    The version and digest are repeated across the catalog, the rules, the
    snapshot and the installer scripts. Nothing used to tie them together, and
    they drifted: a catalog called `aigateway-1.0.0b26.json` whose own evidence
    said `1.0.0b30`, and a `DEFAULT_CATALOG` naming a file deleted two releases
    earlier, which stopped `plan` dead.
    """
    evidence = catalog.get("cliEvidence") or {}
    version = evidence.get("documentedVersion")
    digest = evidence.get("wheelSha256")

    if surface.get("wheelSha256") != digest:
        out.error(
            "snapshot-matches-catalog",
            f"the surface snapshot is for wheel {surface.get('wheelSha256', '?')[:16]}… but the "
            f"catalog documents {str(digest)[:16]}…; the snapshot is not of this release",
        )
    if surface.get("extensionVersion") != version:
        out.error(
            "snapshot-matches-catalog",
            f"the surface snapshot is version {surface.get('extensionVersion')!r}, "
            f"the catalog documents {version!r}",
        )

    expected_stem = f"aigateway-{version}"
    if catalog_path.stem != expected_stem:
        out.error(
            "catalog-filename",
            f"the catalog is {catalog_path.name} but documents {version}; "
            f"it should be {expected_stem}.json",
        )
    if rules.get("targetCapabilities") != catalog_path.stem:
        out.error(
            "rules-target-catalog",
            f"rules.json targets {rules.get('targetCapabilities')!r}, "
            f"the catalog loaded is {catalog_path.stem!r}",
        )

    default = CAPABILITIES_DIR / DEFAULT_CATALOG
    if not default.is_file():
        out.error(
            "default-catalog-resolves",
            f"DEFAULT_CATALOG is {DEFAULT_CATALOG!r}, which is not in {CAPABILITIES_DIR}. "
            f"Every entry point that does not pass --capabilities falls back to it, so this "
            f"stops `plan` outright. Present: "
            f"{sorted(p.name for p in CAPABILITIES_DIR.iterdir())}",
        )

    if cli_dir is None or not cli_dir.is_dir():
        return
    # The installer scripts and their test carry the same pin. They are read for
    # those two constants only, not linted as prose.
    #
    # Only the installers are held to "no other version appears". The test names
    # an older release on purpose, as the upgrade-from fixture, and asserts the
    # installers do *not* mention it -- so a stale-version sweep there would
    # fail on the very line that prevents the staleness.
    for name, forbid_other_versions in (
        ("install.sh", True), ("install.ps1", True), ("tests/test_installers.py", False),
    ):
        path = cli_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if digest and digest not in text:
            out.error("installer-pin", f"cli/{name} does not carry the catalog's wheel digest")
        if version and version not in text:
            out.error("installer-pin", f"cli/{name} does not name {version}")
        if not forbid_other_versions:
            continue
        stale = set(_PIN.findall(text)) - {version}
        if stale:
            out.error(
                "installer-pin",
                f"cli/{name} names {sorted(stale)} while the catalog documents {version}",
            )


# --------------------------------------------------------------- the rules

# Fields a rule may carry that no code reads. Reported as warnings: some are
# deliberate notes to a human reader, and the compiler cannot tell those from
# an option somebody expected to take effect.
_UNREAD_RULE_FIELDS = (
    "constraints", "defaultFrom", "blockingWhen", "dependsOnBackendRole", "priority",
    "autoResolvable", "toolDiscoveryGuidance",
)

# Sections whose rules are chosen through a registered selector.
_SELECTED_SECTIONS = ("assets", "structural", "policies")


def check_rules(catalog: dict[str, Any], rules: dict[str, Any], out: Compilation) -> None:
    capabilities = {c.get("id") for c in catalog.get("capabilities") or []}

    for section in _SELECTED_SECTIONS:
        for rule in rules.get(section) or []:
            match = rule.get("match") or {}
            label = f"{section} {json.dumps(match, sort_keys=True)}"
            governing = dispatch.governing(rule, section)

            if not governing:
                _explain_unreachable(rule, section, label, out)

            capability_id = rule.get("capabilityId")
            if capability_id and capability_id not in capabilities:
                out.error(
                    "rule-capability-exists",
                    f"{label}: names capability {capability_id!r}, which the catalog does not declare",
                )

            if rule.get("verdict") == "partial":
                options = _option_values(rule.get("options") or [])
                if not options:
                    out.error("partial-needs-options",
                              f"{label}: verdict is partial but it offers no options")
                elif rule.get("proposal") and rule["proposal"] not in options:
                    out.error(
                        "proposal-is-an-option",
                        f"{label}: proposes {rule['proposal']!r}, which is not among {options}",
                    )

            for field in _UNREAD_RULE_FIELDS:
                if field in rule:
                    out.warn("rule-field-unread",
                             f"{label}: carries {field!r}, which no code reads")

    _check_uniqueness(rules, out)
    _check_required_fields(rules, out)


def _option_values(options: list[Any]) -> list[str]:
    """The choices an options list offers, in either of the two shapes it uses.

    A bare string is the choice; an object carries the choice in `value` with
    what picking it costs alongside.
    """
    return [o["value"] if isinstance(o, dict) else o for o in options if o]


def _explain_unreachable(rule: dict[str, Any], section: str, label: str, out: Compilation) -> None:
    """Say *why* nothing can choose this rule, not merely that nothing can.

    "No site selects this" is true of a bogus match value and of an invented
    match key alike, and the fix is different. A rule whose keys a site does
    read, but whose value it never compares against, is a vocabulary problem;
    a rule naming a key no site reads at all is a different mistake.
    """
    match = rule.get("match") or {}
    sites = [s for s in dispatch.REGISTRY if s.section == section]
    key_compatible = [s for s in sites if not set(match) - set(s.keys)]

    if key_compatible:
        for selector in key_compatible:
            for key, permitted in selector.values.items():
                value = match.get(key)
                if key in match and permitted and value not in permitted:
                    out.error(
                        "match-value-known",
                        f"{label}: {selector.site} never compares {key} against {value!r}; "
                        f"it only ever sees {sorted(permitted)}",
                    )
        return

    readable = sorted({key for selector in sites for key in selector.keys})
    unknown = sorted(set(match) - set(readable))
    detail = (
        f"it matches on {unknown}, which no {section} selection site reads"
        if unknown
        else f"no site reads this combination of keys {sorted(match)}"
    )
    out.error(
        "rule-reachable",
        f"{label}: no selection site can ever choose this rule -- {detail}. "
        f"Sites read {readable}; they are {[s.site for s in sites]}",
    )


def _check_uniqueness(rules: dict[str, Any], out: Compilation) -> None:
    """Selection is first-match or last-write; either way a tie is a silent bug.

    Ties are judged per selection site, over exactly the keys that site reads:
    two rules are indistinguishable when the site cannot tell them apart, not
    when they happen to look alike.
    """
    for section in ("assets", "structural"):
        for selector in [s for s in dispatch.REGISTRY if s.section == section]:
            seen: set[tuple] = set()
            for rule in rules.get(section) or []:
                if not selector.governs(rule):
                    continue
                match = rule.get("match") or {}
                key = tuple(match.get(name) for name in selector.keys)
                if key in seen:
                    out.error(
                        "rule-unique",
                        f"{section}: {selector.site} cannot tell two rules apart on "
                        f"{dict(zip(selector.keys, key))}; only one of them is ever used",
                    )
                seen.add(key)

    elements: dict[str, int] = {}
    for rule in rules.get("policies") or []:
        for element in (rule.get("match") or {}).get("element") or []:
            elements[element] = elements.get(element, 0) + 1
    for element, count in sorted(elements.items()):
        if count > 1:
            out.error(
                "rule-unique",
                f"policies: element {element!r} appears in {count} rules; only the first is used",
            )


def _check_required_fields(rules: dict[str, Any], out: Compilation) -> None:
    """`verdict` is read with a bare subscript, so a rule without one raises."""
    for section in ("assets", "policies"):
        for rule in rules.get(section) or []:
            if "verdict" not in rule:
                match = json.dumps(rule.get("match") or {}, sort_keys=True)
                out.error(
                    "rule-has-verdict",
                    f"{section} {match}: has no verdict, which is read unguarded",
                )
    for rule in rules.get("structural") or []:
        if "verdict" not in rule and rule.get("itemKind"):
            match = json.dumps(rule.get("match") or {}, sort_keys=True)
            out.warn(
                "rule-has-verdict",
                f"structural {match}: has no verdict; it survives only because the one site "
                f"reading it takes itemKind, proposal and rationale alone",
            )


# ------------------------------------------------------------- the shapes

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"


def check_schemas(catalog: dict[str, Any], rules: dict[str, Any], out: Compilation) -> None:
    """Both data files against their JSON Schema.

    They had none until now, which is how a rule came to match on a key that
    existed nowhere else in the tree. Both schemas close `additionalProperties`,
    so an invented key is rejected at the shape level before anything has to
    reason about whether it could ever be selected.

    Without `jsonschema` installed this degrades to a notice rather than
    passing quietly: a check that cannot run has not succeeded.
    """
    try:
        import jsonschema  # type: ignore
    except ImportError:
        out.warn(
            "schema",
            "jsonschema is not installed, so the catalog and rules were not shape-checked. "
            "Install the 'validate' or 'dev' extra.",
        )
        return

    for document, schema_name, label in (
        (catalog, "capabilities.schema.json", "catalog"),
        (rules, "rules.schema.json", "rules"),
    ):
        try:
            schema = json.loads((SCHEMAS_DIR / schema_name).read_text(encoding="utf-8"))
        except OSError as exc:
            out.error("schema", f"{schema_name} is unavailable: {exc}")
            continue
        validator = jsonschema.Draft202012Validator(schema)
        for error in sorted(validator.iter_errors(document), key=lambda e: list(e.path))[:25]:
            where = "/".join(str(part) for part in error.path) or "<root>"
            out.error("schema", f"{label} {where}: {error.message}")


# ------------------------------------------------------------------ entry

def find_surface(catalog: dict[str, Any], directory: Path | None = None) -> Path:
    """The snapshot for the release a catalog documents."""
    directory = directory or CAPABILITIES_DIR
    version = (catalog.get("cliEvidence") or {}).get("documentedVersion")
    return directory / f"cli-surface-{version}.json"


def compile_contract(
    catalog_path: Path,
    rules_path: Path,
    surface_path: Path,
    *,
    cli_dir: Path | None = None,
) -> Compilation:
    out = Compilation()
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
        rules = json.loads(rules_path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        out.error("load", f"capability data unavailable: {exc}")
        return out
    except json.JSONDecodeError as exc:
        out.error("load", f"capability data is not valid JSON: {exc}")
        return out

    try:
        surface = json.loads(surface_path.read_text(encoding="utf-8-sig"))
    except OSError:
        out.error(
            "load",
            f"no CLI surface snapshot at {surface_path}. Generate one with "
            f"scripts/export_cli_surface.py against the pinned wheel.",
        )
        return out
    except json.JSONDecodeError as exc:
        out.error("load", f"the CLI surface snapshot is not valid JSON: {exc}")
        return out

    check_schemas(catalog, rules, out)
    check_capabilities(catalog, surface, out)
    check_pins(catalog, catalog_path, rules, surface, out, cli_dir=cli_dir)
    check_rules(catalog, rules, out)
    return out
