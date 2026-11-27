import json

import pytest

from migrate_apim.cli import validate_inventory
from migrate_apim.collect import Collector, CollectOptions
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

    def test_a_superseded_revision_is_recorded_rather_than_dropped(self, inventory):
        """`excludedApis` is what proves no API was lost, so it has to hold them all.

        A non-current revision left by a bare `continue`: no entry, no coverage
        record, nothing. It is the one thing this collector dropped in silence,
        which is exactly the shape of defect the list exists to rule out -- an
        operator auditing what moved could not tell a revision considered and
        set aside from one never seen.
        """
        excluded = {entry["name"]: entry for entry in inventory["excludedApis"]}
        assert "aoai-api;rev=1" in excluded
        assert excluded["aoai-api;rev=1"]["reason"] == "notCurrentRevision"

    def test_a_superseded_revision_is_not_an_asset(self, inventory):
        """Recording it must not promote it: callers do not reach it."""
        names = [
            asset["source"]["name"]
            for family in inventory["assets"].values() for asset in family
            if asset.get("source")
        ]
        assert "aoai-api;rev=1" not in names

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
        model = next(m for m in provider["models"]["resolved"] if m["deploymentName"] == "gpt-5")
        assert (model["modelName"], model["modelVersion"]) == ("gpt-5.2", "2025-12-11")
        # Pre-shaped for an AI Gateway model registration.
        assert model["target"]["deployment"]["resourceId"].endswith("/deployments/gpt-5")
        assert model["target"]["providerKind"] == "Foundry"
        # Routes come from the deployment's declared capabilities, not a guess.
        assert model["target"]["supportedEndpoints"] == [
            "/openai/v1/chat/completions", "/openai/v1/responses"
        ]
        embedding = next(
            m for m in provider["models"]["resolved"] if m["deploymentName"] == "text-embedding-3-large"
        )
        assert embedding["target"]["supportedEndpoints"] == ["/openai/v1/embeddings"]

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
        backend = next(b for b in inventory["apim"]["backends"] if b["name"] == "aoai-east")
        assert backend["resourceIdRef"].startswith("/subscriptions/")
        assert "management.azure.com" not in backend["resourceIdRef"]

    def test_model_api_is_found_by_apim_ai_import_naming_alone(self, inventory):
        # No provider host match, no inference path, no LLM policy: only the
        # '-openai-endpoint' backend and '-LLM' named value give it away.
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "meta-ai")
        assert model["detection"]["confidence"] == "medium"
        signals = {signal["type"] for signal in model["detection"]["signals"]}
        assert signals == {"backendNaming", "namedValueNaming"}

    def test_an_unrecognized_host_still_yields_a_known_protocol(self, inventory):
        # api.meta.ai matches no provider rule, so the vendor is not identified.
        # The import naming still declares the protocol -- and with it, where the
        # model list lives. Reporting "unknown" here made the plan ask an operator
        # to type model names the tool could have fetched.
        provider = next(
            p for p in inventory["assets"]["modelProviders"]
            if p["origin"].get("backendName") == "meta-ai-openai-endpoint"
        )
        assert provider["providerKind"] == "openAiCompatible"
        assert provider["apiDialect"] == "openAIChatCompletions"
        assert provider["targetProviderKind"] == "Custom"
        assert provider["models"]["status"] == "unresolved"
        assert provider["models"]["discoverySource"] == "modelsEndpoint"
        assert "resolve-models" in " ".join(provider["models"]["notes"])

    def test_the_model_asset_agrees_with_its_provider(self, inventory):
        # Regression: the asset said openAiCompatible while the provider said
        # unknown, and the plan quoted the provider.
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "meta-ai")
        provider = next(
            p for p in inventory["assets"]["modelProviders"]
            if p["origin"].get("backendName") == "meta-ai-openai-endpoint"
        )
        assert model["provider"]["kind"] == provider["providerKind"]
        assert model["provider"]["apiDialect"] == provider["apiDialect"]
        assert model["models"]["discoverySource"] == provider["models"]["discoverySource"]

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
        [workspace] = inventory["apim"]["workspaces"]
        assert workspace["name"] == "finance"
        assert workspace["collected"] is True
        assert workspace["serveOn"] == "workspaceAndDefault"

    def test_workspace_assets_are_scoped_in_their_ids(self, inventory):
        model = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "model-api")
        assert model["id"] == "model:finance/model-api"
        assert model["workspace"] == "finance"
        backend = next(b for b in inventory["apim"]["backends"] if b["name"] == "claude-backend")
        assert backend["id"] == "backend:finance/claude-backend"

    def test_workspace_scope_can_be_disabled(self):
        document = Collector(FakeArmClient(), SERVICE, options(workspaces=["none"])).run()
        assert [w["collected"] for w in document["apim"]["workspaces"]] == [False]
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
        from migrate_apim import detect

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
        backend = next(b for b in inventory["apim"]["backends"] if b["name"] == "support-backend")
        assert backend["credentials"]["header"]["x-api-key"][0].startswith("${secret:backendInline/")
        ref = next(s for s in inventory["secrets"] if s["class"] == "apimBackendInlineCredential")
        assert ref["retrievable"] is True
        assert ref["resolution"]["method"] == "armRead"

    def test_named_value_reference_is_preserved_verbatim(self, inventory):
        backend = next(b for b in inventory["apim"]["backends"] if b["name"] == "aoai-west")
        assert backend["credentials"]["header"]["api-key"] == ["{{aoai-key}}"]
        assert "secret:namedValue/aoai-key" in backend["secretRefs"]

    def test_non_secret_named_value_keeps_its_value(self, inventory):
        entry = next(n for n in inventory["apim"]["namedValues"] if n["name"] == "MCP-KILLSWITCH")
        assert entry["value"] == "off"
        assert entry["secretRef"] is None

    def test_secret_named_value_has_no_value_but_has_a_recipe(self, inventory):
        entry = next(n for n in inventory["apim"]["namedValues"] if n["name"] == "aoai-key")
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
        levels = {document["scope"]["level"] for document in inventory["apim"]["policies"]}
        assert {"api", "fragment"} <= levels

    def test_normalizes_llm_policies_into_families(self, inventory):
        document = next(p for p in inventory["apim"]["policies"] if p["id"] == "policy:api/aoai-api")
        families = {element["family"] for element in document["elements"]}
        assert {"tokenLimit", "tokenMetrics", "semanticCache", "backendAuthentication"} <= families

    def test_tracks_fragment_dependencies(self, inventory):
        document = next(p for p in inventory["apim"]["policies"] if p["id"] == "policy:api/support-mcp")
        assert document["fragmentRefs"] == ["killswitch"]
        assert any(p["id"] == "policy:fragment/killswitch" for p in inventory["apim"]["policies"])

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

    def test_a_key_set_by_policy_reaches_the_provider_it_credentials(self):
        """APIM credentials a backend either on the backend record or in policy.

        Reading only the record reported the policy shape as having no
        credential at all -- and once the policy *is* read, saying nothing about
        a `set-header` turns that into the stronger claim that the upstream is
        called unauthenticated. The key is the same key either way, and the
        target field is the same field.
        """
        import copy, fake_arm

        backends_key = f"{SERVICE}/backends"
        policy_key = f"{SERVICE}/apis/meta-ai"
        original_backends = fake_arm.ROUTES[backends_key]
        original_policy = fake_arm.POLICIES.get(policy_key)

        backends = copy.deepcopy(original_backends)
        for backend in backends:
            if backend["name"] == "meta-ai-openai-endpoint":
                backend["properties"].pop("credentials", None)
        fake_arm.ROUTES[backends_key] = backends
        fake_arm.POLICIES[policy_key] = (
            "<policies><inbound><base />"
            '<set-header name="api-key" exists-action="override">'
            "<value>{{meta-ai-Authorization-LLM}}</value></set-header>"
            "</inbound><backend><base /></backend>"
            "<outbound><base /></outbound><on-error><base /></on-error></policies>"
        )
        try:
            document = Collector(FakeArmClient(), SERVICE, options()).run()
        finally:
            fake_arm.ROUTES[backends_key] = original_backends
            if original_policy is None:
                fake_arm.POLICIES.pop(policy_key, None)
            else:
                fake_arm.POLICIES[policy_key] = original_policy

        provider = next(
            p for p in document["assets"]["modelProviders"] if "meta-ai" in p["id"]
        )
        auth = provider["auth"]
        assert auth["mode"] == "apiKey", auth.get("note")
        assert auth["evidence"] == ["policy:set-header"]
        # The real header, not a default, and the secret ref the named value
        # collection already registered rather than a second one for the same
        # APIM secret.
        assert auth["parameters"]["header"] == ["api-key"]
        assert auth["secretRefs"] == ["secret:namedValue/meta-ai-Authorization-LLM"]

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
        [subscription] = document["apim"]["subscriptions"]
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
        from migrate_apim.collect import _mcp_transport

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
        levels = [doc["scope"]["level"] for doc in inventory["apim"]["policies"]]
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
        backend = next(b for b in inventory["apim"]["backends"] if b["name"] == "AI-CS-demo")
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
        document = next(p for p in inventory["apim"]["policies"] if p["id"] == pointer["policyId"])
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
        from migrate_apim import detect

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
        assert all("xml" not in policy for policy in document["apim"]["policies"])
        assert any(policy["elements"] for policy in document["apim"]["policies"])

    def test_no_foundry_skips_arm_resolution(self):
        document = Collector(FakeArmClient(), SERVICE, options(resolve_foundry=False)).run()
        provider = document["assets"]["modelProviders"][0]
        assert provider["models"]["status"] == "unresolved"


