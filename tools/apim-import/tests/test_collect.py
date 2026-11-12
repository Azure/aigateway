import json

import pytest

from apim_import.cli import validate_inventory
from apim_import.collect import Collector, CollectOptions
from fake_arm import SERVICE, FakeArmClient


def options(**overrides):
    """Collector options that never shell out to the Azure CLI.

    Leaving cognitive_api_version unset makes FoundryResolver ask `az provider
    show` for the newest version, which turns a unit test into a network call.
    """
    overrides.setdefault("cognitive_api_version", "2025-06-01")
    return CollectOptions(**overrides)


@pytest.fixture(scope="module")
def inventory():
    client = FakeArmClient()
    return Collector(client, SERVICE, options()).run()


class TestDocument:
    def test_is_schema_valid(self, inventory):
        assert validate_inventory(inventory) == []

    def test_is_json_serializable(self, inventory):
        assert json.loads(json.dumps(inventory))["kind"] == "apimAiInventory"

    def test_records_the_service_shape(self, inventory):
        service = inventory["service"]
        assert service["sku"]["name"] == "StandardV2"
        assert service["identity"]["type"] == "SystemAssigned"

    def test_records_coverage_for_every_collection_read(self, inventory):
        collections = {entry["collection"] for entry in inventory["collection"]["coverage"]}
        assert {"apis", "backends", "namedValues", "products", "subscriptions"} <= collections


