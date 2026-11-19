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
`scripts/azcli_aigw_export.py`). The snapshot carries the wheel digest, and the
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
from .capability import (
    CAPABILITIES_DIR,
    DEFAULT_CATALOG,
    POLICY_TERMINAL,
    resolve_policy_rule,
)
from .policy import FAMILIES, family_of

# Importing these registers every selection site in dispatch.REGISTRY. The
# import is the point: the contract checked below is the one the planner runs.
from . import plan as _plan  # noqa: F401  (imported for its selector declarations)

ERROR = "error"
WARNING = "warning"
# Neither a defect nor a risk: something true about the contract that the
# reader may want to act on. A newer release existing does not make the
# catalog wrong about the one it documents, so calling it a warning asked CI
# to report a problem that is not there -- and `--strict` would have failed
# on it. Printed, counted separately, never fatal.
SUGGESTION = "suggestion"


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
        # What each check actually covered. A compile that only speaks up when
        # something is wrong leaves the reader of a green run guessing whether
        # it checked anything at all, or silently skipped the half that
        # mattered -- which is how the catalog shipped a command that existed
        # in no release, through a green suite.
        self.covered: list[str] = []

    def cover(self, what: str) -> None:
        self.covered.append(what)

    def error(self, check: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(ERROR, check, message))

    def warn(self, check: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(WARNING, check, message))

    def suggest(self, check: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(SUGGESTION, check, message))

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == WARNING]

    @property
    def suggestions(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == SUGGESTION]

    def ok(self, *, strict: bool = False) -> bool:
        return not self.errors and not (strict and self.warnings)


# ----------------------------------------------------------- the catalog

# Options every command takes that name *which* resource is being addressed, not
# what to do to it. `apply` supplies them from the plan's target -- see
# `apply.Target.selectors` and the `--gateway-name`/`-n` pairs at each call site
# -- so the catalog has no reason to carry them, and a command requiring one is
# not evidence of anything missing.
IDENTITY_OPTIONS = frozenset({
    "subscription", "resource-group", "gateway-name", "name", "provider-name",
    "model-name", "model-provider", "tool-server-name", "api-key-name",
    "telemetry-exporter-name",
})


def check_capabilities(catalog: dict[str, Any], surface: dict[str, Any], out: Compilation) -> None:
    """Every declared command and option has to exist in the snapshot."""
    commands = surface.get("commands") or {}
    declared = catalog.get("capabilities") or []
    options = sum(len(c.get("options") or []) for c in declared)
    out.cover(
        f"{len(declared)} capabilities and {options} declared options against "
        f"{len(commands)} commands in the {surface.get('extensionVersion', '?')} surface"
    )
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
        # The other direction, and the one the snapshot used to record for
        # nobody: an option the CLI *insists* on. Leave it out of the catalog
        # and the command is built without it and rejected at run time, which
        # is a thing to learn offline rather than mid-migration.
        insisted = set((commands.get(path) or {}).get("required") or [])
        unmet = sorted(insisted - IDENTITY_OPTIONS - set(capability.get("required") or []))
        if unmet:
            out.error(
                "cli-required-option-declared",
                f"{cid}: `az aigateway {path}` requires {['--' + o for o in unmet]}, "
                f"which the catalog does not mark required, so the command is built without it",
            )
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
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)b(\d+)$")


def release_order(version: str) -> tuple[int, ...] | None:
    """A sortable key for `1.0.0b31`, or None if that is not what this is."""
    found = _VERSION.match(version.strip())
    return tuple(int(part) for part in found.groups()) if found else None


def check_release_pin(catalog: dict[str, Any], releases: str, out: Compilation) -> None:
    """Whether the catalog still documents the newest CLI release there is.

    Asked here, offline, against tag names the caller supplies, rather than from
    the CLI's own release pipeline: a gateway release is not this tool's build to
    fail, and the signal that matters -- "the table you are about to edit
    describes an older CLI" -- is most useful to whoever is editing it.

    The cost is that it is only asked when somebody touches this tool. A pin can
    sit stale between visits; what it cannot do is be stale while being worked on.

    `releases` may be one version or every tag there is, whitespace separated.
    Taking the whole list and picking the newest here keeps the answer off git's
    `--sort=v:refname`, which orders `1.0.0b100` against `1.0.0b99` by rules of
    its own that this does not have to depend on.
    """
    documented = (catalog.get("cliEvidence") or {}).get("documentedVersion") or ""
    candidates = [tag.strip().removeprefix("cli-v") for tag in releases.split()]
    candidates = [tag for tag in candidates if tag]
    if not candidates:
        return

    out.cover(f"{documented} against {len(candidates)} published release(s)")

    here = release_order(documented)
    ordered = [(release_order(tag), tag) for tag in candidates]
    comparable = [(order, tag) for order, tag in ordered if order is not None]
    if here is None or not comparable:
        unreadable = documented if here is None else ", ".join(sorted(candidates))
        out.warn(
            "release-pin",
            f"cannot tell whether the catalog is current: {unreadable!r} is not an "
            f"X.Y.ZbN version, so there is nothing to compare {documented!r} against",
        )
        return

    there, newest = max(comparable)
    if there > here:
        # A suggestion, not a warning. Nothing is wrong: the catalog is a claim
        # about one release, verified against that release, and a newer one
        # shipping does not make it false. Reporting it as a warning asked CI
        # to show a problem that is not there, and `--strict` would then have
        # failed on somebody else's release. What it is, is the moment to
        # consider adopting -- said to whoever is already editing the table.
        out.suggest(
            "release-pin",
            f"the catalog documents {documented} but {newest} has been released. "
            f"Adopt it with `python scripts/azcli_aigw_apply.py --version {newest}`, "
            f"which re-exports the surface, re-pins cliEvidence, renames the catalog, "
            f"and repoints rules.json.",
        )
    elif there < here:
        # A legitimate state while a release candidate is being prepared, and
        # worth saying out loud anyway: until the tag exists there is no
        # published wheel to check the snapshot against, so the one claim this
        # whole arrangement rests on is the one claim currently unverifiable.
        out.warn(
            "release-pin",
            f"the catalog documents {documented}, which is newer than {newest}, the newest "
            f"published release. the export job cannot verify the snapshot until that "
            f"release is tagged and its wheel published.",
        )


