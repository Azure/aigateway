"""Each decision that moved from `plan.py` into `rules.json`, as it was.

`test_decisions_unchanged.py` compares the plan built from the fake ARM
fixture, which proves the wiring but only for the cases that fixture reaches.
It does not reach a pool using session affinity, an unbounded published
surface, or a private-networking requirement -- and a decision that moved
wrongly in one of those stayed green there. One did: the session-affinity
options lost `block`, the option that stops a migration, and gained an invented
one, and the fixture's silence let it through.

So every moved decision is pinned here instead, transcribed from the code that
held it before the move. These are not assertions about what the rules *should*
say; they are a copy of what they *did* say, and a diff is a decision changed.

Pinning the rule is half of it. A decision is only in the file if the planner
reads it from there, and seven sites kept writing their own option list beside a
rule that carried one -- editing the file moved nothing, and `rule-field-unread`
could not see it because each site declared it read `options`. So every site is
asked the other question too: say something different in the rule, and the plan
has to say it back.
"""

from __future__ import annotations

import copy

import pytest

from migrate_apim.capability import CapabilityMap
from migrate_apim.dispatch import matches
from migrate_apim.collect import Collector, CollectOptions
from migrate_apim.plan import build_plan
from migrate_apim import plan as plan_mod
from fake_arm import SERVICE, FakeArmClient


@pytest.fixture(scope="module")
def caps():
    return CapabilityMap.load()


@pytest.fixture(scope="module")
def inventory():
    return Collector(FakeArmClient(), SERVICE,
                     CollectOptions(cognitive_api_version="2025-06-01")).run()


def decision(rule):
    """The fields that decide an item, ignoring how the rule was selected."""
    return {
        "verdict": rule.get("verdict"),
        "answer": rule.get("answer"),
        "capabilityId": rule.get("capabilityId"),
        "proposal": rule.get("proposal"),
        "options": [o["value"] if isinstance(o, dict) else o for o in rule.get("options") or []],
        "blocking": rule.get("blocking"),
    }


def expected(verdict, answer=None, capabilityId=None, proposal=None, options=(), blocking=None):
    return {"verdict": verdict, "answer": answer, "capabilityId": capabilityId,
            "proposal": proposal, "options": list(options), "blocking": blocking}


