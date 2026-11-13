import copy
import json

import pytest

from migrate_apim.capability import CapabilityMap
from migrate_apim.cli import validate_document
from migrate_apim.collect import Collector, CollectOptions
from migrate_apim.plan import build_plan
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
        from migrate_apim.capability import CapabilityMap

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


class TestPrerequisiteCommands:
    """A prerequisite the plan can express as a command carries that command, so
    whoever runs it is not improvising a role name or a scope."""

    def test_the_foundry_grant_names_the_role_and_every_account(self, plan):
        prereq = next(p for p in plan["prerequisites"] if p["id"] == "prereq:foundry-rbac")
        assert prereq["commands"]
        for entry in prereq["commands"]:
            assert "Foundry User" in entry["command"]
            # The definition id pins the role even if the display name moves.
            assert entry["roleDefinitionId"] == "53ca6127-db72-4b80-b1b0-d745d6d5456d"
            assert "/providers/Microsoft.CognitiveServices/accounts/" in entry["scope"]

    def test_the_principal_is_late_bound(self, plan):
        prereq = next(p for p in plan["prerequisites"] if p["id"] == "prereq:foundry-rbac")
        entry = prereq["commands"][0]
        # It does not exist until the identity phase has run.
        assert "<gateway-principal-id>" in entry["command"]
        assert "identity phase" in entry["principalFrom"]

    def test_the_caller_grant_names_a_real_role(self, plan):
        prereq = next(p for p in plan["prerequisites"] if p["id"] == "prereq:caller-rbac")
        assert prereq["commands"][0]["roleDefinitionId"] == "a6b68e3d-a1f0-4c60-8678-237c050cf4ea"

    def test_a_prerequisite_without_a_command_claims_none(self, plan):
        # Name collision is a check, not a grant; inventing a command would be worse
        # than leaving it to a human.
        prereq = next(p for p in plan["prerequisites"] if p["id"] == "prereq:name-collision")
        assert "commands" not in prereq


def settle_models(plan, *, models, value="list-models"):
    """Settle the meta-ai catalogue item the way an agent would."""
    adapted = copy.deepcopy(plan)
    item = item_for(adapted, "model:meta-ai", "modelCatalogue")
    item["status"] = "adapted"
    item["decision"] = {"value": value, "models": models}
    return adapted


class TestSettledEnumeration:
    """A decision that names models has to turn into models.

    The question is only worth asking if the answer is built from. Raising it
    and then ignoring what came back left a provider that published nothing,
    with every item reading as settled.
    """

    def test_named_models_become_registrations(self, inventory, capabilities, plan):
        adapted = settle_models(plan, models=["muse-spark-1.1", "muse-ember-1.0"])

        again = build_plan(inventory, capabilities, previous=adapted)
        objects = [
            obj
            for item in again["items"] if item["source"].get("assetId") == "model:meta-ai"
            for obj in (item.get("target") or {}).get("objects") or []
            if item["capabilityId"] == "model.create"
        ]
        assert [obj["name"] for obj in objects] == ["muse-spark-1.1", "muse-ember-1.0"]
        assert {obj["apiFormat"] for obj in objects} == {"OpenAIChatCompletions"}
        # A Custom provider has no backing ARM deployment; the model name is all
        # a registration carries, as a live gateway reads one back.
        assert objects[0]["deploymentConfig"] == {"modelName": "muse-spark-1.1"}
        assert objects[0]["supportedEndpoints"] == ["/openai/v1/chat/completions"]

    def test_named_models_become_callable_aliases(self, inventory, capabilities, plan):
        adapted = settle_models(plan, models=["muse-spark-1.1"])

        again = build_plan(inventory, capabilities, previous=adapted)
        aliases = item_for(again, "model:meta-ai", "aliasNames")
        assert [obj["routingName"] for obj in aliases["target"]["objects"]] == ["muse-spark-1.1"]

    def test_registrations_are_buildable(self, inventory, capabilities, plan):
        adapted = settle_models(plan, models=["muse-spark-1.1"])

        again = build_plan(inventory, capabilities, previous=adapted)
        assert again["summary"]["plannerGaps"] == 0

    def test_a_per_model_route_override_is_honoured(self, inventory, capabilities, plan):
        adapted = settle_models(plan, models=["muse-embed-1.0"])
        item = item_for(adapted, "model:meta-ai", "modelCatalogue")
        item["decision"]["endpoints"] = {"muse-embed-1.0": ["/openai/v1/embeddings"]}

        again = build_plan(inventory, capabilities, previous=adapted)
        model = item_for(again, "model:meta-ai", "model:muse-embed-1.0")
        assert model["target"]["objects"][0]["supportedEndpoints"] == ["/openai/v1/embeddings"]

    def test_retaining_the_api_creates_nothing_and_is_not_a_gap(
        self, inventory, capabilities, plan
    ):
        adapted = settle_models(plan, models=[], value="retain-in-apim")
        for item in adapted["items"]:
            if item["source"].get("assetId") == "model:meta-ai":
                item["status"], item["decision"] = "adapted", "retain-in-apim"

        again = build_plan(inventory, capabilities, previous=adapted)
        assert not [
            i for i in again["items"]
            if i["source"].get("assetId") == "model:meta-ai"
            and (i.get("target") or {}).get("objects")
        ]
        assert again["plannerGaps"] == []

    def test_migrating_while_naming_nothing_is_a_gap(self, inventory, capabilities, plan):
        adapted = settle_models(plan, models=[])

        again = build_plan(inventory, capabilities, previous=adapted)
        item = item_for(again, "model:meta-ai", "modelCatalogue")
        assert "names no models" in item["plannerGap"]
        assert again["summary"]["plannerGaps"] >= 1

    def test_an_unreadable_protocol_is_a_gap_not_a_guess(self, inventory, capabilities, plan):
        # Defaulting the routes here would publish models against a protocol
        # nobody established.
        blinded = copy.deepcopy(inventory)
        for provider in blinded["assets"]["modelProviders"]:
            if "meta-ai" in provider["id"]:
                provider["apiDialect"] = None
        adapted = settle_models(plan, models=["muse-spark-1.1"])

        again = build_plan(blinded, capabilities, previous=adapted)
        item = item_for(again, "model:meta-ai", "modelCatalogue")
        assert "could not be resolved" in item["plannerGap"]
        assert not [
            obj
            for i in again["items"] if i["source"].get("assetId") == "model:meta-ai"
            for obj in (i.get("target") or {}).get("objects") or []
        ]


