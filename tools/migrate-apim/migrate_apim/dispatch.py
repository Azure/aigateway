"""Where rule selection happens, declared once so it can be checked.

`rules.json` is only worth maintaining if the planner reads what it says. Three
things can go wrong quietly, and all three had:

* a rule names a `where` key no selector examines, so it is never chosen;
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

A selector `governs` a rule when the rule decides the subject the selector
selects, its `where` and `derived` keys are a subset of the ones the selector
examines, and every value it constrains is one the selector accepts. Subset
rather than equality: a rule may legitimately pin fewer keys. What it may not
do is pin *more*, because the surplus would be silently ignored.

A fourth thing can go wrong, one layer in: the rule is selected, and then a
*field* of it is never looked at. That is the same defect as an unreadable
`where` key -- something written expecting an effect it does not have -- so it
is answered the same way. A selector also declares what it `reads`, and the site
that reads a field is the site that declares it. The declaration is worth no
more than its narrowness: a site that claims to read `options` while writing its
own list satisfies the check and keeps the decision in the code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

# Every selection site in the planner, in declaration order. Populated at import
# time by the modules that declare selectors; `compile` imports those modules to
# fill it.
REGISTRY: list["Selector"] = []

Rule = dict[str, Any]


# Keys every rule carries that are not a field of the rule's own vocabulary:
# the four that say how the rule is selected, and `note`, which is addressed to
# whoever reads the file. None is expected to be consumed by a selection site.
STRUCTURAL_KEYS = ("selects", "where", "derived", "fallback", "note")


# Hashing is off because `values` is a Mapping, so the hash a frozen dataclass
# would generate raises TypeError the first time anyone puts a selector in a set.
# Identity is the right comparison anyway: two sites that read the same keys are
# still two sites.
@dataclass(frozen=True, eq=False)
class Selector:
    """One rule-selection site: the criteria it dispatches on, and what it reads."""

    section: str
    """Which top-level list of rules.json this reads: assets, structural, policies."""

    selects: str
    """The subject this site decides about: `policyElement`, `mcpServer`, `workspace`.

    A rule's subject used to be implied by which array it sat in, which made
    `family` name the subject in `assets[]` (`mcpServers`) and act as a
    predicate on a field in `policies[]` (`authentication`). Naming the subject
    lets `family` keep only the second job.
    """

    keys: tuple[str, ...]
    """The `where` keys this site examines. Anything else on a rule is ignored.

    Field predicates only. Each names a field of the subject's inventory record,
    which is what lets `compile` check it against the schema.
    """

    values: Mapping[str, tuple[str, ...]]
    """Accepted literals per key. A key absent here, or mapped to (), is unconstrained."""

    site: str
    """Where the selection happens, for diagnostics: "plan._mcp"."""

    reads: tuple[str, ...] = ()
    """The rule fields this site consumes once it has chosen a rule.

    Declared for the same reason `keys` is. A field no site reads is a field
    somebody wrote expecting an effect it does not have, and the only way to
    know is to ask the sites. `compile` warns about any field outside the union
    of this across a rule's governing sites, so the list that decides it lives
    where the reading happens rather than in the checker.
    """

    derived: tuple[str, ...] = ()
    """Predicates computed from the record rather than read off it.

    `hasExpression` is `bool(element["expressionIds"])`. No record carries it,
    so holding it to the same schema check as a `where` key would reject it.
    """

    fallback: bool = False
    """Whether this site chooses the rule that answers when nothing else did.

    A fallback is not a predicate, and writing it as one -- `anyElement: true` --
    made it look like a field of the subject. A site either selects fallbacks or
    it does not, and the two never choose each other's rules.
    """

    fields: Mapping[str, str] = field(default_factory=dict)
    """Per `where` key, the inventory path it is compared against.

    The binding between `where.name` and `element["name"]` lived only inside the
    resolver, so a rule could match on a field no record has and simply never
    fire. Declared here, `compile` checks it the way it already checks a
    declared CLI option against the surface snapshot.
    """

    def governs(self, rule: Rule) -> bool:
        """Whether this site could ever choose `rule`."""
        if rule.get("selects") != self.selects:
            return False
        if bool(rule.get("fallback")) != self.fallback:
            return False
        where = rule.get("where") or {}
        if set(where) - set(self.keys):
            return False
        for key, permitted in self.values.items():
            if key in where and permitted and where[key] not in permitted:
                return False
        if set(rule.get("derived") or {}) - set(self.derived):
            return False
        return True

    def first(self, rules: list[Rule], **criteria: Any) -> Rule | None:
        """The first governed rule whose predicates equal `criteria`. First wins.

        A criterion is looked up in whichever block declares it, so a caller
        asks the same way whether the predicate is read off the record or
        computed from it. The two vocabularies are disjoint by construction --
        a key is declared in `keys` or in `derived`, never both.
        """
        for rule in rules:
            if not self.governs(rule):
                continue
            where = rule.get("where") or {}
            derived = rule.get("derived") or {}
            if all((where if key in self.keys else derived).get(key) == value
                   for key, value in criteria.items()):
                return rule
        return None

    def index(self, rules: list[Rule], key: str) -> dict[str, Rule]:
        """Governed rules keyed by one of their match values.

        Later rules overwrite earlier ones on a collision, which is why
        `compile` requires the key to be unique across the section.
        """
        return {
            (rule.get("where") or {}).get(key) or "": rule
            for rule in rules
            if self.governs(rule)
        }


def selector(
    section: str,
    *,
    selects: str,
    site: str,
    keys: tuple[str, ...] = (),
    values: Mapping[str, tuple[str, ...]] | None = None,
    reads: tuple[str, ...] = (),
    derived: tuple[str, ...] = (),
    fallback: bool = False,
    fields: Mapping[str, str] | None = None,
) -> Selector:
    """Declare a selection site and register it."""
    entry = Selector(
        section=section, selects=selects, keys=keys, values=values or {}, site=site,
        reads=reads, derived=derived, fallback=fallback, fields=fields or {},
    )
    REGISTRY.append(entry)
    return entry


def governing(rule: Rule, section: str) -> list[Selector]:
    """Every registered site that could choose `rule`."""
    return [s for s in REGISTRY if s.section == section and s.governs(rule)]


def fields_read(rule: Rule, section: str) -> set[str]:
    """Every field of `rule` that some site able to choose it would consume.

    The union across governing sites, not the intersection: a rule reachable
    from two sites is read by whichever one chose it, so a field either of them
    takes is a field with an effect.
    """
    return {field for site in governing(rule, section) for field in site.reads}
