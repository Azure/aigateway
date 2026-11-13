import copy
import json

import pytest

from apim_import.capability import CapabilityMap
from apim_import.cli import validate_document
from apim_import.collect import Collector, CollectOptions
from apim_import.plan import build_plan
from fake_arm import SERVICE, FakeArmClient


def options(**overrides):
    overrides.setdefault("cognitive_api_version", "2025-06-01")
    return CollectOptions(**overrides)


@pytest.fixture(scope="module")
def inventory():
    return Collector(FakeArmClient(), SERVICE, options()).run()


@pytest.fixture(scope="module")
def capabilities():
    return CapabilityMap.load()


@pytest.fixture(scope="module")
def plan(inventory, capabilities):
    return build_plan(inventory, capabilities)


def items_of(plan, kind):
    return [item for item in plan["items"] if item.get("kind") == kind]


def item_for(plan, asset_id, aspect=None):
    for item in plan["items"]:
        source = item["source"]
        if source.get("assetId") == asset_id and (aspect is None or source["aspect"] == aspect):
            return item
    raise AssertionError(f"no item for {asset_id}/{aspect}")


class TestDocument:
    def test_is_schema_valid(self, plan):
        assert validate_document(plan) == []

    def test_is_json_serializable(self, plan):
        assert json.loads(json.dumps(plan))["kind"] == "apimMigrationPlan"

    def test_records_which_capability_catalogue_it_planned_against(self, plan):
        caps = plan["target"]["capabilities"]
        assert caps["cliVersion"] == "1.0.0b26"
        # Nothing is claimed about the installed CLI unless it was probed.
        assert caps["probed"] is False

    def test_target_routes_are_carried_on_the_plan(self, plan):
        assert sorted(plan["target"]["publishableRoutes"]) == [
            "/openai/v1/chat/completions", "/openai/v1/embeddings",
            "/openai/v1/responses", "/v1/messages",
        ]

    def test_every_unsettled_item_offers_a_choice_and_a_proposal_reason(self, plan):
        for item in plan["items"]:
            if item["status"] != "needs-decision":
                continue
            assert item["options"], f"{item['id']} has no options"
            assert item["rationale"], f"{item['id']} has no rationale"
            assert item["kind"], f"{item['id']} has no kind"

    def test_no_item_asks_for_a_decision_without_offering_one(self, plan):
        # Regression: an unconfigured MCP server raised an item with no options.
        for item in plan["items"]:
            if item["status"] == "needs-decision":
                assert item["options"], f"{item['id']} asks with nothing to choose from"

    def test_every_unsettled_item_arrives_with_a_proposal(self, plan):
        # "needs-decision" means confirm or change, never "you figure it out".
        for item in plan["items"]:
            if item["status"] == "needs-decision":
                assert item["proposal"] is not None, f"{item['id']} has no proposal"

    def test_a_control_with_no_equivalent_defaults_to_staying_on_apim(self, plan):
        # Dropping a security control by default would silently weaken the posture.
        item = next(
            i for i in plan["items"]
            if i["source"]["assetKind"] == "policy" and i["evidence"]["element"] == "llm-content-safety"
        )
        assert item["proposal"] == "retain-in-apim"

    def test_a_missing_cli_command_is_not_blamed_on_the_mapping_rules(self, inventory):
        # Regression: a capability the installed extension does not expose flipped
        # the item to accept-loss with no options, which then tripped the rulesGap
        # fallback -- sending the reader to fix a rules file that is fine.
        from apim_import.capability import CapabilityMap

        caps = CapabilityMap.load().probe(
            lambda command: None if command == ["mcp", "create"] else {"x"},
            available=lambda: True,
        )
        document = build_plan(inventory, caps)
        blocked = [i for i in document["items"] if i.get("capabilityUnavailable")]
        assert blocked
        for item in blocked:
            assert not item.get("rulesGap"), f"{item['id']} blames the rules for a CLI gap"
            assert "local CLI" in item["rationale"]
            assert "upgrade-cli" in {option["value"] for option in item["options"]}

    def test_every_item_explains_itself(self, plan):
        for item in plan["items"]:
            if item["status"] in {"needs-decision", "ready"}:
                assert item["rationale"].strip(), f"{item['id']} has no rationale"

    def test_an_incomplete_rule_is_reported_rather_than_hidden(self, capabilities, inventory):
        import copy

        stripped = copy.deepcopy(capabilities)
        for rule in stripped.rules["assets"]:
            rule.pop("options", None)
        document = build_plan(inventory, stripped)
        gaps = [item for item in document["items"] if item.get("rulesGap")]
        assert gaps
        assert all(item["options"] for item in gaps)

    def test_ready_items_carry_executable_target_objects(self, plan):
        # A ready item must not need re-deriving at apply time.
        ready = [i for i in plan["items"] if i["status"] == "ready"]
        assert ready
        for item in ready:
            assert item["target"].get("objects"), f"{item['id']} is ready with nothing to execute"
            assert item["capabilityId"]