class TestUnbuildableObjects:
    """An object short of a required flag is caught while it can still be fixed."""

    def test_a_model_without_its_required_fields_is_reported(self, inventory, capabilities):
        blinded = copy.deepcopy(inventory)
        for model in blinded["assets"]["models"]:
            for resolved in (model.get("models") or {}).get("resolved") or []:
                resolved.get("target", {})["supportedEndpoints"] = []

        again = build_plan(blinded, capabilities)
        offenders = [i for i in again["items"] if i.get("unbuildable")]
        assert offenders, "a model with no routes cannot be created and must say so"
        assert "--supported-endpoints" in offenders[0]["unbuildable"]["note"]
        assert again["summary"]["plannerGaps"] >= len(offenders)

    def test_a_complete_plan_reports_no_gaps(self, plan):
        assert plan["summary"]["plannerGaps"] == 0

    def test_required_fields_mirror_the_apply_builders(self):
        # The planner can only vouch for what apply actually demands; drift
        # between the two tables would quietly stop checking something.
        from migrate_apim.apply import _REQUIRED_FLAGS
        from migrate_apim.plan import _REQUIRED_FIELDS

        assert set(_REQUIRED_FIELDS) == set(_REQUIRED_FLAGS)
        for capability_id, flags in _REQUIRED_FLAGS.items():
            assert set(_REQUIRED_FIELDS[capability_id]) == set(flags), capability_id


class TestBatchMembersAreTrackedIndividually:
    """A batch keeps one digest per member, under a name that identifies it."""

    def test_each_model_member_gets_its_own_key(self, plan):
        from migrate_apim.plan import _member_digests

        aliases = next(i for i in plan["items"] if i["id"].endswith("/aliasNames")
                       and len(i["evidence"]["members"]) > 1)
        digests = _member_digests(aliases)
        assert len(digests) == len(aliases["evidence"]["members"])
        assert "None#None" not in digests
        assert set(digests) == {m["modelName"] for m in aliases["evidence"]["members"]}

    def test_a_change_to_any_member_is_noticed(self, inventory, capabilities, plan):
        # Every member used to share one key, so only the last one was compared
        # and a change to any other was invisible.
        adapted = copy.deepcopy(plan)
        target = next(i for i in adapted["items"] if i["id"].endswith("/aliasNames")
                      and len(i["evidence"]["members"]) > 1)
        target["status"], target["decision"] = "adapted", "use-model-names"

        changed = copy.deepcopy(inventory)
        first = target["evidence"]["members"][0]["modelName"]
        for model in changed["assets"]["models"]:
            for resolved in (model.get("models") or {}).get("resolved") or []:
                if resolved.get("modelName") == first:
                    resolved["target"]["supportedEndpoints"] = ["/openai/v1/embeddings"]

        again = build_plan(changed, capabilities, previous=adapted)
        item = next(i for i in again["items"] if i["id"] == target["id"])
        assert item["status"] == "stale"
        assert first in item["staleReason"]

    def test_the_stale_reason_names_the_member(self, plan):
        from migrate_apim.plan import _member_digests

        policies = [i for i in plan["items"] if i["id"].startswith("item:policy/")
                    and i.get("evidence", {}).get("members")]
        for item in policies:
            assert all("#" in key for key in _member_digests(item)), item["id"]


