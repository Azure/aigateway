"""What the tool decides, pinned against how it expresses the decision.

`rules.json` is being restructured: the subject of a rule moves out of which
array it sits in and into a `selects` key, its predicates move into `where`, and
decisions that were written in `plan.py` move into the file. None of that may
change a single verdict, option or proposal.

That property is hard to hold by reading a diff -- the diff is thousands of
lines and touches every rule -- so it is held here instead. `golden/decisions.json`
records two things, generated before the restructure began:

* **the resolution table** -- every element the collector can name, with and
  without an expression, against the decision the rules give it. A rule is
  identified by what it decides and not by how it is matched, because how it is
  matched is exactly what changes.
* **the plan** built from the fake ARM fixture, scrubbed of timestamps.

Regenerate it only when a decision is *meant* to change, and say so in the
commit. A diff here is either a bug or a deliberate answer to a new question.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from migrate_apim.capability import CapabilityMap
from migrate_apim.collect import Collector, CollectOptions
from migrate_apim.plan import build_plan
from migrate_apim.policy import FAMILIES, family_of
from fake_arm import SERVICE, FakeArmClient

GOLDEN = pathlib.Path(__file__).parent / "golden" / "decisions.json"

# How a rule is matched is what this refactor changes; what it decides is what
# must not. Identify a rule by the second.
_MATCHING = {"match", "selects", "where", "derived", "fallback", "note"}

_UNKNOWN = ("some-future-policy", "quantum-shield")


def rule_id(rule):
    if rule is None:
        return None
    return json.dumps({k: v for k, v in rule.items() if k not in _MATCHING}, sort_keys=True)


def resolution_table(caps):
    table = {}
    for name in sorted(FAMILIES):
        for expr in (False, True):
            table[f"{name}|expr={expr}"] = rule_id(
                caps.policy_rule(name, family=family_of(name), has_expression=expr)
            )
    for name in _UNKNOWN:
        for expr in (False, True):
            table[f"{name}|expr={expr}"] = rule_id(
                caps.policy_rule(name, family="other", has_expression=expr)
            )
    return table


def scrub(value):
    """Drop what moves between runs; keep every decision."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in sorted(value.items())
                if k not in {"generatedAt", "inventoryCapturedAt"}}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


class TestTheDecisionsAreTheOnesThatWereThereBefore:
    def test_every_element_resolves_to_the_decision_it_did(self):
        expected = json.loads(GOLDEN.read_text())["resolution"]
        actual = resolution_table(CapabilityMap.load())
        assert set(actual) == set(expected), "the vocabulary itself moved"
        moved = {
            name: (json.loads(expected[name] or "null"), json.loads(actual[name] or "null"))
            for name in sorted(expected)
            if actual[name] != expected[name]
        }
        assert not moved, f"{len(moved)} element(s) now resolve differently: {list(moved)[:5]}"

    def test_the_plan_is_the_one_that_was_there(self, inventory, capabilities):
        expected = json.loads(GOLDEN.read_text())["plan"]
        actual = scrub(build_plan(inventory, capabilities))
        assert actual == expected

    def test_the_golden_covers_every_element_the_collector_classifies(self):
        """A snapshot that quietly stops covering something proves nothing."""
        expected = json.loads(GOLDEN.read_text())["resolution"]
        covered = {name.split("|", 1)[0] for name in expected}
        assert covered == set(FAMILIES) | set(_UNKNOWN)


@pytest.fixture(scope="module")
def inventory():
    return Collector(FakeArmClient(), SERVICE,
                     CollectOptions(cognitive_api_version="2025-06-01")).run()


@pytest.fixture(scope="module")
def capabilities():
    return CapabilityMap.load()