class TestScopeIsTheDominantDecision:
    def test_an_api_with_unpublishable_operations_raises_reduce_surface(self, plan):
        item = item_for(plan, "model:aoai-api", "publishedSurface")
        assert item["kind"] == "reduce-surface"
        assert item["proposal"] == "split"
        assert item["blocking"] is True
        assert {option["value"] for option in item["options"]} == {
            "split", "inference-only", "retain-in-apim", "block"
        }

    def test_the_rationale_counts_what_cannot_move(self, plan):
        item = item_for(plan, "model:aoai-api", "publishedSurface")
        surface = item["evidence"]["surface"]
        assert surface["unpublishableCount"] >= 1
        assert str(surface["operationCount"]) in item["rationale"]

    def test_a_wildcard_api_cannot_be_split_only_scoped(self, plan):
        item = item_for(plan, "model:meta-ai", "publishedSurface")
        assert item["kind"] == "reduce-surface"
        # Nothing can be split when the surface is unreadable.
        assert "split" not in {option["value"] for option in item["options"]}
        assert item["proposal"] == "inference-only"


class TestGoverningRule:
    """A question only where the target cannot do something, or the answer is
    in a caller's head. Anything APIM already answers is a collector fix."""

    def test_no_item_asks_which_provider_an_api_uses(self, plan):
        for item in plan["items"]:
            aspect = item["source"]["aspect"]
            assert "provider" not in aspect.lower() or item["status"] != "needs-decision", (
                f"{item['id']} asks about provider identity, which APIM configuration answers"
            )

    def test_meta_ai_only_needs_scope_not_identity(self, plan):
        aspects = {
            item["source"]["aspect"] for item in plan["items"]
            if item["source"].get("assetId") == "model:meta-ai" and item["status"] == "needs-decision"
        }
        assert "publishedSurface" in aspects
        assert not any("provider" in aspect.lower() for aspect in aspects)

    def test_alias_name_is_asked_because_apim_does_not_store_it(self, plan):
        names = items_of(plan, "name")
        assert names
        for item in names:
            # Asked, but never blank: the deployment name is the default.
            assert item["proposal"]
            assert item["blocking"] is False