class TestTheSummaryShowsBadNews:
    """A view that omits what will not happen reads as a clean bill of health."""

    def test_planner_gaps_appear_in_the_rendered_plan(self, plan):
        from migrate_apim.summary import render_plan

        gapped = copy.deepcopy(plan)
        gapped["plannerGaps"] = [{"id": "item:model/x/models", "gap": "names no models"}]
        rendered = render_plan(gapped)
        assert "Will not happen as planned (1)" in rendered
        assert "names no models" in rendered

    def test_orphaned_decisions_appear_in_the_rendered_plan(self, plan):
        from migrate_apim.summary import render_plan

        orphaned = copy.deepcopy(plan)
        orphaned["orphanedDecisions"] = [{"id": "item:gone", "decision": "split", "note": "n"}]
        rendered = render_plan(orphaned)
        assert "Settled decisions with no item (1)" in rendered
        assert "item:gone" in rendered

    def test_a_clean_plan_says_neither(self, plan):
        from migrate_apim.summary import render_plan

        rendered = render_plan(plan)
        assert "Will not happen as planned" not in rendered
        assert "Settled decisions with no item" not in rendered


class TestAProbeThatCouldNotRun:
    """An unanswerable probe is not evidence the CLI lacks a command."""

    def test_a_timeout_raises_rather_than_demoting_the_catalogue(self):
        import subprocess
        from migrate_apim.capability import CapabilityError, az_option_probe

        def _boom(*_a, **_k):
            raise subprocess.TimeoutExpired(cmd="az", timeout=30)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(subprocess, "run", _boom)
            with pytest.raises(CapabilityError, match="unknown"):
                az_option_probe(["model", "create"])

    def test_a_command_the_cli_does_not_expose_is_still_unavailable(self, capabilities):
        probed = CapabilityMap.load().probe(probe=lambda _c: None, available=lambda: True)
        assert all(c.support == "unavailable" for c in probed.capabilities.values())


class TestLoadBalancedPool:
    """An APIM backend pool is what an AI Gateway alias was built for.

    The target takes 1-30 backend models per alias with a priority and a
    weight, which is exactly an APIM pool. Collapsing it to the first member
    dropped the second upstream and the traffic split with it, and the result
    read like an ordinary single-backend API.
    """

    def pooled(self, plan):
        return next(i for i in plan["items"]
                    if i["id"] == "item:model/aoai-api/aliasNames")

    def test_the_api_routes_to_a_pool(self, inventory):
        asset = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "aoai-api")
        assert asset["routing"]["mode"] == "pool"
        assert [t["weight"] for t in asset["routing"]["targets"]] == [80, 20]

    def test_a_shared_model_becomes_one_alias_over_both_members(self, plan):
        alias = next(o for o in self.pooled(plan)["target"]["objects"]
                     if o["routingName"] == "gpt-5")
        backends = alias["backendModels"]
        assert len(backends) == 2, "the model is deployed in both accounts"
        assert {b["providerName"] for b in backends} == {"aoai-east", "aoai-west"}

    def test_the_pool_weights_survive(self, plan):
        alias = next(o for o in self.pooled(plan)["target"]["objects"]
                     if o["routingName"] == "gpt-5")
        by_provider = {b["providerName"]: b for b in alias["backendModels"]}
        assert (by_provider["aoai-east"]["priority"], by_provider["aoai-east"]["weight"]) == (1, 80)
        assert (by_provider["aoai-west"]["priority"], by_provider["aoai-west"]["weight"]) == (2, 20)

    def test_each_member_registers_its_own_copy_of_the_model(self, plan):
        registrations = [
            (i["target"]["objects"][0]["name"], i["target"]["objects"][0]["providerName"])
            for i in plan["items"]
            if i.get("capabilityId") == "model.create"
            and i["source"]["assetId"] == "model:aoai-api"
        ]
        assert ("gpt-5", "aoai-east") in registrations
        assert ("gpt-5", "aoai-west") in registrations
        # Same gateway-visible name under two providers: only the item id differs.
        assert len({r[1] for r in registrations}) == 2

    def test_a_model_in_one_member_only_is_called_out(self, plan):
        item = self.pooled(plan)
        assert item["evidence"]["pooled"] is True
        # text-embedding-3-large is deployed in the east account alone.
        assert "text-embedding-3-large" in item["evidence"]["singleMemberModels"]
        assert "only one member" in item["rationale"]

    def test_an_unpooled_api_is_unchanged(self, plan):
        for item in plan["items"]:
            if item.get("kind") != "name" or item["source"]["assetId"] == "model:aoai-api":
                continue
            for obj in item["target"]["objects"]:
                assert len(obj["backendModels"]) == 1
                assert (obj["backendModels"][0]["priority"],
                        obj["backendModels"][0]["weight"]) == (0, 100)