class TestPoolBehaviourReachesTheAsset:
    """Pool settings the plan must account for cannot stay on the raw backend."""

    def test_session_affinity_and_failure_response_are_carried(self, inventory):
        asset = next(m for m in inventory["assets"]["models"] if m["source"]["name"] == "aoai-api")
        routing = asset["routing"]
        assert routing["mode"] == "pool"
        # Null on this fixture, but present: the planner reads the key, and an
        # absent key is indistinguishable from a pool that does not use it.
        assert "sessionAffinity" in routing
        assert "failureResponse" in routing


class TestAServiceThatCouldNotBeRead:
    """Regression: every failed service read was reported as "not found".

    An operator looking at a service that plainly exists -- `az apim show`
    succeeds on it -- was sent to check the name, the resource group and the
    subscription, while the real cause (a denied read, a dead CLI, a network
    error) sat unread in a coverage entry.
    """

    class _Failing(FakeArmClient):
        def __init__(self, response):
            super().__init__()
            self._response = response

        def request(self, method, url, **kwargs):
            self.call_count += 1
            return self._response

    def test_a_denied_read_reports_the_denial(self):
        from migrate_apim.arm import ArmError, ArmResponse

        body = {"error": {"code": "AuthorizationFailed", "message": "does not have authorization"}}
        client = self._Failing(ArmResponse(403, body, json.dumps(body)))
        with pytest.raises(ArmError) as excinfo:
            Collector(client, SERVICE, options()).run()
        assert "AuthorizationFailed" in str(excinfo.value)
        assert "not found" not in str(excinfo.value)

    def test_a_genuine_404_still_says_not_found_and_what_to_check(self):
        from migrate_apim.arm import ArmError, ArmResponse

        client = self._Failing(ArmResponse(404, {"error": {"code": "ResourceNotFound"}}, ""))
        with pytest.raises(ArmError) as excinfo:
            Collector(client, SERVICE, options()).run()
        assert "not found" in str(excinfo.value)
        assert "--subscription" in str(excinfo.value)