class TestAssets:
    def test_classifies_each_api_family(self, inventory):
        assets = inventory["assets"]
        assert sorted(asset["source"]["name"] for asset in assets["models"]) == [
            "aoai-api", "meta-ai", "model-api"
        ]
        assert sorted(asset["source"]["name"] for asset in assets["mcpServers"]) == ["orders-mcp", "support-mcp"]
        assert [asset["source"]["name"] for asset in assets["agents"]] == ["support-agent"]

    def test_excludes_the_plain_rest_api_with_a_reason(self, inventory):
        excluded = {entry["name"]: entry for entry in inventory["excludedApis"]}
        assert "orders-rest" in excluded
        # It backs the tool projection, so it is flagged as a dependency rather than noise.
        assert excluded["orders-rest"]["reason"] == "notAnAiAssetButReferencedByOne"
        assert excluded["orders-rest"]["referencedBy"] == ["mcp:orders-mcp"]

    def test_expands_a_backend_pool_into_weighted_targets(self, inventory):
        model = inventory["assets"]["models"][0]
        assert model["routing"]["mode"] == "pool"
        targets = {target["backendId"]: target for target in model["routing"]["targets"]}
        assert targets["backend:aoai-east"]["priority"] == 1
        assert targets["backend:aoai-east"]["weight"] == 80
        assert targets["backend:aoai-west"]["weight"] == 20

    def test_resolves_foundry_deployments_from_arm(self, inventory):
        provider = next(
            entry for entry in inventory["assets"]["modelProviders"] if entry["providerKind"] == "foundry"
        )
        assert provider["models"]["status"] == "resolved"
        assert provider["models"]["discoverySource"] == "armDeployments"
        [model] = provider["models"]["resolved"]
        assert (model["modelName"], model["modelVersion"]) == ("gpt-5.2", "2025-12-11")
        # Pre-shaped for an AI Gateway model registration.
        assert model["target"]["deployment"]["resourceId"].endswith("/deployments/gpt-5")
        assert model["target"]["providerKind"] == "Foundry"

    def test_detects_managed_identity_as_the_backend_auth_mode(self, inventory):
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "aoai-api")
        assert model["provider"]["auth"]["mode"] == "managedIdentity"
        assert "policy:authentication-managed-identity" in model["provider"]["auth"]["evidence"]

    def test_reads_managed_identity_from_undocumented_backend_credentials(self, inventory):
        # The published ARM schema omits credentials.managedIdentity; the live
        # service returns it, and it is how the portal wires a Foundry backend.
        provider = next(
            p for p in inventory["assets"]["modelProviders"] if p["providerKind"] == "foundry"
        )
        auth = provider["auth"]
        assert auth["mode"] == "managedIdentity"
        assert auth["identity"] == {
            "type": "systemAssigned", "clientId": None,
            "audience": "https://cognitiveservices.azure.com/",
        }
        assert "backend.credentials.managedIdentity" in auth["evidence"]
        assert any(ref.startswith("secret:managedIdentity/") for ref in auth["secretRefs"])

    def test_managed_identity_does_not_discard_other_credential_references(self, inventory):
        # Regression: the secretRefs list used to be overwritten after the
        # identity reference was added.
        provider = next(
            p for p in inventory["assets"]["modelProviders"] if p["providerKind"] == "foundry"
        )
        assert len(provider["auth"]["secretRefs"]) >= 1
        assert provider["auth"]["modes"] == ["managedIdentity"]

    def test_management_uri_resource_id_is_normalized_to_an_arm_id(self, inventory):
        backend = next(b for b in inventory["shared"]["backends"] if b["name"] == "aoai-east")
        assert backend["resourceIdRef"].startswith("/subscriptions/")
        assert "management.azure.com" not in backend["resourceIdRef"]

    def test_model_api_is_found_by_apim_ai_import_naming_alone(self, inventory):
        # No provider host match, no inference path, no LLM policy: only the
        # '-openai-endpoint' backend and '-LLM' named value give it away.
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "meta-ai")
        assert model["detection"]["confidence"] == "medium"
        signals = {signal["type"] for signal in model["detection"]["signals"]}
        assert signals == {"backendNaming", "namedValueNaming"}

    def test_unrecognized_provider_is_reported_as_unknown_not_guessed(self, inventory):
        provider = next(
            p for p in inventory["assets"]["modelProviders"]
            if p["origin"].get("backendName") == "meta-ai-openai-endpoint"
        )
        assert provider["providerKind"] == "unknown"
        assert provider["targetProviderKind"] == "Custom"
        assert provider["models"]["status"] == "unresolved"
        assert "Confirm the provider" in " ".join(provider["models"]["notes"])

    def test_passthrough_mcp_marks_tools_as_runtime_only(self, inventory):
        server = next(a for a in inventory["assets"]["mcpServers"] if a["source"]["name"] == "support-mcp")
        assert server["pattern"] == "passthrough"
        assert server["toolDiscovery"]["status"] == "runtimeOnly"
        assert server["upstream"][0]["url"] == "https://support.contoso.com:8000"

    def test_tool_projection_resolves_tools_and_upstream(self, inventory):
        server = next(a for a in inventory["assets"]["mcpServers"] if a["source"]["name"] == "orders-mcp")
        assert server["pattern"] == "toolProjection"
        assert [tool["name"] for tool in server["tools"]] == ["list_orders"]
        assert server["toolDiscovery"]["status"] == "complete"
        assert server["sourceApiIds"] == ["api:orders-rest"]
        assert server["upstream"][0]["url"] == "https://orders.contoso.com"

    def test_tool_projection_carries_an_openapi_export_recipe(self, inventory):
        server = next(a for a in inventory["assets"]["mcpServers"] if a["source"]["name"] == "orders-mcp")
        recipe = server["openApiSources"][0]["exportRecipe"]
        assert recipe["valuePath"] == "$.link"
        assert "export=true&format=openapi%2Bjson-link" in recipe["request"]["url"]

    def test_links_assets_to_their_access_path(self, inventory):
        model = inventory["assets"]["models"][0]
        assert model["access"]["productIds"] == ["product:ai"]
        vias = {entry["via"] for entry in model["access"]["subscriptions"]}
        assert vias == {"product", "service"}


