"""What the target can actually do, and how APIM shapes land on it.

Two data files, loaded together:

* ``capabilities/aigateway-<cli>.json`` — a curated table of `az aigateway`
  operations pinned to a CLI revision. Declares what *should* exist.
* ``capabilities/rules.json`` — source shape to target capability, with the
  verdict and the plan-item kind to raise when the mapping is not direct.

The declared table is paired with a runtime probe of the installed extension, so
a capability the docs promise but the installed CLI does not expose is reported
``unavailable`` rather than silently planned against. The probe is injectable:
tests pass their own, and never shell out.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

CAPABILITIES_DIR = Path(__file__).resolve().parent.parent / "capabilities"
DEFAULT_CATALOG = "aigateway-1.0.0b26.json"

# A probe maps an `az aigateway` command path to the option names the installed
# extension exposes for it, or None when the command is absent.
Probe = Callable[[list[str]], "set[str] | None"]

# Whether the `az aigateway` extension is installed at all. A per-command probe
# cannot tell "this command is missing" from "nothing is installed"; this can.
Presence = Callable[[], bool]


class CapabilityError(RuntimeError):
    pass


@dataclass
class Capability:
    id: str
    command: list[str]
    read: list[str]
    kind: str
    options: list[str]
    required: list[str]
    approval_class: str
    limitations: list[str]
    support: str = "declared"  # declared | conditional | unavailable
    missing_options: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.support in {"declared", "conditional"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command,
            "read": self.read,
            "kind": self.kind,
            "required": self.required,
            "approvalClass": self.approval_class,
            "limitations": self.limitations,
            "support": self.support,
            "missingOptions": self.missing_options,
        }


class CapabilityMap:
    """The target's capability table plus the APIM mapping rules."""

    def __init__(self, catalog: dict[str, Any], rules: dict[str, Any]) -> None:
        self.catalog = catalog
        self.rules = rules
        self.capabilities: dict[str, Capability] = {}
        for raw in catalog.get("capabilities", []):
            self.capabilities[raw["id"]] = Capability(
                id=raw["id"],
                command=list(raw.get("command") or []),
                read=list(raw.get("read") or []),
                kind=raw.get("kind") or "",
                options=list(raw.get("options") or []),
                required=list(raw.get("required") or []),
                approval_class=raw.get("approvalClass") or "consequential",
                limitations=list(raw.get("limitations") or []),
            )
        self.unsupported: list[str] = list(catalog.get("unsupported") or [])
        self.probed = False

    # ------------------------------------------------------------- loading

    @classmethod
    def load(
        cls,
        *,
        catalog_path: Path | None = None,
        rules_path: Path | None = None,
    ) -> "CapabilityMap":
        catalog_path = catalog_path or CAPABILITIES_DIR / DEFAULT_CATALOG
        rules_path = rules_path or CAPABILITIES_DIR / "rules.json"
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            rules = json.loads(rules_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CapabilityError(f"capability data unavailable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CapabilityError(f"capability data is not valid JSON: {exc}") from exc
        return cls(catalog, rules)

    @property
    def cli_version(self) -> str | None:
        return (self.catalog.get("cliEvidence") or {}).get("documentedVersion")

    # -------------------------------------------------------------- probe

    def probe(self, probe: Probe | None = None, *, available: Presence | None = None
              ) -> "CapabilityMap":
        """Reconcile the declared table against the installed extension.

        A command the catalog declares but the CLI does not expose becomes
        ``unavailable``; one exposed without a required option is also
        ``unavailable``, naming the option. Without a probe the table stays
        ``declared`` and nothing is claimed about the local install.

        A probe can only speak for an extension that is *there*. When
        ``az aigateway`` is absent altogether, every command reads as missing,
        which would demote the whole catalog to ``unavailable`` and turn native
        mappings into blocking losses. That is an unknown, not an absence, so it
        raises instead. Supplying ``probe`` yourself asserts the presence
        question is already answered; pass ``available`` to override either way.
        """
        if available is None:
            available = (lambda: True) if probe is not None else az_extension_present
        if not available():
            raise CapabilityError(
                "the 'aigateway' az extension is not installed, so the installed CLI cannot be "
                "probed. Install it, or plan without --probe-cli to use the declared table."
            )
        probe = probe or az_option_probe
        for capability in self.capabilities.values():
            options = probe(capability.command)
            if options is None:
                capability.support = "unavailable"
                capability.missing_options = []
                continue
            missing = [name for name in capability.required if name not in options]
            capability.missing_options = missing
            capability.support = "unavailable" if missing else "conditional"
        self.probed = True
        return self

    # --------------------------------------------------------------- rules

    def capability(self, capability_id: str | None) -> Capability | None:
        return self.capabilities.get(capability_id) if capability_id else None

    def asset_rules(self) -> list[dict[str, Any]]:
        return list(self.rules.get("assets") or [])

    def structural_rules(self) -> list[dict[str, Any]]:
        return list(self.rules.get("structural") or [])

    def policy_rule(self, element_name: str, *, family: str = "", has_expression: bool = False
                    ) -> dict[str, Any] | None:
        """The rule governing one policy element.

        Element-specific rules win. An expression does not by itself demote a
        policy that has a real target: a token limit whose ``counter-key`` is
        ``@(context.Subscription.Id)`` still maps to ``tokenLimit`` -- only the
        partitioning needs choosing, which the rule expresses through
        ``partialWhen``. The expression rule is the fallback for elements with no
        mapping of their own, where arbitrary C# genuinely has no target.
        """
        rules = self.rules.get("policies") or []
        for rule in rules:
            names = (rule.get("match") or {}).get("element")
            if names and element_name in names:
                return rule
        for rule in rules:
            match = rule.get("match") or {}
            if match.get("family") and match["family"] == family:
                return rule
        if has_expression:
            for rule in rules:
                if (rule.get("match") or {}).get("hasExpression"):
                    return rule
        return None

    def publishable_routes(self) -> list[str]:
        return list(self.rules.get("publishableRoutes") or [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog": Path(DEFAULT_CATALOG).stem,
            "cliVersion": self.cli_version,
            "probed": self.probed,
            "capabilities": {cid: cap.support for cid, cap in sorted(self.capabilities.items())},
            "unsupported": self.unsupported,
        }


# ---------------------------------------------------------------- probing


def az_extension_present(*, timeout: int = 30) -> bool:
    """Whether `az aigateway` resolves at all.

    Asks the one question the per-command probe cannot: an uninstalled extension
    makes every command look absent, which is an unknown about the local CLI
    rather than evidence the target lacks the capability.
    """
    try:
        proc = subprocess.run(
            ["az", "aigateway", "--help"], capture_output=True, text=True, timeout=timeout
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):  # pragma: no cover
        return False
    return proc.returncode == 0


def az_option_probe(command: Iterable[str], *, timeout: int = 30) -> set[str] | None:
    """Ask the installed extension which options a command exposes."""
    argv = ["az", "aigateway", *command, "--help"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):  # pragma: no cover
        return None
    if proc.returncode != 0:
        return None
    options: set[str] = set()
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            for token in stripped.split():
                if token.startswith("--"):
                    options.add(token.lstrip("-").rstrip(":,"))
    return options