class TestPolicyRoutedBackend:
    """An API whose backend is named only by policy still has a backend."""

    def test_a_single_set_backend_service_resolves(self):
        from migrate_apim.collect import policy_routed_backends

        elements = [{"name": "set-backend-service", "attributes": {"backend-id": "aoai-pool"}}]
        assert policy_routed_backends(elements) == ["aoai-pool"]

    def test_a_runtime_expression_is_not_a_backend_name(self):
        from migrate_apim.collect import policy_routed_backends

        elements = [{"name": "set-backend-service",
                     "attributes": {"backend-id": "@(context.Variables[\"b\"])"}}]
        assert policy_routed_backends(elements) == []

    def test_several_candidates_are_reported_rather_than_guessed(self):
        from migrate_apim.collect import _resolve_backend

        elements = [
            {"name": "set-backend-service", "attributes": {"backend-id": "east"}},
            {"name": "set-backend-service", "attributes": {"backend-id": "west"}},
        ]
        record, candidates = _resolve_backend({}, {"east": {"id": "x"}}, {}, None, elements)
        assert record is None
        assert candidates == ["east", "west"]


class TestServiceOnlyCapabilities:
    """A missing CLI flag is not a missing feature.

    The catalogue is built by probing `az aigateway`, so a capability the
    gateway has and the CLI cannot author is structurally invisible to it --
    which is how session affinity went unrecorded while the control plane
    accepted it. `serviceOnly` holds those, apart from `unsupported`: one means
    the workload cannot move, the other that it moves by hand afterwards.
    """

    def test_the_catalogue_separates_them(self, capabilities):
        ids = {entry["id"] for entry in capabilities.service_only}
        assert "alias-session-affinity" in ids
        assert "alias-auto-model-selection" in ids
        assert "alias-selection-order" in ids
        # Not lumped in with things the target genuinely cannot do.
        assert not ids & set(capabilities.unsupported)

    def test_each_entry_says_how_it_was_established(self, capabilities):
        for entry in capabilities.service_only:
            assert entry.get("evidence"), entry["id"]
            assert entry.get("cliGap"), entry["id"]
            assert entry.get("authoring") == "armOnly", entry["id"]

    def test_an_entry_we_cannot_author_says_so(self, capabilities):
        # Recording a shape without a working example is the thing to avoid.
        affinity = capabilities.service_only_entry("alias-session-affinity")
        assert affinity["incomplete"] == "key syntax unresolved"
        assert "NOT established" in affinity["evidence"]


class TestPoolSessionAffinity:
    def _with_affinity(self, inventory, value):
        changed = copy.deepcopy(inventory)
        asset = next(m for m in changed["assets"]["models"] if m["source"]["name"] == "aoai-api")
        asset["routing"]["sessionAffinity"] = value
        return changed

    def test_a_pool_without_affinity_raises_nothing(self, plan):
        assert not [i for i in plan["items"] if i["source"]["aspect"] == "sessionAffinity"]

    def test_a_pool_using_affinity_is_reported_as_a_loss(self, inventory, capabilities):
        changed = self._with_affinity(inventory, {"enabled": True})
        built = build_plan(changed, capabilities)
        item = next(i for i in built["items"] if i["source"]["aspect"] == "sessionAffinity")
        assert item["kind"] == "accept-loss"
        assert item["blocking"] is True
        assert {o["value"] for o in item["options"]} == {"accept-loss", "retain-in-apim", "block"}

    def test_it_says_the_target_can_do_it_and_the_tool_cannot(self, inventory, capabilities):
        built = build_plan(self._with_affinity(inventory, {"enabled": True}), capabilities)
        item = next(i for i in built["items"] if i["source"]["aspect"] == "sessionAffinity")
        assert item["evidence"]["targetSupports"] is True
        assert item["evidence"]["targetProperty"] == "aliases.properties.sessionBackendPreference"
        # The consequence, not just the fact.
        assert "move between backends" in item["rationale"]
        assert ".," not in item["rationale"] and "but No flag" not in item["rationale"]

    def test_the_apim_setting_is_carried_as_evidence(self, inventory, capabilities):
        built = build_plan(self._with_affinity(inventory, {"enabled": True}), capabilities)
        item = next(i for i in built["items"] if i["source"]["aspect"] == "sessionAffinity")
        assert item["evidence"]["apimSessionAffinity"] == {"enabled": True}