class TestAgents:
    def test_a2a_api_is_classified_as_an_agent(self, inventory):
        [agent] = inventory["assets"]["agents"]
        assert agent["source"]["name"] == "support-agent"
        assert agent["source"]["type"] == "a2a"
        assert agent["detection"]["confidence"] == "high"

    def test_upstream_comes_from_json_rpc_properties(self, inventory):
        # Regression: backendId and serviceUrl are both null on an A2A API, so
        # the usual backend resolution produced an empty upstream.
        [agent] = inventory["assets"]["agents"]
        [upstream] = agent["upstream"]
        assert upstream["source"] == "jsonRpcProperties"
        assert upstream["transport"] == "jsonRpc"
        assert upstream["url"].endswith("/endpoint/protocols/a2a/")
        assert upstream["path"] == "/"

    def test_foundry_hosted_agent_resolves_its_project_and_account(self, inventory):
        [agent] = inventory["assets"]["agents"]
        hosting = agent["hosting"]
        assert hosting["kind"] == "foundry"
        assert (hosting["project"], hosting["agentId"]) == ("default-project", "support-bot")
        assert hosting["azure"]["accountName"] == "aif"

    def test_agent_card_is_a_location_not_content(self, inventory):
        [agent] = inventory["assets"]["agents"]
        card = agent["agentCard"]
        assert card["exposedPath"] == "/agent-card.json"
        assert card["backendUrl"].endswith("/.well-known/agent-card.json")
        assert card["discovery"]["status"] == "runtimeOnly"

    def test_raw_preview_properties_are_kept_verbatim(self, inventory):
        [agent] = inventory["assets"]["agents"]
        assert agent["a2a"]["jsonRpcProperties"]["BackendUrl"]
        assert agent["agent"]["id"] == "support-bot"

    def test_agent_is_reported_as_having_no_target(self, inventory):
        [agent] = inventory["assets"]["agents"]
        assert "does not yet expose an A2A building block" in agent["note"]


class TestWorkspaces:
    def test_workspaces_are_collected_by_default(self, inventory):
        # A workspace can hold model APIs of its own; skipping it by default
        # would silently under-report the migration.
        [workspace] = inventory["workspaces"]
        assert workspace["name"] == "finance"
        assert workspace["collected"] is True
        assert workspace["serveOn"] == "workspaceAndDefault"

    def test_workspace_assets_are_scoped_in_their_ids(self, inventory):
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "model-api")
        assert model["id"] == "model:finance/model-api"
        assert model["workspace"] == "finance"
        backend = next(b for b in inventory["shared"]["backends"] if b["name"] == "claude-backend")
        assert backend["id"] == "backend:finance/claude-backend"

    def test_workspace_scope_can_be_disabled(self):
        document = Collector(FakeArmClient(), SERVICE, options(workspaces=["none"])).run()
        assert [w["collected"] for w in document["workspaces"]] == [False]
        assert not any(m["workspace"] == "finance" for m in document["assets"]["models"])

    def test_unknown_workspace_name_is_reported(self):
        document = Collector(FakeArmClient(), SERVICE, options(workspaces=["nope"])).run()
        codes = {warning["code"] for warning in document["collection"]["warnings"]}
        assert "workspaceNotFound" in codes