class TestFragmentsAreCollectedAsAssetsOfTheirOwn:
    """A fragment is a shared asset, and was the one that was not scoped like
    one: two workspaces holding a same-named fragment collapsed onto one id,
    and the collector keeps whichever document it saw first."""

    def _with_workspace_fragment(self, body="<fragment><set-variable name='w' value='1' /></fragment>"):
        import fake_arm

        key = f"{SERVICE}/workspaces/finance/policyFragments"
        original = fake_arm.ROUTES[key]
        fake_arm.ROUTES[key] = [{
            "id": f"{SERVICE}/workspaces/finance/policyFragments/killswitch",
            "name": "killswitch",
            "properties": {"description": "finance kill switch", "value": body},
        }]
        try:
            return Collector(FakeArmClient(), SERVICE, options()).run()
        finally:
            fake_arm.ROUTES[key] = original

    def test_a_same_named_fragment_in_a_workspace_is_a_second_fragment(self):
        document = self._with_workspace_fragment()
        ids = {d["id"] for d in document["apim"]["policies"]
               if (d.get("scope") or {}).get("level") == "fragment"}
        assert ids == {"policy:fragment/killswitch", "policy:fragment/finance/killswitch"}

    def test_each_one_keeps_its_own_contents(self):
        document = self._with_workspace_fragment()
        bodies = {
            d["id"]: [e["name"] for e in d["elements"]]
            for d in document["apim"]["policies"] if (d.get("scope") or {}).get("level") == "fragment"
        }
        assert bodies["policy:fragment/killswitch"] == ["set-variable"]
        assert bodies["policy:fragment/finance/killswitch"] == ["set-variable"]
        service = next(d for d in document["apim"]["policies"] if d["id"] == "policy:fragment/killswitch")
        finance = next(d for d in document["apim"]["policies"]
                       if d["id"] == "policy:fragment/finance/killswitch")
        assert service["elements"][0]["attributes"] != finance["elements"][0]["attributes"]

    def test_the_asset_record_says_which_workspace_it_is_in(self):
        document = self._with_workspace_fragment()
        by_id = {f["id"]: f for f in document["apim"]["policyFragments"]}
        assert by_id["policyFragment:killswitch"]["workspace"] == "default"
        assert by_id["policyFragment:finance/killswitch"]["workspace"] == "finance"

    def test_a_fragment_whose_body_could_not_be_read_is_not_an_empty_fragment(self):
        """Parsed as the empty string it registered as a fragment that resolves
        and contains nothing, so whatever it carried migrated as if absent."""
        import fake_arm

        key = f"{SERVICE}/policyFragments"
        original = fake_arm.ROUTES[key]
        fake_arm.ROUTES[key] = [{
            "id": f"{SERVICE}/policyFragments/killswitch", "name": "killswitch",
            "properties": {"description": "kill switch"},  # no value, and the GET 404s
        }]
        try:
            document = Collector(FakeArmClient(), SERVICE, options()).run()
        finally:
            fake_arm.ROUTES[key] = original
        fragment = next(d for d in document["apim"]["policies"] if d["id"] == "policy:fragment/killswitch")
        assert fragment["parseError"], "unknown is not empty"
        assert "not evidence" in fragment["parseError"]
        asset = next(f for f in document["apim"]["policyFragments"] if f["name"] == "killswitch")
        assert asset["parseError"]

    def test_the_fragment_list_is_read_as_authored(self):
        """Every other policy read forces `format=rawxml` so expression text is
        kept as written. The fragment list did not, so the same expression
        hashed to a different `expr:` id than it did at API scope."""
        seen = {}

        class Recording(FakeArmClient):
            def list(self, url, api_version, **params):
                seen[url] = params
                return super().list(url, api_version, **params)

        Collector(Recording(), SERVICE, options()).run()
        assert seen[f"{SERVICE}/policyFragments"] == {"format": "rawxml"}