def check_pins(
    catalog: dict[str, Any],
    catalog_path: Path,
    rules: dict[str, Any],
    surface: dict[str, Any],
    out: Compilation,
) -> None:
    """One release, named the same way everywhere it is named.

    The version and digest are repeated across the catalog, the rules and the
    snapshot. Nothing used to tie them together, and they drifted: a catalog
    called `aigateway-1.0.0b26.json` whose own evidence said `1.0.0b30`, and a
    `DEFAULT_CATALOG` naming a file deleted two releases earlier, which stopped
    `plan` dead.

    `cli/` is not among them. Those installers are the CLI's own artifact and
    move when it releases; holding the catalog to them would make the newest
    release the only one it could pin, so every run would validate against
    latest. The catalog says which release to install, not the other way round.
    """
    evidence = catalog.get("cliEvidence") or {}
    version = evidence.get("documentedVersion")
    digest = evidence.get("wheelSha256")
    out.cover(
        f"{version} and its wheel digest agree across the catalog filename, "
        f"cliEvidence, the snapshot and rules targetCapabilities"
    )

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


# --------------------------------------------------------------- the rules

# Sections whose rules are chosen through a registered selector.
_SELECTED_SECTIONS = ("assets", "structural", "policies")


def check_rules(catalog: dict[str, Any], rules: dict[str, Any], out: Compilation) -> None:
    capabilities = {c.get("id") for c in catalog.get("capabilities") or []}
    counted = sum(len(rules.get(section) or []) for section in _SELECTED_SECTIONS)
    out.cover(
        f"{counted} rules across {', '.join(_SELECTED_SECTIONS)}: each selectable, "
        f"every field read by a site that can select it, none ambiguous"
    )

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

            # Which fields have an effect is the selecting site's answer, not a
            # list kept here: a list kept here is a second declaration, and it
            # drifted. The denylist this replaces named `constraints` and
            # `toolDiscoveryGuidance` and missed `prerequisiteGuide`, the
            # telemetry rule's `options`, and `blocking`/`cannotAccept` -- all
            # equally unread, none of them remembered.
            #
            # Only asked of a rule something can select. For one nothing can,
            # every field is unread by construction, and saying so twenty times
            # buries the reachability error that is the actual problem.
            if governing:
                unread = (
                    set(rule) - dispatch.fields_read(rule, section)
                    - set(dispatch.STRUCTURAL_KEYS)
                )
                for field in sorted(unread):
                    out.warn(
                        "rule-field-unread",
                        f"{label}: carries {field!r}, which no site that can select this "
                        f"rule reads. Sites that can: {[s.site for s in governing]}",
                    )

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


def check_policy_vocabulary(rules: dict[str, Any], out: Compilation) -> None:
    """Every policy element the collector can name must be answered deliberately.

    `policy.FAMILIES` is the vocabulary this tool classifies against: committed
    data, so the question is decidable here, offline, with no APIM to ask. The
    terminal rule answers for anything outside it, which is what keeps an
    unrecognised policy out of silence -- but it would equally answer for an
    element somebody simply never wrote a rule for, and then the safety net
    becomes the mapping. Eleven elements lived there, three of them carrying
    backend credentials.

    So the net is held to its purpose: a known element reaching it is an error,
    and the fix is a rule of its own or a rule for its family.
    """
    policies = rules.get("policies") or []
    out.cover(
        f"{len(FAMILIES)} policy elements the collector classifies: each answered by a "
        f"rule of its own or a family rule, none left to the terminal rule"
    )

    terminal = next((rule for rule in policies if POLICY_TERMINAL.governs(rule)), None)
    if terminal is None:
        out.error(
            "policy-terminal",
            "no rule matches `anyElement`, so an element outside the known vocabulary resolves "
            "to nothing and is dropped where it is classified. Add the terminal rule.",
        )
        return

    unanswered: dict[str, list[str]] = {}
    for name in sorted(FAMILIES):
        rule = resolve_policy_rule(policies, name, family=family_of(name), has_expression=False)
        if rule is terminal:
            unanswered.setdefault(family_of(name), []).append(name)

    for family, names in sorted(unanswered.items()):
        out.error(
            "policy-vocabulary",
            f"family {family!r}: {', '.join(names)} reach the terminal rule, which exists for "
            f"policies this catalog has never heard of. Give the family a rule, or each element "
            f"one of its own.",
        )