class TestUnifiedModelApi:
    def test_is_classified_deterministically_from_the_api_type(self, inventory):
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "model-api")
        assert model["pattern"] == "unifiedModelApi"
        assert model["detection"]["confidence"] == "high"
        assert [s["type"] for s in model["detection"]["signals"]] == ["apiType"]

    def test_language_model_backend_declares_the_model(self, inventory):
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "model-api")
        assert model["models"]["status"] == "declared"
        assert model["models"]["discoverySource"] == "backendLanguageModel"
        [resolved] = model["models"]["resolved"]
        assert resolved["modelName"] == "claude-opus-5"
        assert resolved["apiFormat"] == "anthropic-messages"
        assert resolved["formatResolution"] == "verified"
        assert resolved["target"]["supportedEndpoints"] == ["/v1/messages"]

    def test_declared_format_overrides_the_host_heuristic(self, inventory):
        # The host is a Foundry one, but the backend speaks the Anthropic
        # protocol, so the target provider is Custom rather than Foundry.
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "model-api")
        assert model["provider"]["targetProviderKind"] == "Custom"
        assert model["provider"]["apiDialect"] == "anthropicMessages"

    def test_dialect_translation_is_flagged_as_a_gap(self, inventory):
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "model-api")
        translation = model["endpoints"]["translation"]
        assert translation["status"] == "translating"
        assert translation["inbound"] == ["openAIChatCompletions"]
        assert translation["backend"] == ["anthropicMessages"]
        assert "native endpoint" in translation["note"]

    def test_inbound_dialect_records_that_it_is_inferred(self, inventory):
        # Operation URL templates are operator-configured, so the inbound side is
        # evidence while the backend side is a declaration.
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "model-api")
        endpoints = model["endpoints"]
        assert endpoints["inboundDialectsInferredFrom"] == "operationTemplates"
        assert endpoints["backendDialectsDeclared"] is True
        assert model["endpoints"]["translation"]["basis"]["inboundFrom"] == "operationTemplates"

    def test_unreadable_inbound_dialect_is_indeterminate_not_absent(self):
        # Regression: a wildcard route yielded no inbound dialect, which used to
        # drop the translation block entirely and hide a real gap.
        import fake_arm

        key = f"{SERVICE}/workspaces/finance/apis/model-api/operations"
        original = fake_arm.ROUTES[key]
        fake_arm.ROUTES[key] = [
            {"id": "op", "name": "op",
             "properties": {"displayName": "passthrough", "method": "POST", "urlTemplate": "/*"}}
        ]
        try:
            document = Collector(FakeArmClient(), SERVICE, options()).run()
        finally:
            fake_arm.ROUTES[key] = original
        model = next(m for m in document["assets"]["models"] if m["source"]["name"] == "model-api")
        translation = model["endpoints"]["translation"]
        assert translation["status"] == "indeterminate"
        assert translation["inbound"] == []
        assert translation["backend"] == ["anthropicMessages"]
        assert "Confirm it with the operator" in translation["note"]

    def test_matching_dialects_report_native_routing(self):
        import fake_arm

        key = f"{SERVICE}/workspaces/finance/apis/model-api/operations"
        original = fake_arm.ROUTES[key]
        fake_arm.ROUTES[key] = [
            {"id": "op", "name": "op",
             "properties": {"displayName": "messages", "method": "POST", "urlTemplate": "/v1/messages"}}
        ]
        try:
            document = Collector(FakeArmClient(), SERVICE, options()).run()
        finally:
            fake_arm.ROUTES[key] = original
        model = next(m for m in document["assets"]["models"] if m["source"]["name"] == "model-api")
        assert model["endpoints"]["translation"]["status"] == "native"

    def test_no_translation_block_without_a_declared_backend_dialect(self, inventory):
        # Nothing to compare against: silence here is correct, not an omission.
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "meta-ai")
        assert model["endpoints"]["translation"] is None
        assert model["endpoints"]["backendDialectsDeclared"] is False

    def test_unverified_format_is_marked_inferred(self):
        from apim_import import detect

        verified = detect.language_model_format("anthropic-messages")
        assert verified["resolution"] == "verified"
        inferred = detect.language_model_format("azure-openai-chat")
        assert inferred["resolution"] == "inferred"
        assert inferred["targetProviderKind"] == "Foundry"
        unknown = detect.language_model_format("some-future-format")
        assert unknown["resolution"] == "unknown"
        assert unknown["supportedEndpoints"] is None


