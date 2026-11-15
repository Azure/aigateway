"""Where rule selection happens, declared once so it can be checked.

`rules.json` is only worth maintaining if the planner reads what it says. Three
things can go wrong quietly, and all three had:

* a rule names a `match` key no selector examines, so it is never chosen;
* a rule carries an extra key the selector ignores, so it matches more broadly
  than it reads;
* a rule names a value no asset ever carries, so it matches nothing.

None of those is visible at the call site, because selection used to be an
inline lambda per site. A checker could only find them by declaring the
criteria a second time, somewhere else -- and a second declaration drifts from
the first, which is how the problem started.

So selection goes through `Selector`. It performs the match *and* is the
statement of what the match looks at. `migrate_apim.compile` reads `REGISTRY`,
so the contract it checks is the one the planner actually runs; there is no
second copy to fall out of step.

A selector `governs` a rule when the rule's `match` keys are a subset of the
keys the selector examines, and every value it constrains is one the selector
accepts. Subset rather than equality: a rule may legitimately pin fewer keys.
What it may not do is pin *more*, because the surplus would be silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# Every selection site in the planner, in declaration order. Populated at import
# time by the modules that declare selectors; `compile` imports those modules to
# fill it.
REGISTRY: list["Selector"] = []

Rule = dict[str, Any]


@dataclass(frozen=True)
class Selector:
    """One rule-selection site, and the criteria it dispatches on."""

    section: str
    """Which top-level list of rules.json this reads: assets, structural, policies."""

    keys: tuple[str, ...]
    """The `match` keys this site examines. Anything else on a rule is ignored."""

    values: Mapping[str, tuple[str, ...]]
    """Accepted literals per key. A key absent here, or mapped to (), is unconstrained."""

    site: str
    """Where the selection happens, for diagnostics: "plan._mcp"."""

    def governs(self, rule: Rule) -> bool:
        """Whether this site could ever choose `rule`."""
        match = rule.get("match") or {}
        if set(match) - set(self.keys):
            return False
        for key, permitted in self.values.items():
            if key in match and permitted and match[key] not in permitted:
                return False
        return True

    def first(self, rules: list[Rule], **criteria: Any) -> Rule | None:
        """The first governed rule whose match equals `criteria`. First wins."""
        for rule in rules:
            if not self.governs(rule):
                continue
            match = rule.get("match") or {}
            if all(match.get(key) == value for key, value in criteria.items()):
                return rule
        return None

    def index(self, rules: list[Rule], key: str) -> dict[str, Rule]:
        """Governed rules keyed by one of their match values.

        Later rules overwrite earlier ones on a collision, which is why
        `compile` requires the key to be unique across the section.
        """
        return {
            (rule.get("match") or {}).get(key) or "": rule
            for rule in rules
            if self.governs(rule)
        }


def selector(
    section: str,
    *,
    keys: tuple[str, ...],
    site: str,
    values: Mapping[str, tuple[str, ...]] | None = None,
) -> Selector:
    """Declare a selection site and register it."""
    entry = Selector(section=section, keys=keys, values=values or {}, site=site)
    REGISTRY.append(entry)
    return entry


def governing(rule: Rule, section: str) -> list[Selector]:
    """Every registered site that could choose `rule`."""
    return [s for s in REGISTRY if s.section == section and s.governs(rule)]