class TestTheDecisionsThatMovedAreTheOnesThatWereThere:
    def test_a_provider_registers_directly(self, caps):
        rule = plan_mod.PROVIDER_RULE.first(caps.asset_rules())
        assert decision(rule) == expected("native", capabilityId="provider.create")

    def test_a_model_registers_directly(self, caps):
        rule = plan_mod.MODEL_REGISTRATION_RULE.first(caps.asset_rules())
        assert decision(rule) == expected("native", capabilityId="model.create")

    def test_an_unbounded_surface_publishes_inference_only(self, caps):
        rule = plan_mod.SURFACE_BY_STATUS.first(caps.asset_rules(), group="wildcard")
        assert decision(rule) == expected(
            "partial", "choose", "alias.create", "inference-only",
            ["inference-only", "retain-in-apim", "block"], blocking=True)

    def test_a_partly_publishable_surface_splits(self, caps):
        rule = plan_mod.SURFACE_PARTIALLY_PUBLISHABLE.first(
            caps.asset_rules(), publishable=False)
        assert decision(rule) == expected(
            "partial", "choose", "alias.create", "split",
            ["split", "inference-only", "retain-in-apim", "block"], blocking=True)

    def test_a_translating_dialect_moves_callers(self, caps):
        rule = plan_mod.DIALECT_TRANSLATING.first(caps.asset_rules(), status="translating")
        assert decision(rule) == expected(
            "partial", "choose", "alias.create", "move-callers",
            ["move-callers", "retain-in-apim", "block"], blocking=True)

    def test_an_indeterminate_dialect_asks_and_proposes_nothing(self, caps):
        rule = plan_mod.DIALECT_INDETERMINATE.first(caps.asset_rules(), status="indeterminate")
        assert decision(rule) == expected(
            "partial", "supply", "alias.create", None,
            ["confirm-dialect", "retain-in-apim"], blocking=True)

    def test_session_affinity_keeps_the_option_that_stops_a_migration(self, caps):
        """The one the fixture does not reach, and the one that moved wrongly."""
        rule = plan_mod.SESSION_AFFINITY_RULE.first(caps.asset_rules())
        assert decision(rule) == expected(
            "gap", "choose", "alias.create", "accept-loss",
            ["accept-loss", "retain-in-apim", "block"])

    def test_a_read_catalogue_is_published_as_listed(self, caps):
        rule = plan_mod.CATALOGUE_RULE.first(caps.asset_rules(), catalogue=["gpt-4o"])
        assert decision(rule) == expected(
            "partial", "supply", "model.create", "list-models",
            ["list-models", "retain-in-apim"], blocking=True)

    def test_an_unread_catalogue_with_an_endpoint_proposes_resolving_it(self, caps):
        rule = plan_mod.CATALOGUE_RULE.first(
            caps.asset_rules(), catalogue=[], discoverySource="modelsEndpoint")
        assert decision(rule) == expected(
            "partial", "supply", "model.create", "resolve-models",
            ["resolve-models", "list-models", "retain-in-apim"], blocking=True)

    def test_an_unread_catalogue_without_one_proposes_naming_them(self, caps):
        rule = plan_mod.CATALOGUE_RULE.first(
            caps.asset_rules(), catalogue=[], discoverySource=None)
        assert decision(rule) == expected(
            "partial", "supply", "model.create", "list-models",
            ["resolve-models", "list-models", "retain-in-apim"], blocking=True)

    def test_alias_names_default_to_the_model_names(self, caps):
        rule = plan_mod.ALIAS_NAMES_RULE.first(caps.asset_rules())
        assert decision(rule) == expected(
            "partial", "supply", "alias.create", "use-model-names",
            ["use-model-names", "override"])

    def test_a_bypassed_tool_list_is_a_decision(self, caps):
        rule = plan_mod.TOOL_EXPOSURE_BYPASSED.first(
            caps.asset_rules(), policiesApplied=False)
        assert decision(rule) == expected(
            "partial", "supply", None, "accept-as-listed",
            ["accept-as-listed", "verify-through-gateway", "retain-in-apim"])

    def test_a_user_assigned_identity_is_a_choice(self, caps):
        rule = plan_mod.IDENTITY_RULE.first(
            caps.structural_rules(), userAssignedIdentities=[{"resourceId": "/uai/one"}])
        # The reuse options are one per identity the source carries, so they are
        # built where the inventory is read; `system-assigned` is the choice
        # that exists either way.
        assert decision(rule) == expected(
            "partial", "choose", "identity.assign", "system-assigned", ["system-assigned"])

    def test_without_one_the_gateway_takes_its_own(self, caps):
        rule = plan_mod.IDENTITY_RULE.first(
            caps.structural_rules(), userAssignedIdentities=[])
        assert decision(rule) == expected(
            "native", capabilityId="identity.assign", proposal="system-assigned")

    def test_backends_needing_a_subnet_propose_one(self, caps):
        rule = plan_mod.REACHABILITY_BY_SUBNET.first(caps.structural_rules(), needsSubnet=True)
        assert decision(rule) == expected(
            "partial", "choose", "network.update", "new-delegated-subnet",
            ["new-delegated-subnet", "public-egress", "retain-in-apim", "block"])

    def test_backends_not_needing_one_propose_private_ingress(self, caps):
        """The one case where moving a decision had to change it.

        `plan.py` offered the same four options whichever way `needsSubnet`
        went, and proposed `private-ingress` here -- a recommendation that was
        not among the choices, so nobody could settle the item on it.
        `proposal-is-an-option` says that cannot be written down, so the
        proposal joins the options rather than the four being narrowed.
        """
        rule = plan_mod.REACHABILITY_BY_SUBNET.first(caps.structural_rules(), needsSubnet=False)
        assert decision(rule) == expected(
            "partial", "choose", "network.update", "private-ingress",
            ["private-ingress", "new-delegated-subnet", "public-egress",
             "retain-in-apim", "block"])


OFFERED = ["named-only-in-the-file"]