class TestSecrets:
    def test_no_secret_value_reaches_the_document(self, inventory):
        payload = json.dumps(inventory)
        assert "sk-abcdefghijklmnopqrstuvwxyz01" not in payload

    def test_inline_backend_credential_becomes_a_reference(self, inventory):
        backend = next(b for b in inventory["shared"]["backends"] if b["name"] == "support-backend")
        assert backend["credentials"]["header"]["x-api-key"][0].startswith("${secret:backendInline/")
        ref = next(s for s in inventory["secrets"] if s["class"] == "apimBackendInlineCredential")
        assert ref["retrievable"] is True
        assert ref["resolution"]["method"] == "armRead"

    def test_named_value_reference_is_preserved_verbatim(self, inventory):
        backend = next(b for b in inventory["shared"]["backends"] if b["name"] == "aoai-west")
        assert backend["credentials"]["header"]["api-key"] == ["{{aoai-key}}"]
        assert "secret:namedValue/aoai-key" in backend["secretRefs"]

    def test_non_secret_named_value_keeps_its_value(self, inventory):
        entry = next(n for n in inventory["shared"]["namedValues"] if n["name"] == "MCP-KILLSWITCH")
        assert entry["value"] == "off"
        assert entry["secretRef"] is None

    def test_secret_named_value_has_no_value_but_has_a_recipe(self, inventory):
        entry = next(n for n in inventory["shared"]["namedValues"] if n["name"] == "aoai-key")
        assert entry["value"] is None
        ref = next(s for s in inventory["secrets"] if s["id"] == entry["secretRef"])
        assert ref["resolution"]["request"]["url"].endswith("/namedValues/aoai-key/listValue?api-version=2025-09-01-preview")

    def test_every_secret_is_either_retrievable_or_explains_why_not(self, inventory):
        for ref in inventory["secrets"]:
            if ref["retrievable"]:
                assert ref["resolution"] is not None
            else:
                assert ref["notes"], f"{ref['id']} is unretrievable with no guidance"

    def test_subscription_keys_are_referenced_not_read(self, inventory):
        refs = [s for s in inventory["secrets"] if s["class"] == "apimSubscriptionKey"]
        assert {ref["id"] for ref in refs} == {
            "secret:subscriptionKey/team-a", "secret:subscriptionKey/master"
        }
        assert all(ref["resolution"]["request"]["httpMethod"] == "POST" for ref in refs)


class TestPolicies:
    def test_captures_every_scope_it_reads(self, inventory):
        levels = {document["scope"]["level"] for document in inventory["policies"]}
        assert {"api", "fragment"} <= levels

    def test_normalizes_llm_policies_into_families(self, inventory):
        document = next(p for p in inventory["policies"] if p["id"] == "policy:api/aoai-api")
        families = {element["family"] for element in document["elements"]}
        assert {"tokenLimit", "tokenMetrics", "semanticCache", "backendAuthentication"} <= families

    def test_tracks_fragment_dependencies(self, inventory):
        document = next(p for p in inventory["policies"] if p["id"] == "policy:api/support-mcp")
        assert document["fragmentRefs"] == ["killswitch"]
        assert any(p["id"] == "policy:fragment/killswitch" for p in inventory["policies"])

    def test_links_assets_to_the_policies_that_govern_them(self, inventory):
        model = inventory["assets"]["models"][0]
        assert model["policyRefs"]["api"] == "policy:api/aoai-api"
        assert model["policyRefs"]["global"] == "policy:global"


