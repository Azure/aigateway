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
"""

from __future__ import annotations

import pytest

from migrate_apim.capability import CapabilityMap
from migrate_apim import plan as plan_mod


@pytest.fixture(scope="module")
def caps():
    return CapabilityMap.load()


def decision(rule):
    """The fields that decide an item, ignoring how the rule was selected."""
    return {
        "verdict": rule.get("verdict"),
        "itemKind": rule.get("itemKind"),
        "capabilityId": rule.get("capabilityId"),
        "proposal": rule.get("proposal"),
        "options": [o["value"] if isinstance(o, dict) else o for o in rule.get("options") or []],
        "blocking": rule.get("blocking"),
    }


def expected(verdict, itemKind=None, capabilityId=None, proposal=None, options=(), blocking=None):
    return {"verdict": verdict, "itemKind": itemKind, "capabilityId": capabilityId,
            "proposal": proposal, "options": list(options), "blocking": blocking}


class TestTheDecisionsThatMovedAreTheOnesThatWereThere:
    def test_a_provider_registers_directly(self, caps):
        rule = plan_mod.PROVIDER_RULE.first(caps.asset_rules())
        assert decision(rule) == expected("native", capabilityId="provider.create")

    def test_a_model_registers_directly(self, caps):
        rule = plan_mod.MODEL_REGISTRATION_RULE.first(caps.asset_rules())
        assert decision(rule) == expected("native", capabilityId="model.create")

    def test_an_unbounded_surface_publishes_inference_only(self, caps):
        rule = plan_mod.SURFACE_BY_STATUS.first(caps.asset_rules(), status="unbounded")
        assert decision(rule) == expected(
            "partial", "reduce-surface", "alias.create", "inference-only",
            ["inference-only", "retain-in-apim", "block"], blocking=True)

    def test_a_partly_publishable_surface_splits(self, caps):
        rule = plan_mod.SURFACE_PARTIALLY_PUBLISHABLE.first(
            caps.asset_rules(), hasUnpublishable=True)
        assert decision(rule) == expected(
            "partial", "reduce-surface", "alias.create", "split",
            ["split", "inference-only", "retain-in-apim", "block"], blocking=True)

    def test_a_translating_dialect_moves_callers(self, caps):
        rule = plan_mod.DIALECT_BY_STATUS.first(caps.asset_rules(), status="translating")
        assert decision(rule) == expected(
            "partial", "translate", "alias.create", "move-callers",
            ["move-callers", "retain-in-apim", "block"], blocking=True)

    def test_an_indeterminate_dialect_asks_and_proposes_nothing(self, caps):
        rule = plan_mod.DIALECT_BY_STATUS.first(caps.asset_rules(), status="indeterminate")
        assert decision(rule) == expected(
            "partial", "enumerate", "alias.create", None,
            ["confirm-dialect", "retain-in-apim"], blocking=True)

    def test_session_affinity_keeps_the_option_that_stops_a_migration(self, caps):
        """The one the fixture does not reach, and the one that moved wrongly."""
        rule = plan_mod.SESSION_AFFINITY_RULE.first(caps.asset_rules())
        assert decision(rule) == expected(
            "gap", "accept-loss", "alias.create", "accept-loss",
            ["accept-loss", "retain-in-apim", "block"])

    def test_a_read_catalogue_is_published_as_listed(self, caps):
        rule = plan_mod.CATALOGUE_RULE.first(caps.asset_rules(), hasCatalogue=True)
        assert decision(rule) == expected(
            "partial", "enumerate", "model.create", "list-models",
            ["list-models", "retain-in-apim"], blocking=True)

    def test_an_unread_catalogue_with_an_endpoint_proposes_resolving_it(self, caps):
        rule = plan_mod.CATALOGUE_RULE.first(
            caps.asset_rules(), hasCatalogue=False, discoverySource="modelsEndpoint")
        assert decision(rule) == expected(
            "partial", "enumerate", "model.create", "resolve-models",
            ["resolve-models", "list-models", "retain-in-apim"], blocking=True)

    def test_an_unread_catalogue_without_one_proposes_naming_them(self, caps):
        rule = plan_mod.CATALOGUE_RULE.first(
            caps.asset_rules(), hasCatalogue=False, discoverySource=None)
        assert decision(rule) == expected(
            "partial", "enumerate", "model.create", "list-models",
            ["resolve-models", "list-models", "retain-in-apim"], blocking=True)

    def test_alias_names_default_to_the_model_names(self, caps):
        rule = plan_mod.ALIAS_NAMES_RULE.first(caps.asset_rules())
        assert decision(rule) == expected(
            "partial", "name", "alias.create", "use-model-names",
            ["use-model-names", "override"])

    def test_a_bypassed_tool_list_is_a_decision(self, caps):
        rule = plan_mod.TOOL_EXPOSURE_BYPASSED.first(caps.asset_rules(), policiesBypassed=True)
        assert decision(rule) == expected(
            "partial", "enumerate", None, "accept-as-listed",
            ["accept-as-listed", "verify-through-gateway", "retain-in-apim"])

    def test_a_user_assigned_identity_is_a_choice(self, caps):
        rule = plan_mod.IDENTITY_RULE.first(caps.structural_rules(), hasUserAssigned=True)
        # The reuse options are one per identity the source carries, so they are
        # built where the inventory is read; `system-assigned` is the choice
        # that exists either way.
        assert decision(rule) == expected(
            "partial", "translate", "identity.assign", "system-assigned", ["system-assigned"])

    def test_without_one_the_gateway_takes_its_own(self, caps):
        rule = plan_mod.IDENTITY_RULE.first(caps.structural_rules(), hasUserAssigned=False)
        assert decision(rule) == expected(
            "native", capabilityId="identity.assign", proposal="system-assigned")

    def test_backends_needing_a_subnet_propose_one(self, caps):
        rule = plan_mod.REACHABILITY_BY_SUBNET.first(caps.structural_rules(), needsSubnet=True)
        assert decision(rule) == expected(
            "partial", "translate", "network.update", "new-delegated-subnet",
            ["new-delegated-subnet", "public-egress", "retain-in-apim", "block"])

    def test_backends_not_needing_one_propose_private_ingress(self, caps):
        rule = plan_mod.REACHABILITY_BY_SUBNET.first(caps.structural_rules(), needsSubnet=False)
        assert decision(rule) == expected(
            "partial", "translate", "network.update", "private-ingress",
            ["private-ingress", "public-egress", "retain-in-apim", "block"])


class TestEveryMovedDecisionIsPinned:
    """A pin that quietly stops covering a site proves nothing."""

    MOVED = (
        "modelProvider", "publishedSurface", "callerDialect", "sessionAffinity",
        "modelCatalogue", "modelRegistration", "aliasNames", "toolExposure",
        "gatewayIdentity", "backendReachability",
    )

    def test_each_subject_has_a_rule(self, caps):
        rules = [*caps.asset_rules(), *caps.structural_rules()]
        answered = {rule.get("selects") for rule in rules}
        assert set(self.MOVED) <= answered, sorted(set(self.MOVED) - answered)

    def test_each_subject_has_a_selection_site(self):
        from migrate_apim.dispatch import REGISTRY

        sites = {site.selects for site in REGISTRY}
        assert set(self.MOVED) <= sites, sorted(set(self.MOVED) - sites)