def saying(caps, site, overrides, **predicates):
    """The shipped rules with one rule rewritten, as a map the planner can use.

    Named by the selection site, which is what says where the rewritten rule is
    read. Selection is left exactly as it ships: the question is whether the
    planner reads the rule it already chooses, not whether a different one can
    be made to win.
    """
    rules = copy.deepcopy(caps.rules)
    for section in ("assets", "structural"):
        for rule in rules[section]:
            # `selects` alone stopped identifying a site once several of them
            # named the same APIM object -- an API is asked about by the MCP
            # registration site, the agent site and the alias-naming site, which
            # are told apart by what they narrow on. `governs` is what "this
            # site reads this rule" means, so it is what this asks.
            if not site.governs(rule):
                continue
            if matches(rule.get("where") or {}, predicates):
                rule.update(overrides)
                return CapabilityMap(caps.catalog, rules)
    raise AssertionError(f"no {site.selects} rule matching {predicates}")


def item_with(plan, aspect):
    return next(item for item in plan["items"] if item["source"]["aspect"] == aspect)


def offered(item):
    return [option["value"] for option in item["options"]]


class TestThePlannerOffersWhatTheFileSays:
    """Change a rule, and the item it decides has to change with it."""

    def test_a_provider_takes_its_verdict_from_the_rule(self, inventory, caps):
        built = build_plan(inventory, saying(caps, plan_mod.PROVIDER_RULE, {"verdict": "handled"}))
        item = next(i for i in built["items"] if i["source"]["assetKind"] == "modelProvider")
        assert item["verdict"] == "handled"

    def test_a_model_registration_takes_its_verdict_from_the_rule(self, inventory, caps):
        built = build_plan(inventory, saying(
            caps, plan_mod.MODEL_REGISTRATION_RULE, {"verdict": "handled"}))
        item = next(i for i in built["items"] if i["source"]["aspect"].startswith("model:"))
        assert item["verdict"] == "handled"

    def test_an_unbounded_surface_offers_the_rules_choices(self, inventory, caps):
        built = build_plan(inventory, saying(
            caps, plan_mod.SURFACE_BY_STATUS, {"options": OFFERED}, group="wildcard"))
        # Three APIs raise this question; the unbounded one is the API whose
        # surface could not be read, which is the rule being changed here.
        item = next(i for i in built["items"]
                    if i["source"]["aspect"] == "publishedSurface"
                    and i["proposal"] == "inference-only")
        assert offered(item) == OFFERED

    def test_a_partly_publishable_surface_offers_the_rules_choices(self, inventory, caps):
        built = build_plan(inventory, saying(
            caps, plan_mod.SURFACE_PARTIALLY_PUBLISHABLE, {"options": OFFERED},
            publishable=False))
        item = next(i for i in built["items"]
                    if i["source"]["aspect"] == "publishedSurface" and i["proposal"] == "split")
        assert offered(item) == OFFERED

    def test_what_splitting_costs_is_still_this_apis_number(self, inventory, caps):
        """The half that stays in code: the choice is the rule's, the sentence
        counts the operations this API leaves behind, which no rule can know."""
        item = next(i for i in build_plan(inventory, caps)["items"]
                    if i["source"]["aspect"] == "publishedSurface" and i["proposal"] == "split")
        consequence = {o["value"]: o["consequence"] for o in item["options"]}["split"]
        left_behind = item["evidence"]["surface"]["unpublishableCount"]
        assert f"{left_behind} operations stay on APIM" in consequence

    def test_a_translating_dialect_offers_the_rules_choices(self, inventory, caps):
        built = build_plan(inventory, saying(
            caps, plan_mod.DIALECT_TRANSLATING, {"options": OFFERED}, status="translating"))
        assert offered(item_with(built, "callerDialect")) == OFFERED

    def test_an_indeterminate_dialect_offers_the_rules_choices(self, inventory, caps):
        changed = copy.deepcopy(inventory)
        asset = next(m for m in changed["assets"]["models"] if m["source"]["name"] == "model-api")
        asset["endpoints"]["translation"]["status"] = "indeterminate"
        built = build_plan(changed, saying(
            caps, plan_mod.DIALECT_INDETERMINATE, {"options": OFFERED}, status="indeterminate"))
        assert offered(item_with(built, "callerDialect")) == OFFERED

    def test_session_affinity_offers_the_rules_choices(self, inventory, caps):
        changed = copy.deepcopy(inventory)
        asset = next(m for m in changed["assets"]["models"] if m["source"]["name"] == "aoai-api")
        asset["routing"]["sessionAffinity"] = {"enabled": True}
        built = build_plan(changed, saying(
            caps, plan_mod.SESSION_AFFINITY_RULE, {"options": OFFERED}))
        assert offered(item_with(built, "sessionAffinity")) == OFFERED

    def test_an_unread_catalogue_offers_the_rules_choices(self, inventory, caps):
        built = build_plan(inventory, saying(
            caps, plan_mod.CATALOGUE_RULE, {"options": OFFERED},
            catalogue=[], discoverySource="modelsEndpoint"))
        assert offered(item_with(built, "modelCatalogue")) == OFFERED

    def test_alias_naming_offers_the_rules_choices(self, inventory, caps):
        built = build_plan(inventory, saying(
            caps, plan_mod.ALIAS_NAMES_RULE, {"options": OFFERED}))
        assert offered(item_with(built, "aliasNames")) == OFFERED

    def test_a_bypassed_tool_list_offers_the_rules_choices(self, inventory, caps):
        changed = copy.deepcopy(inventory)
        server = changed["assets"]["mcpServers"][0]
        server["toolDiscovery"] = {"status": "complete", "policiesApplied": False,
                                   "discoveredCount": 3}
        built = build_plan(changed, saying(
            caps, plan_mod.TOOL_EXPOSURE_BYPASSED, {"options": OFFERED},
            policiesApplied=False))
        assert offered(item_with(built, "toolExposure")) == OFFERED

    def test_a_user_assigned_identity_offers_the_rules_choice_and_the_reuse(
        self, inventory, caps
    ):
        changed = copy.deepcopy(inventory)
        changed["service"]["identity"]["userAssignedIdentities"] = [{"resourceId": "/uai/one"}]
        built = build_plan(changed, saying(
            caps, plan_mod.IDENTITY_RULE, {"options": OFFERED},
            userAssignedIdentities=[{"resourceId": "/uai/one"}]))
        assert offered(item_with(built, "gatewayIdentity")) == [*OFFERED, "reuse:/uai/one"]

    def test_backend_reachability_offers_the_rules_choices(self, inventory, caps):
        changed = copy.deepcopy(inventory)
        changed["service"]["networking"]["targetRequirement"] = {
            "needsSubnet": True, "note": "Collected."}
        built = build_plan(changed, saying(
            caps, plan_mod.REACHABILITY_BY_SUBNET, {"options": OFFERED}, needsSubnet=True))
        assert offered(item_with(built, "backendReachability")) == OFFERED