class TestInferenceIsMarked:
    """Every derived value must say what it rests on, and say when it cannot tell.

    A failed inference that renders as an empty list or a null reads as "nothing
    there", which is the same shape as a confident negative answer.
    """

    def test_backend_auth_sees_policies_included_by_fragment(self, inventory):
        # Regression: auth scanned only the API's own document, so an
        # authentication-managed-identity inside a fragment was missed and the
        # backend was reported as called unauthenticated.
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "aoai-api")
        basis = model["provider"]["auth"]["basis"]
        assert "policy:api/aoai-api" in basis["policyScopesExamined"]
        assert basis["unresolvedFragments"] == []

    def test_backend_auth_records_what_it_searched(self, inventory):
        for asset in inventory["assets"]["models"]:
            auth = asset["provider"]["auth"]
            assert "basis" in auth
            if auth["mode"] in {"none", "undetermined"}:
                assert auth["note"], f"{asset['id']} claims {auth['mode']} with no explanation"

    def test_unresolvable_fragment_makes_auth_undetermined_not_none(self):
        import fake_arm

        key = f"{SERVICE}/policyFragments"
        original = fake_arm.ROUTES[key]
        fake_arm.ROUTES[key] = []  # fragment referenced by the MCP policy now missing
        try:
            document = Collector(FakeArmClient(), SERVICE, options()).run()
        finally:
            fake_arm.ROUTES[key] = original
        server = next(
            a for a in document["assets"]["mcpServers"] if a["source"]["name"] == "support-mcp"
        )
        assert "killswitch" in server["policyRefs"]["fragments"][0]

    def test_operation_policies_are_linked_to_their_asset(self, inventory):
        # Regression: policyRefs.operations was hardcoded empty, so an asset with
        # operation-level policy looked like it had none.
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "aoai-api")
        assert model["policyRefs"]["operations"] == []
        assert "chat" in [op["name"] for op in model["endpoints"]["operations"]]

    def test_unparseable_subscription_scope_is_unknown_not_service_wide(self):
        import fake_arm

        key = f"{SERVICE}/subscriptions"
        original = fake_arm.ROUTES[key]
        fake_arm.ROUTES[key] = [
            {"id": f"{SERVICE}/subscriptions/weird", "name": "weird",
             "properties": {"displayName": "weird", "state": "active", "scope": "/something/else"}}
        ]
        try:
            document = Collector(FakeArmClient(), SERVICE, options()).run()
        finally:
            fake_arm.ROUTES[key] = original
        [subscription] = document["shared"]["subscriptions"]
        # Defaulting to "service" would over-report a key as granting full access.
        assert subscription["scope"]["level"] == "unknown"

    def test_mcp_transport_records_that_it_was_inferred(self, inventory):
        server = next(
            a for a in inventory["assets"]["mcpServers"] if a["source"]["name"] == "support-mcp"
        )
        upstream = server["upstream"][0]
        assert upstream["transport"] == "streamableHttp"
        assert upstream["transportBasis"]["status"] == "declared"

    def test_unreadable_mcp_transport_is_undetermined_not_null(self):
        from apim_import.collect import _mcp_transport

        assert _mcp_transport({"transportType": "streamable"})["status"] == "declared"
        assert _mcp_transport({"endpoints": [{"name": "mcp"}]})["status"] == "inferred"
        blank = _mcp_transport({})
        assert blank["status"] == "undetermined"
        assert blank["value"] is None
        assert "Confirm it" in blank["note"]

    def test_backend_reference_scan_disclaims_proof_of_orphanhood(self, inventory):
        provider = next(
            p for p in inventory["assets"]["modelProviders"] if p["providerKind"] == "foundry"
        )
        basis = provider["referencedBy"]["basis"]
        assert "not proof" in basis["caveat"]

    def test_backend_reference_scan_covers_policy_expressions(self, inventory):
        provider = next(
            p for p in inventory["assets"]["modelProviders"] if p["providerKind"] == "foundry"
        )
        assert "expressions" in provider["referencedBy"]

    def test_skipped_backends_are_recorded_like_skipped_apis(self, inventory):
        # Absence must not be the only evidence that a backend is not a provider.
        skipped = {entry["name"] for entry in inventory["excludedBackends"]}
        assert "support-backend" in skipped
        entry = next(e for e in inventory["excludedBackends"] if e["name"] == "support-backend")
        assert entry["reason"]
        assert entry["usedByAssets"] == ["mcp:support-mcp"]


class TestPublishableSurface:
    """What the target can publish of what the source exposes.

    Drives the scope decision, so it has to be on the asset rather than
    re-derived later.
    """

    def test_provider_is_resolved_from_import_naming_not_asked_about(self, inventory):
        # Regression for the governing rule: APIM already answers this through
        # the backend name `meta-ai-openai-endpoint`, so it is not a question.
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "meta-ai")
        provider = model["provider"]
        assert provider["kind"] == "openAiCompatible"
        assert provider["apiDialect"] == "openAIChatCompletions"
        assert provider["targetProviderKind"] == "Custom"
        assert provider["protocolBasis"] == "importConvention"

    def test_host_identifies_the_vendor_naming_declares_the_protocol(self, inventory):
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "aoai-api")
        assert model["provider"]["kind"] == "foundry"
        assert model["provider"]["basis"] == "backendHost"

    def test_each_model_api_carries_a_surface_breakdown(self, inventory):
        for model in inventory["assets"]["models"]:
            surface = model["endpoints"]["surface"]
            assert surface["status"] in {"bounded", "unbounded", "unknown"}
            assert surface["basis"] == "operationTemplates"
            assert sorted(surface["targetRoutes"]) == [
                "/openai/v1/chat/completions", "/openai/v1/embeddings",
                "/openai/v1/responses", "/v1/messages",
            ]

    def test_wildcard_api_reports_an_unbounded_surface(self, inventory):
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "meta-ai")
        assert model["endpoints"]["surface"]["status"] == "unbounded"

    def test_bounded_api_counts_what_cannot_move(self, inventory):
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "aoai-api")
        surface = model["endpoints"]["surface"]
        assert surface["status"] == "bounded"
        # chat/completions and embeddings move; threads, assistants and vector stores cannot.
        assert surface["publishableCount"] == 2
        assert {entry["group"] for entry in surface["unpublishable"]} == {
            "threads", "assistants", "vectorStores"
        }