class TestPolicyMapping:
    def test_a_native_policy_is_not_demoted_by_an_expression(self, plan):
        # Regression: llm-token-limit maps to tokenLimit. A counter-key expression
        # makes the partitioning a choice, not the whole policy a loss.
        item = next(
            i for i in plan["items"]
            if i["source"]["assetKind"] == "policy" and i["evidence"]["element"] == "azure-openai-token-limit"
        )
        assert item["kind"] == "translate"
        assert item["verdict"] == "partial"
        assert item["proposal"] == "identity"
        assert {o["value"] for o in item["options"]} == {
            "identity", "ipAddress", "identity+ipAddress", "pooled"
        }

    def test_policies_with_no_target_become_an_accepted_loss(self, plan):
        elements = {
            i["evidence"]["element"] for i in plan["items"]
            if i["source"]["assetKind"] == "policy" and i["kind"] == "accept-loss"
        }
        assert "llm-content-safety" in elements
        assert "llm-semantic-cache-lookup" in elements

    def test_identical_policies_batch_into_one_decision(self, plan):
        # The prior attempt asked once per occurrence; that is what made it unusable.
        batched = [
            i for i in plan["items"]
            if i["source"]["assetKind"] == "policy" and i["evidence"]["occurrences"] > 1
        ]
        for item in batched:
            assert len(item["memberDigests"]) == item["evidence"]["occurrences"]

    def test_configuration_children_are_not_mistaken_for_policies(self, plan):
        # <set-header><value/></set-header> is one decision, not two.
        elements = {
            i["evidence"].get("element") for i in plan["items"]
            if i["source"]["assetKind"] == "policy"
        }
        assert "value" not in elements
        assert "category" not in elements
        assert "categories" not in elements

    def test_plumbing_raises_nothing(self, plan):
        elements = {
            i["evidence"].get("element") for i in plan["items"]
            if i["source"]["assetKind"] == "policy"
        }
        assert not elements & {"base", "include-fragment", "choose", "when", "set-variable"}


class TestStructural:
    def test_a_non_default_workspace_must_be_collapsed(self, plan):
        [item] = items_of(plan, "collapse")
        assert item["evidence"]["workspace"]["name"] == "finance"
        assert item["proposal"] == "flatten"
        assert item["blocking"] is True

    def test_subscriptions_raise_one_access_decision(self, plan):
        [item] = items_of(plan, "scope")
        assert item["evidence"]["count"] == 2
        assert sorted(item["evidence"]["scopeLevels"]) == ["product", "service"]

    def test_the_a2a_agent_has_no_target(self, plan):
        item = item_for(plan, "agent:support-agent", "registration")
        assert item["verdict"] == "gap"
        assert item["proposal"] == "retain-in-apim"


class TestPrerequisites:
    def test_external_steps_are_surfaced_before_execution(self, plan):
        ids = {entry["id"] for entry in plan["prerequisites"]}
        assert "prereq:caller-rbac" in ids
        assert "prereq:name-collision" in ids

    def test_managed_identity_providers_require_a_backend_grant(self, plan):
        ids = {entry["id"] for entry in plan["prerequisites"]}
        assert "prereq:foundry-rbac" in ids