class TestEveryMovedDecisionIsPinned:
    """A pin that quietly stops covering a site proves nothing."""

    MOVED = (
        plan_mod.PROVIDER_RULE, plan_mod.SURFACE_BY_STATUS,
        plan_mod.SURFACE_PARTIALLY_PUBLISHABLE, plan_mod.DIALECT_TRANSLATING,
        plan_mod.DIALECT_INDETERMINATE, plan_mod.SESSION_AFFINITY_RULE,
        plan_mod.CATALOGUE_RULE, plan_mod.MODEL_REGISTRATION_RULE,
        plan_mod.ALIAS_NAMES_RULE, plan_mod.TOOL_EXPOSURE_BYPASSED,
        plan_mod.IDENTITY_RULE, plan_mod.REACHABILITY_BY_SUBNET,
    )

    def test_each_path_has_a_rule(self, caps):
        rules = [*caps.asset_rules(), *caps.structural_rules()]
        answered = {rule.get("selects") for rule in rules}
        paths = {site.selects for site in self.MOVED}
        assert paths <= answered, sorted(paths - answered)

    def test_each_path_has_a_selection_site(self):
        from migrate_apim.dispatch import REGISTRY

        sites = {site.selects for site in REGISTRY}
        paths = {site.selects for site in self.MOVED}
        assert paths <= sites, sorted(paths - sites)