def _check_uniqueness(rules: dict[str, Any], out: Compilation) -> None:
    """Selection is first-match or last-write; either way a tie is a silent bug.

    Ties are judged per selection site, over exactly the keys that site reads:
    two rules are indistinguishable when the site cannot tell them apart, not
    when they happen to look alike. Every section is covered, including the
    policy passes keyed on `family` and `hasExpression` -- they were not, and a
    second `family: transform` rule compiled clean while never being reached.
    """
    for section in _SELECTED_SECTIONS:
        for selector in [s for s in dispatch.REGISTRY if s.section == section]:
            seen: set[tuple] = set()
            for rule in rules.get(section) or []:
                if not selector.governs(rule):
                    continue
                match = rule.get("match") or {}
                # A match value may itself be a list of alternatives -- a policy
                # rule naming several elements. Each alternative is its own way
                # to reach the rule, so each is its own chance of a tie.
                for key in _match_keys(match, selector.keys):
                    if key in seen:
                        out.error(
                            "rule-unique",
                            f"{section}: {selector.site} cannot tell two rules apart on "
                            f"{dict(zip(selector.keys, key))}; only one of them is ever used",
                        )
                    seen.add(key)


def _match_keys(match: dict[str, Any], keys: tuple[str, ...]) -> list[tuple]:
    """Every distinct way a site keyed on `keys` can arrive at this rule."""
    combinations: list[tuple] = [()]
    for name in keys:
        value = match.get(name)
        alternatives = value if isinstance(value, list) else [value]
        combinations = [(*prefix, alt) for prefix in combinations for alt in alternatives]
    return combinations


def _check_required_fields(rules: dict[str, Any], out: Compilation) -> None:
    """`verdict` decides an item's status, and assets read it with a bare subscript.

    Structural rules used to be exempt, because `plan._structural` hardcoded a
    verdict per branch and never consulted the rule. It consults it now, so the
    exemption is gone and all three sections are held to the same thing.
    """
    for section in _SELECTED_SECTIONS:
        for rule in rules.get(section) or []:
            if "verdict" not in rule:
                match = json.dumps(rule.get("match") or {}, sort_keys=True)
                out.error(
                    "rule-has-verdict",
                    f"{section} {match}: has no verdict, which decides the item's status",
                )


# ------------------------------------------------------------- the shapes

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

# Enough to show the shape of the problem without burying the other checks.
_SCHEMA_ERROR_LIMIT = 25


def check_schemas(catalog: dict[str, Any], rules: dict[str, Any], out: Compilation) -> None:
    """Both data files against their JSON Schema.

    They had none until now, which is how a rule came to match on a key that
    existed nowhere else in the tree. Both schemas close `additionalProperties`,
    so an invented key is rejected at the shape level before anything has to
    reason about whether it could ever be selected.

    Without `jsonschema` installed this degrades to a notice rather than
    passing quietly: a check that cannot run has not succeeded.
    """
    out.cover("catalog and rules against their schemas, unknown keys rejected")
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
        errors = sorted(validator.iter_errors(document), key=lambda e: list(e.path))
        for error in errors[:_SCHEMA_ERROR_LIMIT]:
            where = "/".join(str(part) for part in error.path) or "<root>"
            out.error("schema", f"{label} {where}: {error.message}")
        if len(errors) > _SCHEMA_ERROR_LIMIT:
            # Said rather than left implicit: a reader who fixes every line
            # printed here and expects a clean run should know there is more.
            out.error(
                "schema",
                f"{label}: and {len(errors) - _SCHEMA_ERROR_LIMIT} further schema "
                f"error(s), not shown",
            )


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
    newest_release: str | None = None,
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
            f"scripts/azcli_aigw_export.py against the pinned wheel.",
        )
        return out
    except json.JSONDecodeError as exc:
        out.error("load", f"the CLI surface snapshot is not valid JSON: {exc}")
        return out

    check_schemas(catalog, rules, out)
    check_capabilities(catalog, surface, out)
    check_pins(catalog, catalog_path, rules, surface, out)
    check_rules(catalog, rules, out)
    check_policy_vocabulary(rules, out)
    if newest_release:
        check_release_pin(catalog, newest_release, out)
    return out