class TestRegeneration:
    """Adaptations survive; only the facts they rested on can unsettle them."""

    def test_an_adapted_decision_is_preserved(self, inventory, capabilities, plan):
        adapted = copy.deepcopy(plan)
        target = item_for(adapted, "model:aoai-api", "publishedSurface")
        target["status"] = "adapted"
        target["decision"] = "split"

        again = build_plan(inventory, capabilities, previous=adapted)
        item = item_for(again, "model:aoai-api", "publishedSurface")
        assert item["status"] == "adapted"
        assert item["decision"] == "split"
        assert item["decidedAgainst"]["shape"] == target["shapeDigest"]

    def test_only_the_changed_item_goes_stale(self, inventory, capabilities, plan):
        adapted = copy.deepcopy(plan)
        for item in adapted["items"]:
            if item["status"] == "needs-decision":
                item["status"] = "adapted"
                item["decision"] = item["proposal"] or "accept"

        changed = copy.deepcopy(inventory)
        model = next(m for m in changed["assets"]["models"] if m["source"]["name"] == "aoai-api")
        model["endpoints"]["surface"]["unpublishableCount"] = 99

        again = build_plan(changed, capabilities, previous=adapted)
        stale = [i["id"] for i in again["items"] if i["status"] == "stale"]
        assert stale == ["item:model/aoai-api/surface"]
        assert again["summary"]["byStatus"].get("adapted", 0) > 1

    def test_a_stale_item_keeps_its_prior_decision_and_says_why(self, inventory, capabilities, plan):
        adapted = copy.deepcopy(plan)
        target = item_for(adapted, "model:aoai-api", "publishedSurface")
        target["status"] = "adapted"
        target["decision"] = "split"

        changed = copy.deepcopy(inventory)
        model = next(m for m in changed["assets"]["models"] if m["source"]["name"] == "aoai-api")
        model["endpoints"]["surface"]["unpublishableCount"] = 99

        again = build_plan(changed, capabilities, previous=adapted)
        item = item_for(again, "model:aoai-api", "publishedSurface")
        assert item["status"] == "stale"
        assert item["decision"] == "split"
        assert "changed" in item["staleReason"]

    def test_a_member_joining_a_settled_batch_inherits_the_decision(self, inventory, capabilities, plan):
        adapted = copy.deepcopy(plan)
        batch = next(
            i for i in adapted["items"]
            if i["source"]["assetKind"] == "policy" and i["evidence"]["element"] == "set-header"
        )
        batch["status"] = "adapted"
        batch["decision"] = "accept"
        known = len(batch["memberDigests"])

        changed = copy.deepcopy(inventory)
        document = next(p for p in changed["policies"] if p["id"] == "policy:api/support-mcp")
        extra = copy.deepcopy(
            next(e for e in document["elements"] if e["name"] == "rate-limit-by-key")
        )
        extra.update({"name": "set-header", "family": "transform", "path": "inbound/set-header[9]",
                      "attributes": {"name": "x-extra"}, "expressionIds": []})
        document["elements"].append(extra)

        again = build_plan(changed, capabilities, previous=adapted)
        item = next(
            i for i in again["items"]
            if i["source"]["assetKind"] == "policy" and i["evidence"]["element"] == "set-header"
        )
        assert item["status"] == "adapted"
        assert item["decision"] == "accept"
        assert len(item["memberDigests"]) == known + 1
        assert item["newMembers"]

    def test_regeneration_is_deterministic(self, inventory, capabilities):
        def run():
            document = build_plan(inventory, capabilities)
            document.pop("generatedAt")
            return json.dumps(document, sort_keys=True)

        assert run() == run()


class TestCoverageGapCannotBeAccepted:
    def test_a_failed_read_is_unknown_not_absent(self, capabilities, inventory):
        broken = copy.deepcopy(inventory)
        broken["collection"]["coverage"].append(
            {"collection": "backends", "scope": "service", "status": "failed",
             "count": 0, "error": "403"}
        )
        document = build_plan(broken, capabilities)
        item = next(i for i in document["items"] if i["source"]["assetKind"] == "coverageGap")
        assert item["cannotAccept"] is True
        assert item["blocking"] is True
        assert "accept" not in {option["value"] for option in item["options"]}

    def test_schema_rejects_accepting_an_unknown(self, capabilities, inventory):
        broken = copy.deepcopy(inventory)
        broken["collection"]["coverage"].append(
            {"collection": "backends", "scope": "service", "status": "failed",
             "count": 0, "error": "403"}
        )
        document = build_plan(broken, capabilities)
        item = next(i for i in document["items"] if i["source"]["assetKind"] == "coverageGap")
        item["status"] = "adapted"
        item["decision"] = "accept"
        assert validate_document(document) != []


class TestSecrets:
    def test_no_secret_value_reaches_the_plan(self, plan):
        payload = json.dumps(plan)
        assert "sk-abcdefghijklmnopqrstuvwxyz01" not in payload

    def test_credentials_are_carried_as_references(self, plan):
        custom = [
            item for item in plan["items"]
            if item["capabilityId"] == "provider.create"
            and item["target"]["objects"][0].get("custom")
        ]
        assert custom
        for item in custom:
            auth = item["target"]["objects"][0]["custom"]["authentication"]
            value = auth["apiKey"]["value"]
            assert value is None or set(value) == {"$secretRef"}


