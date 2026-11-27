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

A selector `governs` a rule when the rule selects the same inventory path, its
`where` keys are a subset of the ones the selector examines, and every literal
it constrains is one the selector accepts. Subset rather than equality: a rule
may legitimately pin fewer keys. What it may not do is pin *more*, because the
surplus would be silently ignored.

A `where` predicate takes one of three forms and no others -- `key: value` for
equals, `key: [a, b]` for one of, `key: {"nonEmpty": bool}` for non-empty or
empty. `compile` rejects anything else. Three is what the thirty-nine rules
need; a fourth would start `where` down the road to a query language, and a
predicate that needs `contains` or `matches` belongs in code where it can say
why.

The third form was `present`, which reads as "the key exists" -- the one thing
it does not test. It is truthiness: `[]`, `""` and `0` are all empty. That
distinction is load-bearing on `inferenceRoutes`, where an empty list is a
model declaring it serves no route and so a real decision, while null means the
dialect could not be read and is filtered out before any predicate runs. Read
as a null check, `{"nonEmpty": false}` would stop matching the empty list and a
model that serves nothing would register as though it served something.

A fourth thing can go wrong, one layer in: the rule is selected, and then a
*field* of it is never looked at. That is the same defect as an unreadable
`where` key -- something written expecting an effect it does not have -- so it
is answered the same way. A selector also declares what it `reads`, and the site
that reads a field is the site that declares it. The declaration is worth no
more than its narrowness: a site that claims to read `options` while writing its
own list satisfies the check and keeps the decision in the code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# Every selection site in the planner, in declaration order. Populated at import
# time by the modules that declare selectors; `compile` imports those modules to
# fill it.
REGISTRY: list["Selector"] = []

Rule = dict[str, Any]


# Keys every rule carries that are not a field of the rule's own vocabulary:
# the three that say how the rule is selected, and `note`, which is addressed to
# whoever reads the file. None is expected to be consumed by a selection site.
STRUCTURAL_KEYS = ("selects", "where", "fallback", "note")


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
    """Where the object this site judges lives, as a path into the inventory,
    with `[]` for "each of these": `assets.models[].endpoints.surface`.

    It used to be a label for the decision site -- `publishedSurface`, which
    exists nowhere in the inventory -- so neither half of a rule could be
    checked against anything a reader can open. A path can: take it, open the
    inventory, see the object the `where` keys are predicates on.
    """

    keys: tuple[str, ...]
    """The `where` keys this site examines. Anything else on a rule is ignored.

    Each names a field of the object `selects` points at, so `selects` plus the
    key is the path `compile` checks against inventory.schema.json. That used
    to need an alias table per site, mapping an invented key back to the real
    field; the path is the field now.
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

    fallback: bool = False
    """Whether this site chooses the rule that answers when nothing else did.

    A fallback is not a predicate, and writing it as one -- `anyElement: true` --
    made it look like a field of the subject. A site either selects fallbacks or
    it does not, and the two never choose each other's rules.
    """

    computed: tuple[str, ...] = ()
    """The `where` keys the planner works out rather than reads off the record.

    A fragment's `disposition` is the only one: no document carries it, because
    it is what this migration makes of the fragment -- dissolved, conditional,
    split across sections, unreferenced, unresolved. Named here so the path
    check knows there is no field to check it against, rather than skipping
    every key that happens to fail.
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
            if key not in where or not permitted:
                continue
            if not all(alt in permitted for alt in literals(where[key])):
                return False
        return True

    def first(self, rules: list[Rule], **criteria: Any) -> Rule | None:
        """The first governed rule whose `where` holds for `criteria`. First wins.

        A criterion is the value read off the record; which of the three forms
        the rule wrote it as is the rule's business. That is what lets
        `unpublishableCount` be asked once and answered by `{"nonEmpty": true}`,
        where the caller used to have to compute `hasUnpublishable` itself and
        the rule had to carry a key no record has.
        """
        for rule in rules:
            if self.governs(rule) and matches(rule.get("where") or {}, criteria):
                return rule
        return None


def selector(
    section: str,
    *,
    selects: str,
    site: str,
    keys: tuple[str, ...] = (),
    values: Mapping[str, tuple[str, ...]] | None = None,
    reads: tuple[str, ...] = (),
    fallback: bool = False,
    computed: tuple[str, ...] = (),
) -> Selector:
    """Declare a selection site and register it."""
    entry = Selector(
        section=section, selects=selects, keys=keys, values=values or {}, site=site,
        reads=reads, fallback=fallback, computed=computed,
    )
    REGISTRY.append(entry)
    return entry


def matches(where: Mapping[str, Any], criteria: Mapping[str, Any]) -> bool:
    """Whether every named predicate holds for the value read off the record."""
    return all(holds(where.get(key), value) for key, value in criteria.items())


def holds(predicate: Any, value: Any) -> bool:
    """One predicate against one value, in whichever of the three forms it took.

    A key the rule does not pin reads as `None`, so a rule that says nothing
    about a field only answers for a record that carries nothing there. That is
    what separates the catalogue rule naming `modelsEndpoint` from the one that
    names no source at all.
    """
    if isinstance(predicate, dict):
        return bool(value) is bool(predicate.get("nonEmpty"))
    if isinstance(predicate, list):
        return value in predicate
    return predicate == value


def literals(predicate: Any) -> tuple[Any, ...]:
    """The literals a predicate names, for the checks that compare against a
    vocabulary. A presence test names none."""
    if isinstance(predicate, dict):
        return ()
    return tuple(predicate) if isinstance(predicate, list) else (predicate,)


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