class TestWorkThisToolCannotAuthor:
    """The third answer to "can this be migrated?", and the one that read as a lie.

    An agent asked why the policies never got configured had to read `apply.py`
    to find out: the plan proposed `model.policy`, the operator settled it, the
    summary counted it ready, and the phase that was supposed to carry it ran no
    steps. The gateway supports it and so does the installed CLI -- only this
    tool does not, and that is the plan's fact to state, not apply's to discover.
    """

    @pytest.fixture
    def settled(self, inventory, capabilities):
        """A plan taken through the documented loop: settle, then re-run `plan`."""
        first = build_plan(copy.deepcopy(inventory), capabilities)
        for item in first["items"]:
            if item["status"] == "needs-decision":
                item["status"] = "adapted"
                item["decision"] = item["proposal"] or "accept"
        return build_plan(copy.deepcopy(inventory), capabilities, previous=first)

    def test_settled_work_with_no_builder_says_so_on_the_item(self, settled):
        from migrate_apim.apply import AUTHORED_HERE, PHASE_FOR_CAPABILITY

        unbuildable = [
            item for item in settled["items"]
            if item.get("capabilityId") in PHASE_FOR_CAPABILITY
            and item["capabilityId"] not in AUTHORED_HERE
            and (item.get("target") or {}).get("objects")
        ]
        assert unbuildable, "the fixture should settle work this tool has no builder for"
        for item in unbuildable:
            assert item.get("appliedByHand"), item["id"]
            assert "no builder" in item["appliedByHand"]["reason"]
            assert "cannot author it" in item["rationale"], item["rationale"]

    def test_it_names_the_command_the_operator_has_to_run(self, settled):
        item = next(i for i in settled["items"]
                    if i.get("capabilityId") == "model.policy" and i.get("appliedByHand"))
        # Read off the catalogue rather than composed here: the point is to spare
        # whoever reads this plan the reconstruction, not to guess at flags.
        assert item["appliedByHand"]["command"] == "az aigateway model policy set"
        assert item["appliedByHand"]["phase"] == "policies"

    def test_an_unsettled_item_says_it_while_the_decision_is_still_open(self, plan):
        """Choosing counter semantics for a policy nobody will author is wasted work."""
        item = next(i for i in plan["items"]
                    if i.get("capabilityId") == "model.policy"
                    and i["status"] == "needs-decision")
        assert "However this is settled" in item["rationale"], item["rationale"]
        # Not the settled marker: which way it goes is still open.
        assert "appliedByHand" not in item

    def test_an_item_this_tool_can_build_is_not_marked(self, settled):
        item = next(i for i in settled["items"] if i.get("capabilityId") == "model.create")
        assert "appliedByHand" not in item
        assert "no builder" not in item["rationale"]

    def test_the_plan_is_still_schema_valid(self, settled):
        assert validate_document(settled) == []

    def test_the_summary_separates_it_from_what_apply_will_do(self, settled):
        from migrate_apim.summary import render_plan

        rendered = render_plan(settled)
        assert "az aigateway model policy set" in rendered
        by_hand = [i for i in settled["items"] if i.get("appliedByHand")]
        ready = [i for i in settled["items"]
                 if i["status"] == "ready" and not i.get("appliedByHand")]
        # The count under "Ready to execute" is a claim about what apply will do.
        assert f"Ready to execute ({len(ready)})" in rendered
        assert f"Applied by hand ({len(by_hand)})" in rendered

    def test_apply_and_the_plan_agree_on_what_is_by_hand(self, settled):
        """Two sources of truth for one fact is how it drifted in the first place."""
        from migrate_apim.apply import unperformable_for

        assert {e["itemId"] for e in unperformable_for(settled)} == \
            {i["id"] for i in settled["items"] if i.get("appliedByHand")}