class TestCollectionCost:
    """Reading a policy per operation cost 110 of 171 round trips on one real
    instance, nearly all returning 404. It is opt-in, and the skip is recorded
    because "not collected" must not read as "none exist"."""

    def test_operation_policies_are_not_read_by_default(self, inventory):
        levels = [doc["scope"]["level"] for doc in inventory["policies"]]
        assert "operation" not in levels

    def test_the_skip_is_recorded_in_coverage(self, inventory):
        skipped = [
            entry for entry in inventory["collection"]["coverage"]
            if entry["status"] == "notCollected"
        ]
        assert skipped
        assert all(entry["collection"] == "operationPolicies" for entry in skipped)
        # The count says how many were skipped, so the size of the gap is visible.
        assert all(entry["count"] > 0 for entry in skipped)

    def test_the_asset_says_an_empty_list_proves_nothing(self, inventory):
        for model in inventory["assets"]["models"]:
            refs = model["policyRefs"]
            assert refs["operationPoliciesCollected"] is False
            assert refs["operations"] == []

    def test_opting_in_collects_them_and_records_no_gap(self):
        document = Collector(FakeArmClient(), SERVICE, options(operation_policies=True)).run()
        assert not [
            entry for entry in document["collection"]["coverage"]
            if entry["status"] == "notCollected"
        ]
        for model in document["assets"]["models"]:
            assert model["policyRefs"]["operationPoliciesCollected"] is True

    def test_skipping_costs_fewer_reads_than_collecting(self):
        lean = FakeArmClient()
        Collector(lean, SERVICE, options()).run()
        full = FakeArmClient()
        Collector(full, SERVICE, options(operation_policies=True)).run()
        assert lean.call_count < full.call_count

    def test_progress_is_reported_so_slow_is_not_mistaken_for_hung(self):
        seen: list[str] = []
        Collector(FakeArmClient(), SERVICE, options(), progress=seen.append).run()
        assert seen
        assert any("apis@" in message for message in seen)
        # Each heartbeat carries a running read count.
        assert all("reads)" in message for message in seen)