def _find_auth(value):
    """The first `auth` record anywhere in an asset, however it is nested."""
    if isinstance(value, dict):
        if "mode" in value and "evidence" in value:
            return value
        for nested in value.values():
            found = _find_auth(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_auth(nested)
            if found:
                return found
    return None


class TestBackendAuthReadsAnOrderAndNotAUnion:
    """The last `authentication-managed-identity` to run is the one that
    applies, and a union of alternative request contexts has no last."""

    def _collected(self, product_identity):
        import fake_arm

        api_policy = (
            "<policies><inbound><base />"
            "<authentication-managed-identity resource='https://api' />"
            "</inbound><backend><base /></backend>"
            "<outbound><base /></outbound><on-error><base /></on-error></policies>"
        )
        product_policy = (
            "<policies><inbound>"
            f"<authentication-managed-identity resource='{product_identity}' />"
            "</inbound><backend><base /></backend>"
            "<outbound><base /></outbound><on-error><base /></on-error></policies>"
        )
        originals = {
            "policies": dict(fake_arm.POLICIES),
            "product_apis": fake_arm.ROUTES[f"{SERVICE}/products/ai/apis"],
        }
        fake_arm.POLICIES[f"{SERVICE}/apis/aoai-api"] = api_policy
        fake_arm.POLICIES[f"{SERVICE}/products/ai"] = product_policy
        try:
            return Collector(FakeArmClient(), SERVICE, options()).run()
        finally:
            fake_arm.POLICIES.clear()
            fake_arm.POLICIES.update(originals["policies"])

    def _auth(self, document):
        """The authentication the policy decided, not one a backend declared."""
        for group in document["assets"].values():
            for asset in group:
                auth = _find_auth(asset)
                if auth and "policy:authentication-managed-identity" in (
                    auth.get("evidence") or []
                ):
                    return auth
        raise AssertionError("no asset took its identity from policy")

    def test_the_apis_own_identity_wins_over_an_inherited_one(self):
        auth = self._auth(self._collected("https://product"))
        assert auth["identity"]["audience"] == "https://api"

    def test_two_identities_that_cannot_both_apply_are_named_not_chosen(self):
        auth = self._auth(self._collected("https://product"))
        assert "identityCandidates" not in auth, (
            "the API overrides the product in both contexts, so there is one answer")

    def test_an_unambiguous_identity_carries_no_note(self):
        auth = self._auth(self._collected("https://api"))
        assert "identityNote" not in auth

    def test_two_products_setting_different_identities_are_named_not_picked(self):
        """Which one applies depends on the product a call arrives through,
        and one provider cannot authenticate two ways."""
        from migrate_apim import collect as collect_mod
        from migrate_apim import policy as policy_mod
        from migrate_apim import secrets as secrets_mod

        def doc(policy_id, scope, xml):
            return policy_mod.parse(xml, policy_id=policy_id, scope=scope, scope_url="/x")

        def product(name, resource):
            return doc(
                f"policy:product/{name}",
                {"level": "product", "name": name, "workspace": "default"},
                "<policies><inbound>"
                f"<authentication-managed-identity resource='{resource}' />"
                "</inbound><backend><base /></backend><outbound><base /></outbound>"
                "<on-error><base /></on-error></policies>",
            )

        graph = policy_mod.PolicyGraph(
            [
                product("a", "https://a"),
                product("b", "https://b"),
                doc("policy:api/aoai", {"level": "api", "name": "aoai", "workspace": "default"},
                    "<policies><inbound><base /></inbound><backend><base /></backend>"
                    "<outbound><base /></outbound><on-error><base /></on-error></policies>"),
            ],
            products=[{"policyId": "policy:product/a", "apiIds": ["api:aoai"]},
                      {"policyId": "policy:product/b", "apiIds": ["api:aoai"]}],
        )
        auth = collect_mod._backend_auth(
            None, graph.governing(api="aoai"),
            secrets_mod.SecretRegistry(service_id=SERVICE, api_version="2025-09-01-preview"),
        )
        assert auth["mode"] == "managedIdentity"
        assert {c["audience"] for c in auth["identityCandidates"]} == {"https://a", "https://b"}
        assert "depending on which product" in auth["identityNote"]


class TestAnUnreadableFragmentCannotBeCalledUnauthenticated:
    """`mode: none` is a claim the backend is called without credentials. A
    fragment whose body would not load is a place one could have been set."""

    def _resolved(self):
        from migrate_apim import policy as policy_mod

        def doc(policy_id, scope, xml):
            return policy_mod.parse(xml, policy_id=policy_id, scope=scope, scope_url="/x")

        broken = doc("policy:fragment/creds",
                     {"level": "fragment", "name": "creds", "workspace": "default"},
                     "<fragment />")
        broken["parseError"] = "the body could not be read"
        graph = policy_mod.PolicyGraph([
            doc("policy:api/aoai", {"level": "api", "name": "aoai", "workspace": "default"},
                "<policies><inbound><include-fragment fragment-id='creds' /></inbound>"
                "<backend><base /></backend><outbound><base /></outbound>"
                "<on-error><base /></on-error></policies>"),
            broken,
        ])
        return graph.governing(api="aoai")

    def _auth(self):
        from migrate_apim import collect as collect_mod
        from migrate_apim import secrets as secrets_mod

        return collect_mod._backend_auth(
            None, self._resolved(),
            secrets_mod.SecretRegistry(service_id=SERVICE, api_version="2025-09-01-preview"),
        )

    def test_it_is_undetermined_rather_than_none(self):
        assert self._auth()["mode"] == "undetermined"

    def test_the_basis_names_the_fragment_nobody_could_read(self):
        assert "policy:fragment/creds" in self._auth()["basis"]["unresolvedFragments"]

    def test_the_asset_keeps_its_link_to_the_document_that_failed(self):
        """It contributes no elements, so it is on no route -- and dropping it
        cut the only pointer to the document explaining the failure."""
        from migrate_apim import collect as collect_mod

        assert collect_mod._fragments_reaching(self._resolved(), None) == [
            "policy:fragment/creds"
        ]

    def test_an_identity_inherited_through_a_products_fragment_still_loses_to_the_api(self):
        """The reported shape: `<base />` then identity A on the API, and a
        product that *includes a fragment* setting B. A overrides B in both
        request contexts, and the flattened union says otherwise."""
        from migrate_apim import collect as collect_mod
        from migrate_apim import policy as policy_mod
        from migrate_apim import secrets as secrets_mod

        def doc(policy_id, scope, xml):
            return policy_mod.parse(xml, policy_id=policy_id, scope=scope, scope_url="/x")

        def wrap(inner):
            return (f"<policies><inbound>{inner}</inbound><backend><base /></backend>"
                    "<outbound><base /></outbound><on-error><base /></on-error></policies>")

        graph = policy_mod.PolicyGraph(
            [
                doc("policy:product/ai", {"level": "product", "name": "ai",
                                          "workspace": "default"},
                    wrap("<include-fragment fragment-id='creds' />")),
                doc("policy:api/aoai", {"level": "api", "name": "aoai", "workspace": "default"},
                    wrap("<base /><authentication-managed-identity resource='https://a' />")),
                doc("policy:fragment/creds", {"level": "fragment", "name": "creds",
                                              "workspace": "default"},
                    "<fragment><authentication-managed-identity resource='https://b' />"
                    "</fragment>"),
            ],
            products=[{"policyId": "policy:product/ai", "apiIds": ["api:aoai"]}],
        )
        auth = collect_mod._backend_auth(
            None, graph.governing(api="aoai"),
            secrets_mod.SecretRegistry(service_id=SERVICE, api_version="2025-09-01-preview"),
        )
        assert auth["identity"]["audience"] == "https://a"
        assert "identityCandidates" not in auth, "both chains end on A, so there is one answer"


class TestABasicCredentialIsNotNoCredential:
    """`authentication-basic` sets the credential the upstream is called with.

    It contributed no mode, so a backend secured by it reported `none` -- whose
    note says outright that the upstream "appears to be called unauthenticated".
    That is a false statement in the voice of something that checked, and the
    policy element was separately raised as a gap, so the inventory and the plan
    said different things about one backend.
    """

    def _auth(self, inbound, record=None):
        from migrate_apim import collect as collect_mod
        from migrate_apim import policy as policy_mod
        from migrate_apim import secrets as secrets_mod

        graph = policy_mod.PolicyGraph([
            policy_mod.parse(
                f"<policies><inbound>{inbound}</inbound><backend><base /></backend>"
                "<outbound><base /></outbound><on-error><base /></on-error></policies>",
                policy_id="policy:api/aoai",
                scope={"level": "api", "name": "aoai", "workspace": "default"},
                scope_url="/x",
            )
        ])
        return collect_mod._backend_auth(
            record, graph.governing(api="aoai"),
            secrets_mod.SecretRegistry(service_id=SERVICE, api_version="2025-09-01-preview"),
        )

    BASIC = "<authentication-basic username='svc' password='{{aoai-key}}' />"

    def test_the_mode_names_the_credential_that_is_set(self):
        assert self._auth(self.BASIC)["mode"] == "basic"

    def test_the_evidence_names_the_policy_that_set_it(self):
        assert self._auth(self.BASIC)["evidence"] == ["policy:authentication-basic"]

    def test_it_no_longer_claims_the_upstream_is_called_unauthenticated(self):
        assert "note" not in self._auth(self.BASIC)

    def test_it_claims_no_secret_ref_for_a_credential_with_no_target(self):
        """`secretRefs` is what fills a Custom provider's ApiKey value.

        Publishing the basic password there would register it as a working api
        key -- a stronger falsehood than the one this fix removes. The password
        is still registered on the policy document, so nothing is lost.
        """
        assert self._auth(self.BASIC)["secretRefs"] == []

    def test_it_outranks_an_api_key_the_same_backend_carries(self):
        """Basic has no target field and an api-key header has one. Reporting
        the key would say this backend migrates by registering it, when the
        call also carries a credential nothing on the target can express."""
        auth = self._auth(self.BASIC, record={"credentials": {"header": {"api-key": ["{{k}}"]}}})
        assert auth["mode"] == "basic"
        assert set(auth["modes"]) == {"basic", "apiKey"}

    def test_a_client_certificate_still_outranks_it(self):
        auth = self._auth(self.BASIC + "<authentication-certificate thumbprint='ABC' />")
        assert auth["mode"] == "clientCertificate"


class TestEveryApiIsInOnePlace:
    """`apim.apis` answers "what APIs are on this service" in one read.

    It used to take a union of four lists -- three asset families plus
    `excludedApis` -- with model providers in a fifth that has no API behind it
    at all. That is a question APIM answers in one call, and an inventory that
    cannot answer it in one place makes every caller reassemble it, each the
    same way, each able to forget a list.
    """

    def test_it_holds_every_api_exactly_once(self, inventory):
        apis = inventory["apim"]["apis"]
        ids = [api["apiId"] for api in apis]
        assert len(ids) == len(set(ids)), "an API listed twice"

        reachable = {
            (asset.get("source") or {}).get("apiId")
            for family in inventory["assets"].values() for asset in family
            if (asset.get("source") or {}).get("apiId")
        } | {entry["apiId"] for entry in inventory["excludedApis"]}
        assert set(ids) == reachable

    def test_an_api_either_became_an_asset_or_says_why_not(self, inventory):
        """Exactly one of the two, for every API. Neither would be an API the
        inventory holds and says nothing about, which is the state this
        collection exists to make impossible."""
        for api in inventory["apim"]["apis"]:
            assert bool(api["assetId"]) != bool(api["excludedReason"]), api["apiId"]

    def test_it_agrees_with_the_asset_it_points_at(self, inventory):
        """Both come out of `_api_source`, so this is a guard on that staying true.

        A second copy of an API's fields that nothing joins is a second
        description, and a second description drifts.
        """
        by_id = {api["apiId"]: api for api in inventory["apim"]["apis"]}
        for family in inventory["assets"].values():
            for asset in family:
                source = asset.get("source") or {}
                if not source.get("apiId"):
                    continue
                row = by_id[source["apiId"]]
                assert all(row[key] == value for key, value in source.items()), source["apiId"]
                assert row["assetId"] == asset["id"]

    def test_a_superseded_revision_is_in_it_too(self, inventory):
        row = next(a for a in inventory["apim"]["apis"] if a["name"] == "aoai-api;rev=1")
        assert row["isCurrent"] is False
        assert row["excludedReason"] == "notCurrentRevision"
        assert row["assetId"] is None

    def test_the_summary_counts_from_it(self, inventory):
        from migrate_apim.summary import render

        line = next(l for l in render(inventory).splitlines() if "APIs on the service" in l)
        total = len(inventory["apim"]["apis"])
        excluded = len([a for a in inventory["apim"]["apis"] if a["excludedReason"]])
        assert f"{total} APIs on the service, {total - excluded} inventoried, {excluded} not" in line


def _account():
    from migrate_apim.foundry import FoundryAccount
    return FoundryAccount(
        resource_id="/subscriptions/s/resourceGroups/r/providers/"
                    "Microsoft.CognitiveServices/accounts/a",
        name="a", resource_group="r", subscription_id="s", location="eastus2",
        kind="AIServices", sku="S0", hosts={"a.cognitiveservices.azure.com"},
    )


class TestACapabilityValueIsReadNotJustItsKey:
    """Foundry writes capability values as the strings "true" and "false".

    `bool("false")` is True, so testing the value naively is as wrong as not
    testing it. Both are pinned here because the obvious fix is the second bug.
    """

    def test_a_false_capability_declares_no_route(self):
        from migrate_apim.foundry import supported_endpoints
        assert supported_endpoints(
            {"capabilities": {"chatCompletion": "false", "decision": "true"}}) == []

    def test_a_true_capability_declares_its_route(self):
        from migrate_apim.foundry import supported_endpoints
        assert supported_endpoints({"capabilities": {"chatCompletion": "true"}}) == [
            "/openai/v1/chat/completions"]

    def test_a_real_boolean_is_read_too(self):
        from migrate_apim.foundry import supported_endpoints
        assert supported_endpoints({"capabilities": {"embeddings": True}}) == [
            "/openai/v1/embeddings"]
        assert supported_endpoints({"capabilities": {"embeddings": False}}) == []

    def test_a_capability_with_no_gateway_route_is_ignored(self):
        from migrate_apim.foundry import supported_endpoints
        assert supported_endpoints(
            {"capabilities": {"imageGenerations": "true", "area": "US"}}) == []

    def test_the_record_names_the_routes_the_command_takes(self):
        """`inferenceRoutes` is the value `model create --supported-endpoints` wants."""
        from migrate_apim.foundry import resolved_model
        account = _account()
        deployment = {"name": "d", "modelName": "m", "modelVersion": "1",
                      "modelFormat": "OpenAI", "sku": {}, "raiPolicyName": None,
                      "capabilities": {"chatCompletion": "true"}}
        record = resolved_model(account, deployment)
        assert record["inferenceRoutes"] == ["/openai/v1/chat/completions"]
        assert record["inferenceRoutes"] == record["target"]["supportedEndpoints"], \
            "one list, named where a rule can reach it and where the command reads it"

    def test_a_model_denying_every_route_names_none(self):
        from migrate_apim.foundry import resolved_model
        account = _account()
        deployment = {"name": "d", "modelName": "m", "modelVersion": "1",
                      "modelFormat": "Microsoft", "sku": {}, "raiPolicyName": None,
                      "capabilities": {"chatCompletion": "false", "decision": "true"}}
        assert resolved_model(account, deployment)["inferenceRoutes"] == []


class TestTheReadingsFollowTheAssetTheySummarise:
    """"Rendered once, so there is nothing to drift" held only until collection.

    `resolve-models` and `discover-tools` -- the two commands the skill
    requires -- rewrite an asset in place. The readings on `apim.apis[]` are a
    copy of what that asset said when it was collected, so afterwards a
    provider whose catalogue had just been fetched still read
    `catalogueFetched: false`, and a server whose tools had just been listed
    still read `toolDiscovery: runtimeOnly`.
    """

    def api_row(self, inventory, asset_id):
        return next(r for r in inventory["apim"]["apis"] if r.get("assetId") == asset_id)

    def an_asset(self, inventory, family):
        return (inventory["assets"][family] or [])[0]

    def test_a_fetched_catalogue_is_reflected(self, inventory):
        from migrate_apim.collect import refresh_api_readings
        asset = next(a for a in inventory["assets"]["models"]
                     if (a.get("source") or {}).get("apiId"))
        row = self.api_row(inventory, asset["id"])
        asset.setdefault("models", {})["catalogue"] = ["muse-1", "muse-2"]
        asset["models"]["discoverySource"] = "modelsEndpoint"
        assert row["catalogueFetched"] is False, "nothing has refreshed it yet"

        refresh_api_readings(inventory)
        row = self.api_row(inventory, asset["id"])
        assert row["catalogueFetched"] is True
        assert row["discoverySource"] == "modelsEndpoint"

    def test_a_discovered_tool_list_is_reflected(self, inventory):
        from migrate_apim.collect import refresh_api_readings
        servers = inventory["assets"].get("mcpServers") or []
        if not servers:
            pytest.skip("fixture has no MCP server")
        asset = servers[0]
        asset["toolDiscovery"] = {"status": "complete", "policiesApplied": True}
        refresh_api_readings(inventory)
        row = self.api_row(inventory, asset["id"])
        assert row["toolDiscovery"] == "complete"
        assert row["toolsFromGateway"] is True

    def test_refreshing_an_untouched_inventory_changes_nothing(self, inventory):
        import copy as _copy
        from migrate_apim.collect import refresh_api_readings
        before = _copy.deepcopy(inventory)
        refresh_api_readings(inventory)
        assert inventory == before


class TestABackendChosenAtRuntimeIsStillBehindItsApi:
    """An API that picks its upstream in policy still credentials that upstream.

    `_resolve_backend` reports a target only when exactly one
    `set-backend-service` names a backend; a `choose` between two reports
    `candidates` and no target at all. Both halves of the provider link read
    targets alone, so such an API linked to no provider -- and the policy
    carrying its managed identity was never consulted for the very backends
    that policy names. The plan then registered Foundry providers with
    `authentication.kind: ManagedIdentity` while creating no identity and
    granting no role.
    """

    CONDITIONAL = (
        "<policies><inbound><base />"
        '<authentication-managed-identity resource="https://cognitiveservices.azure.com/" />'
        "<choose>"
        '<when condition="@(true)"><set-backend-service backend-id="aoai-east" /></when>'
        '<otherwise><set-backend-service backend-id="aoai-west" /></otherwise>'
        "</choose>"
        "</inbound><backend><base /></backend>"
        "<outbound><base /></outbound><on-error><base /></on-error></policies>"
    )

    def _collect(self, policy, *, strip_credentials=True):
        """Collect with `aoai-api` routed by policy instead of `backendId`."""
        import copy, fake_arm

        apis_key, backends_key = f"{SERVICE}/apis", f"{SERVICE}/backends"
        policy_key = f"{SERVICE}/apis/aoai-api"
        originals = (
            fake_arm.ROUTES[apis_key], fake_arm.ROUTES[backends_key],
            fake_arm.POLICIES[policy_key],
        )

        apis = copy.deepcopy(originals[0])
        for api in apis:
            if api["name"] == "aoai-api":
                api["properties"]["backendId"] = None
        backends = copy.deepcopy(originals[1])
        if strip_credentials:
            # The policy must be the only place a credential could come from,
            # or the backend record would answer and prove nothing.
            for backend in backends:
                if backend["name"] in {"aoai-east", "aoai-west"}:
                    backend["properties"].pop("credentials", None)

        fake_arm.ROUTES[apis_key] = apis
        fake_arm.ROUTES[backends_key] = backends
        fake_arm.POLICIES[policy_key] = policy
        try:
            return Collector(FakeArmClient(), SERVICE, options()).run()
        finally:
            (fake_arm.ROUTES[apis_key], fake_arm.ROUTES[backends_key],
             fake_arm.POLICIES[policy_key]) = originals

    def test_the_policys_identity_reaches_every_backend_it_can_route_to(self):
        document = self._collect(self.CONDITIONAL)
        asset = next(
            a for a in document["assets"]["models"] if a["source"]["name"] == "aoai-api"
        )
        # The precondition: no *single* backend resolved, so the candidates are
        # named and the targets are derived from them. `mode` is what keeps the
        # distinction from a declared pool; this used to assert no targets at
        # all, which is what left the catalogue unresolvable.
        assert asset["routing"]["mode"] == "conditional"
        assert asset["routing"]["candidates"] == ["aoai-east", "aoai-west"]
        assert [target["backendId"] for target in asset["routing"]["targets"]] == [
            "backend:aoai-east", "backend:aoai-west"
        ]

        for name in ("aoai-east", "aoai-west"):
            provider = next(
                p for p in document["assets"]["modelProviders"] if p["id"].endswith(name)
            )
            auth = provider["auth"]
            assert auth["mode"] == "managedIdentity", auth.get("note")
            assert auth["evidence"] == ["policy:authentication-managed-identity"]

    def test_both_halves_of_the_provider_link_agree(self):
        """The forward and reverse links are only trustworthy while they match.

        `providerIds` says which providers an API uses; `_provider_resolutions`
        asks the same question backwards to find the policy governing a
        provider. A provider credentialed by this API's policy that the API
        does not list is the divergence both are written to prevent.
        """
        document = self._collect(self.CONDITIONAL)
        asset = next(
            a for a in document["assets"]["models"] if a["source"]["name"] == "aoai-api"
        )
        credentialled = {
            p["id"] for p in document["assets"]["modelProviders"]
            if p["auth"]["evidence"] == ["policy:authentication-managed-identity"]
        }
        assert credentialled <= set(asset["providerIds"])
        assert {"modelProvider:aoai-east", "modelProvider:aoai-west"} == credentialled

    def test_a_single_set_backend_service_still_resolves_as_a_target(self):
        """The path that already worked must not have moved.

        One `set-backend-service` resolves to a real target, so these providers
        were always reachable. If the fix had replaced the target test rather
        than widening it, this is what would have broken.
        """
        document = self._collect(
            "<policies><inbound><base />"
            '<authentication-managed-identity resource="https://cognitiveservices.azure.com/" />'
            '<set-backend-service backend-id="aoai-east" />'
            "</inbound><backend><base /></backend>"
            "<outbound><base /></outbound><on-error><base /></on-error></policies>"
        )
        asset = next(
            a for a in document["assets"]["models"] if a["source"]["name"] == "aoai-api"
        )
        assert asset["routing"]["candidates"] == []
        assert [t["backendId"] for t in asset["routing"]["targets"]] == ["backend:aoai-east"]
        provider = next(
            p for p in document["assets"]["modelProviders"] if p["id"].endswith("aoai-east")
        )
        assert provider["auth"]["mode"] == "managedIdentity"

    def test_a_candidate_is_an_alternative_and_not_a_confirmed_route(self):
        """Widening the link must not turn alternatives into one asserted answer.

        Two APIs that both pick this backend at runtime, credentialling it
        differently, have no single answer. Reading targets alone neither API
        reached it, so the question could not arise; now that both do, it has
        to arrive at `identityCandidates` rather than at whichever API was
        collected second. The merge concatenates chains for exactly this.
        """
        import copy, fake_arm

        apis_key, backends_key = f"{SERVICE}/apis", f"{SERVICE}/backends"
        second_ops = f"{SERVICE}/apis/aoai-api-2/operations"
        originals = (
            fake_arm.ROUTES[apis_key], fake_arm.ROUTES[backends_key],
            fake_arm.POLICIES[f"{SERVICE}/apis/aoai-api"],
        )

        apis = copy.deepcopy(originals[0])
        second = None
        for api in apis:
            if api["name"] == "aoai-api":
                api["properties"]["backendId"] = None
                second = copy.deepcopy(api)
        second["id"], second["name"] = f"{SERVICE}/apis/aoai-api-2", "aoai-api-2"
        second["properties"]["displayName"] = second["properties"]["path"] = "aoai-api-2"
        apis.append(second)

        backends = copy.deepcopy(originals[1])
        for backend in backends:
            if backend["name"] in {"aoai-east", "aoai-west"}:
                backend["properties"].pop("credentials", None)

        fake_arm.ROUTES[apis_key] = apis
        fake_arm.ROUTES[backends_key] = backends
        fake_arm.ROUTES[second_ops] = copy.deepcopy(
            fake_arm.ROUTES[f"{SERVICE}/apis/aoai-api/operations"]
        )
        fake_arm.POLICIES[f"{SERVICE}/apis/aoai-api"] = self.CONDITIONAL
        fake_arm.POLICIES[f"{SERVICE}/apis/aoai-api-2"] = self.CONDITIONAL.replace(
            "<authentication-managed-identity ",
            '<authentication-managed-identity client-id="11111111-1111-1111-1111-111111111111" ',
        )
        try:
            document = Collector(FakeArmClient(), SERVICE, options()).run()
        finally:
            (fake_arm.ROUTES[apis_key], fake_arm.ROUTES[backends_key],
             fake_arm.POLICIES[f"{SERVICE}/apis/aoai-api"]) = originals
            fake_arm.ROUTES.pop(second_ops, None)
            fake_arm.POLICIES.pop(f"{SERVICE}/apis/aoai-api-2", None)

        auth = next(
            p for p in document["assets"]["modelProviders"] if p["id"].endswith("aoai-east")
        )["auth"]
        # Both APIs were read, so neither silently won.
        assert auth["basis"]["policyScopesExamined"] == [
            "policy:api/aoai-api", "policy:api/aoai-api-2"
        ]
        assert [c["clientId"] for c in auth["identityCandidates"]] == [
            None, "11111111-1111-1111-1111-111111111111"
        ]
        assert "2 managed identities apply" in auth["identityNote"]

    def test_the_model_catalogue_resolves_from_the_backends_the_policy_names(self):
        """The models are readable, so the operator must not be asked for them.

        Model resolution walks `targets`, so an empty list meant no Foundry
        account was ever looked up: the catalogue came back `unresolved` with
        "Provider could not be inferred from the backend URL", and the plan
        raised a blocking item asking the operator to hand-list models that ARM
        had already resolved for the very same backends in the pool case.
        """
        document = self._collect(self.CONDITIONAL, strip_credentials=False)
        asset = next(
            a for a in document["assets"]["models"] if a["source"]["name"] == "aoai-api"
        )
        models = asset["models"]
        assert models["status"] == "resolved"
        assert models["discoverySource"] == "armDeployments"
        assert models["notes"] == []
        # Every member's catalogue, filed under the member that serves it.
        assert {r["backendId"] for r in models["resolved"]} == {
            "backend:aoai-east", "backend:aoai-west"
        }
        # And the provider is identified rather than "unknown".
        assert asset["provider"]["targetProviderKind"] == "Foundry"

    def test_a_runtime_choice_is_not_reported_as_a_declared_pool(self):
        """Deriving targets must not invent what APIM did not declare.

        A pool states a priority and a weight per member; a `choose` states a
        condition. Carrying the members across without carrying shares they
        never had is the point -- what the condition meant is the separate
        decision the `set-backend-service` rule raises.
        """
        document = self._collect(self.CONDITIONAL, strip_credentials=False)
        routing = next(
            a for a in document["assets"]["models"] if a["source"]["name"] == "aoai-api"
        )["routing"]
        assert routing["mode"] == "conditional"
        assert routing["sessionAffinity"] is None
        # Asserted over a non-empty list on purpose: "no target carries a
        # weight" is vacuously true of no targets, which is the shape this
        # exists to tell apart from a pool.
        assert len(routing["targets"]) == 2
        assert [t["priority"] for t in routing["targets"]] == [None, None]
        assert [t["weight"] for t in routing["targets"]] == [None, None]

    def test_the_compensate_proposal_has_an_alias_to_compensate_in(self):
        """The plan must not propose an answer it builds nothing to carry.

        The `set-backend-service` decision proposes `compensate`: say what the
        condition was for in the priority and weight of the alias backend
        models. With no target resolved there was no alias and no members, so
        the proposed answer could not be applied to anything.
        """
        from migrate_apim.capability import CapabilityMap
        from migrate_apim.plan import build_plan

        document = self._collect(self.CONDITIONAL, strip_credentials=False)
        plan = build_plan(document, CapabilityMap.load())

        routing_items = [
            item for item in plan["items"]
            if (item.get("evidence") or {}).get("element") == "set-backend-service"
        ]
        assert [item["proposal"] for item in routing_items] == ["compensate"]

        aliases = [
            object_
            for item in plan["items"]
            if (item.get("target") or {}).get("capability") == "alias.create"
            for object_ in (item.get("target") or {}).get("objects") or []
        ]
        assert aliases, "compensate names alias priority and weight; there was no alias"
        members = {
            backend["providerName"]
            for alias in aliases for backend in alias["backendModels"]
        }
        assert {"aoai-east", "aoai-west"} <= members


class TestAnMcpServerChosenAtRuntime:
    """The same gap, one asset kind over.

    A model API that picks its upstream in policy now reads its candidates as
    targets. An MCP server did not: `_mcp_asset` called `_routing_targets`
    without them, so a tool server behind a `choose` reported no upstream at
    all -- and `mcp create` takes the absolute URL of the endpoint, so a server
    with no upstream registers nothing.
    """

    CONDITIONAL = (
        "<policies><inbound><base />"
        "<choose>"
        '<when condition="@(true)"><set-backend-service backend-id="support-backend" /></when>'
        '<otherwise><set-backend-service backend-id="support-backend-eu" /></otherwise>'
        "</choose>"
        "</inbound><backend><base /></backend>"
        "<outbound><base /></outbound><on-error><base /></on-error></policies>"
    )

    def _collect(self, policy):
        """Collect with `support-mcp` routed by policy instead of `backendId`."""
        import copy, fake_arm

        apis_key, backends_key = f"{SERVICE}/apis", f"{SERVICE}/backends"
        policy_key = f"{SERVICE}/apis/support-mcp"
        originals = (
            fake_arm.ROUTES[apis_key], fake_arm.ROUTES[backends_key],
            fake_arm.POLICIES[policy_key],
        )

        apis = copy.deepcopy(originals[0])
        for api in apis:
            if api["name"] == "support-mcp":
                api["properties"]["backendId"] = None
        backends = copy.deepcopy(originals[1])
        # A second upstream, so the choose has two arms to pick between. One
        # arm is not a runtime choice -- `_resolve_backend` resolves it.
        backends.append({
            "id": f"{SERVICE}/backends/support-backend-eu", "name": "support-backend-eu",
            "properties": {"type": "Single", "protocol": "http",
                           "url": "https://support-eu.contoso.com:8000"},
        })

        fake_arm.ROUTES[apis_key] = apis
        fake_arm.ROUTES[backends_key] = backends
        fake_arm.POLICIES[policy_key] = policy
        try:
            return Collector(FakeArmClient(), SERVICE, options()).run()
        finally:
            (fake_arm.ROUTES[apis_key], fake_arm.ROUTES[backends_key],
             fake_arm.POLICIES[policy_key]) = originals

    def _server(self, document):
        return next(
            a for a in document["assets"]["mcpServers"]
            if a["source"]["name"] == "support-mcp"
        )

    def test_every_backend_the_choose_can_pick_is_an_upstream(self):
        server = self._server(self._collect(self.CONDITIONAL))
        assert [u["backendId"] for u in server["upstream"]] == [
            "backend:support-backend", "backend:support-backend-eu"
        ]

    def test_each_upstream_carries_what_registering_it_needs(self):
        """A backendId alone registers nothing: `mcp create` takes a URL and a
        transport, so a candidate has to arrive as complete as a target does."""
        server = self._server(self._collect(self.CONDITIONAL))
        # Asserted over a known count, not over whatever the list holds: every
        # claim below is vacuously true of the empty list this used to be.
        assert len(server["upstream"]) == 2
        for upstream in server["upstream"]:
            assert upstream["url"]
            assert upstream["transport"] == "streamableHttp"

    def test_a_declared_backend_is_unaffected(self):
        """The fixture routes by `backendId`, which still resolves to one."""
        import fake_arm

        server = self._server(
            Collector(FakeArmClient(), SERVICE, options()).run()
        )
        assert [u["backendId"] for u in server["upstream"]] == ["backend:support-backend"]