class TestResume:
    """The plan file is the saved state. Picking it up later must not lose work."""

    def test_a_decision_whose_item_vanished_is_reported_not_dropped(self, inventory, capabilities, plan):
        import copy

        adapted = copy.deepcopy(plan)
        adapted["items"].append({
            "id": "item:model/gone/alias/old-shape",
            "source": {"assetId": "model:gone", "assetKind": "modelApi", "aspect": "alias:old"},
            "status": "adapted", "decision": "keep-this", "kind": "name", "verdict": "partial",
            "rationale": "", "options": [], "evidence": {}, "blocking": False,
            "shapeDigest": "x", "memberDigests": {},
        })
        again = build_plan(inventory, capabilities, previous=adapted)
        [orphan] = [o for o in again["orphanedDecisions"] if o["id"].endswith("old-shape")]
        assert orphan["decision"] == "keep-this"
        assert "no longer exists" in orphan["note"]
        assert again["summary"]["orphanedDecisions"] == 1

    def test_an_unresolved_orphan_is_carried_forward(self, inventory, capabilities, plan):
        import copy

        first = copy.deepcopy(plan)
        first["orphanedDecisions"] = [
            {"id": "item:model/gone/x", "decision": "v", "note": "n", "kind": "name"}
        ]
        again = build_plan(inventory, capabilities, previous=first)
        assert [o["id"] for o in again["orphanedDecisions"]] == ["item:model/gone/x"]

    def test_the_deployment_target_is_recorded_and_sticky(self, inventory, capabilities):
        target = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.ApiManagement/aigateways/gw"
        first = build_plan(inventory, capabilities, target=target)
        assert first["target"]["resourceId"] == target
        # A later run without --target keeps the destination rather than forgetting it.
        again = build_plan(inventory, capabilities, previous=first)
        assert again["target"]["resourceId"] == target

    def test_adapted_decisions_survive_a_plain_regeneration(self, inventory, capabilities, plan):
        import copy

        adapted = copy.deepcopy(plan)
        for item in adapted["items"]:
            if item["status"] == "needs-decision":
                item["status"] = "adapted"
                item["decision"] = item["proposal"] or "accept"
        again = build_plan(inventory, capabilities, previous=adapted)
        assert again["summary"]["byStatus"].get("needs-decision", 0) == 0
        assert again["orphanedDecisions"] == []


class TestGatewayIdentity:
    """Every Foundry provider registers with ManagedIdentity, so the gateway
    needs one before any of them is created."""

    def test_an_identity_step_is_emitted_for_managed_identity_providers(self, plan):
        item = next(i for i in plan["items"] if i["capabilityId"] == "identity.assign")
        assert item["target"]["objects"]
        assert item["evidence"]["providers"]

    def test_a_system_assigned_source_cannot_carry_its_principal_over(self, plan):
        item = next(i for i in plan["items"] if i["capabilityId"] == "identity.assign")
        assert item["proposal"] == "system-assigned"
        assert "cannot be carried" in item["rationale"]

    def test_a_user_assigned_source_proposes_reusing_it(self, inventory, capabilities):
        import copy

        changed = copy.deepcopy(inventory)
        changed["service"]["identity"] = {
            "type": "UserAssigned",
            "userAssignedIdentities": [{"resourceId": "/subscriptions/s/uami/one", "clientId": "c"}],
        }
        document = build_plan(changed, capabilities)
        item = next(i for i in document["items"] if i["capabilityId"] == "identity.assign")
        # Reusing an identity that already holds its grants makes the RBAC
        # prerequisite a no-op, which is a materially different outcome.
        assert item["proposal"] == "reuse:/subscriptions/s/uami/one"
        assert item["kind"] == "translate"
        prereq = next(p for p in document["prerequisites"] if p["id"] == "prereq:foundry-rbac")
        assert "already cover this" in prereq["detail"]

    def test_no_identity_step_when_nothing_authenticates_as_one(self, inventory, capabilities):
        import copy

        changed = copy.deepcopy(inventory)
        for provider in changed["assets"]["modelProviders"]:
            provider["auth"]["mode"] = "apiKey"
        document = build_plan(changed, capabilities)
        assert not [i for i in document["items"] if i["capabilityId"] == "identity.assign"]