class TestBackendRoles:
    """A policy that points at a backend declares what it is for.

    That declaration outranks the host heuristic: an Azure AI Content Safety
    endpoint sits on *.cognitiveservices.azure.com and is otherwise
    indistinguishable from a Foundry model host.
    """

    def test_content_safety_backend_is_not_a_model_provider(self, inventory):
        names = {p["origin"].get("backendName") for p in inventory["assets"]["modelProviders"]}
        assert "AI-CS-demo" not in names

    def test_content_safety_backend_is_recorded_as_skipped_with_its_role(self, inventory):
        entry = next(e for e in inventory["excludedBackends"] if e["name"] == "AI-CS-demo")
        assert entry["reason"] == "declaredNonModelRole"
        assert entry["roles"] == ["contentSafety"]
        assert entry["declaredBy"]["contentSafety"]

    def test_roles_are_attached_to_the_backend_record(self, inventory):
        backend = next(b for b in inventory["shared"]["backends"] if b["name"] == "AI-CS-demo")
        assert backend["roles"] == ["contentSafety"]

    def test_content_safety_is_surfaced_as_a_dependency_of_the_api(self, inventory):
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "aoai-api")
        by_role = {entry["role"]: entry for entry in model["supportingBackends"]}
        assert by_role["contentSafety"]["name"] == "AI-CS-demo"
        assert by_role["contentSafety"]["attributes"]["shield-prompt"] == "true"
        # A semantic-cache embeddings backend is a dependency too, and a different role.
        assert by_role["embeddings"]["name"] == "embed"

    def test_child_element_configuration_is_not_passed_off_as_complete(self, inventory):
        # llm-content-safety keeps its thresholds in <categories>, not attributes.
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "aoai-api")
        supporting = next(e for e in model["supportingBackends"] if e["role"] == "contentSafety")
        assert supporting["configurationComplete"] is False
        assert supporting["childElements"] == ["categories"]
        assert supporting["fullConfigurationAt"]["policyId"] == "policy:api/aoai-api"
        # The embeddings one really is attribute-only, so it is marked complete.
        embeddings = next(e for e in model["supportingBackends"] if e["role"] == "embeddings")
        assert embeddings["configurationComplete"] is True

    def test_full_configuration_is_reachable_where_it_points(self, inventory):
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "aoai-api")
        pointer = next(
            e for e in model["supportingBackends"] if e["role"] == "contentSafety"
        )["fullConfigurationAt"]
        document = next(p for p in inventory["policies"] if p["id"] == pointer["policyId"])
        categories = [
            element for element in document["elements"]
            if element["path"].startswith(pointer["path"]) and element["name"] == "category"
        ]
        assert {c["attributes"]["name"]: c["attributes"]["threshold"] for c in categories} == {
            "Hate": "0", "Violence": "2"
        }

    def test_routing_backend_is_not_listed_as_supporting(self, inventory):
        # set-backend-service names the model backend itself; routing.targets covers it.
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "aoai-api")
        assert all(s["role"] != "routing" for s in model["supportingBackends"])

    def test_expression_valued_backend_id_is_not_treated_as_a_name(self):
        from apim_import import detect

        assert detect.backend_roles_from_element(
            {"name": "llm-content-safety", "attributes": {"backend-id": "@(context.Variables[\"b\"])"}}
        ) is None
        assert detect.backend_roles_from_element(
            {"name": "llm-content-safety", "attributes": {"backend-id": "{{cs-backend}}"}}
        ) is None
        assert detect.backend_roles_from_element(
            {"name": "llm-content-safety", "attributes": {"backend-id": "AI-CS-demo"}}
        ) == ("AI-CS-demo", "contentSafety")


class TestDeterminism:
    def test_two_runs_produce_identical_content(self):
        def run():
            document = Collector(FakeArmClient(), SERVICE, options()).run()
            document["collection"].pop("startedAt")
            document["collection"].pop("completedAt")
            return json.dumps(document, sort_keys=True)

        assert run() == run()


class TestOptions:
    def test_family_filter_skips_other_families(self):
        document = Collector(FakeArmClient(), SERVICE, options(families={"mcp"})).run()
        assert document["assets"]["models"] == []
        assert document["assets"]["modelProviders"] == []
        assert len(document["assets"]["mcpServers"]) == 2

    def test_exclude_api_removes_an_asset(self):
        document = Collector(
            FakeArmClient(), SERVICE, options(exclude_api=["support-*"])
        ).run()
        names = {asset["source"]["name"] for asset in document["assets"]["mcpServers"]}
        assert names == {"orders-mcp"}
        assert any(entry["reason"] == "excludedByOption" for entry in document["excludedApis"])

    def test_no_policy_xml_drops_raw_documents_but_keeps_elements(self):
        document = Collector(
            FakeArmClient(), SERVICE, options(include_policy_xml=False)
        ).run()
        assert all("xml" not in policy for policy in document["policies"])
        assert any(policy["elements"] for policy in document["policies"])

    def test_no_foundry_skips_arm_resolution(self):
        document = Collector(FakeArmClient(), SERVICE, options(resolve_foundry=False)).run()
        provider = document["assets"]["modelProviders"][0]
        assert provider["models"]["status"] == "unresolved"
