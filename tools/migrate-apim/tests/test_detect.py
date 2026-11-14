from migrate_apim import detect


def api(name="x", **props):
    base = {"type": "http", "displayName": name, "path": name}
    base.update(props)
    return {"name": name, "properties": base}


def classify(api_payload, *, backend=None, backend_urls=(), operation_paths=(), elements=(), families=()):
    return detect.classify_api(
        api_payload,
        backend=backend,
        backend_urls=list(backend_urls),
        operation_paths=list(operation_paths),
        policy_element_names=set(elements),
        policy_families=set(families),
    )


class TestFirstClassTypes:
    def test_mcp_api_with_backend_is_passthrough(self):
        result = classify(api("m", type="mcp", backendId="b", mcpProperties={"transportType": "streamable"}))
        assert (result.kind, result.pattern, result.confidence) == ("mcpServer", "passthrough", "high")

    def test_mcp_api_with_tools_is_a_tool_projection(self):
        result = classify(api("m", type="mcp", mcpTools=[{"name": "t", "operationId": "/x"}]))
        assert result.pattern == "toolProjection"

    def test_mcp_api_marked_as_router_is_a_federation_router(self):
        result = classify(api("m", type="mcp", mcpProperties={"isFederationRouter": True}))
        assert result.pattern == "federationRouter"

    def test_mcp_api_with_nothing_configured_is_reported_as_unconfigured(self):
        result = classify(api("m", type="mcp", mcpProperties=None, mcpTools=[]))
        assert result.pattern == "unconfigured"

    def test_agent_api_is_detected_from_a2a_properties(self):
        result = classify(api("a", a2aProperties={"agentCard": {}}))
        assert (result.kind, result.pattern) == ("agent", "a2a")

    def test_agent_api_is_detected_from_is_agent_flag(self):
        assert classify(api("a", isAgent=True)).kind == "agent"


class TestModelDetection:
    def test_foundry_backend_resource_id_is_a_strong_signal(self):
        backend = {
            "properties": {
                "url": "https://acct.openai.azure.com/",
                "resourceId": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/acct",
            }
        }
        result = classify(api("aoai"), backend=backend, backend_urls=["https://acct.openai.azure.com/"])
        assert result.kind == "modelApi"
        assert result.confidence == "high"
        assert result.provider.kind == "foundry"

    def test_third_party_host_is_recognised(self):
        result = classify(api("claude"), backend_urls=["https://api.anthropic.com/v1"])
        assert result.provider.kind == "anthropic"
        assert result.provider.target_provider_kind == "Custom"

    def test_llm_policy_alone_reaches_medium_confidence(self):
        result = classify(api("gw", serviceUrl="https://internal.contoso.com"), elements=["llm-token-limit"])
        assert result.kind == "modelApi"
        assert result.confidence == "medium"

    def test_naming_alone_is_low_confidence_and_flagged(self):
        result = classify(api("gpt-proxy", serviceUrl="https://internal.contoso.com"))
        assert (result.kind, result.confidence) == ("modelApi", "low")
        assert [signal.type for signal in result.signals] == ["naming"]

    def test_plain_rest_api_is_excluded_with_a_reason(self):
        result = classify(api("orders", serviceUrl="https://orders.contoso.com"))
        assert result.kind == "excluded"
        assert "No model, MCP, or agent signal" in result.reason

    def test_signals_are_reported_for_audit(self):
        result = classify(
            api("aoai"),
            backend_urls=["https://acct.openai.azure.com/"],
            operation_paths=["/deployments/{deployment-id}/chat/completions"],
        )
        payload = result.to_dict()
        assert payload["providerGuess"] == "foundry"
        assert {signal["type"] for signal in payload["signals"]} >= {"backendUrl", "operationPath"}


class TestProviderRules:
    def test_wildcard_hosts_match(self):
        assert detect.provider_for_url("https://acct.services.ai.azure.com/").kind == "foundry"
        assert detect.provider_for_url("https://bedrock-runtime.us-east-1.amazonaws.com").kind == "bedrock"
        assert detect.provider_for_url("https://us-central1-aiplatform.googleapis.com").kind == "vertex"

    def test_unknown_host_has_no_rule(self):
        assert detect.provider_for_url("https://contoso.com") is None

    def test_missing_url_is_safe(self):
        assert detect.provider_for_url(None) is None

    def test_every_provider_declares_a_target_kind(self):
        assert all(rule.target_provider_kind in {"Foundry", "Custom"} for rule in detect.PROVIDERS)


class TestImportConvention:
    """APIM's AI import names the backend after the protocol it imported.

    Observed consistently across two live instances. Reading it means the
    provider rarely has to be asked about.
    """

    def test_openai_suffix_declares_the_openai_protocol(self):
        assert detect.protocol_from_backend_name("meta-ai-openai-endpoint") == {
            "providerKind": "openAiCompatible",
            "apiDialect": "openAIChatCompletions",
            "targetProviderKind": "Custom",
            # Knowing it speaks OpenAI is also knowing where its model list is.
            "catalog": "modelsEndpoint",
            "basis": "importConvention",
        }

    def test_ai_suffix_declares_foundry(self):
        found = detect.protocol_from_backend_name("a2a-intent-fdry-9a73-ai-endpoint")
        assert (found["providerKind"], found["targetProviderKind"]) == ("foundry", "Foundry")

    def test_other_names_declare_nothing(self):
        assert detect.protocol_from_backend_name("orders-backend") is None
        assert detect.protocol_from_backend_name(None) is None


class TestPublishableSurface:
    """AI Gateway publishes four inference routes; everything else has no target."""

    def test_the_four_target_routes(self):
        assert sorted(detect.TARGET_ROUTES.values()) == [
            "/openai/v1/chat/completions", "/openai/v1/embeddings",
            "/openai/v1/responses", "/v1/messages",
        ]

    def test_inference_routes_are_publishable(self):
        for template, group in [
            ("/openai/deployments/{deployment-id}/chat/completions?api-version={v}", "chatCompletions"),
            ("/openai/deployments/{deployment-id}/embeddings?api-version={v}", "embeddings"),
            ("/openai/responses?api-version={v}", "responses"),
            ("/anthropic/v1/messages", "messages"),
        ]:
            result = detect.classify_operation(template)
            assert (result["group"], result["publishable"]) == (group, True), template
            assert result["route"] == detect.TARGET_ROUTES[group]

    def test_assistants_surface_has_no_target(self):
        for template, group in [
            ("/openai/assistants/{assistant_id}?api-version={v}", "assistants"),
            ("/openai/threads/{thread_id}/runs?api-version={v}", "threads"),
            ("/openai/vector_stores/{vector_store_id}/files?api-version={v}", "vectorStores"),
            ("/openai/deployments/{d}/audio/speech?api-version={v}", "audio"),
            ("/openai/deployments/{d}/images/generations?api-version={v}", "images"),
            ("/openai/deployments/{d}/completions?api-version={v}", "legacyCompletions"),
        ]:
            result = detect.classify_operation(template)
            assert (result["group"], result["publishable"]) == (group, False), template

    def test_container_resources_win_over_the_verbs_they_contain(self):
        # /threads/{id}/messages is a thread operation, not the Anthropic route.
        assert detect.classify_operation(
            "/openai/threads/{thread_id}/messages?api-version={v}"
        )["group"] == "threads"

    def test_chat_completions_is_not_legacy_completions(self):
        assert detect.classify_operation("/v1/chat/completions")["group"] == "chatCompletions"

    def test_subresources_of_a_publishable_group_are_not_claimed(self):
        result = detect.classify_operation("/openai/responses/{response_id}/input_items")
        assert result["group"] == "responses"
        assert result["subresource"] is True
        assert result["route"] is None

    def test_summary_splits_publishable_from_not(self):
        summary = detect.summarize_surface([
            "/openai/deployments/{d}/chat/completions?api-version={v}",
            "/openai/threads?api-version={v}",
            "/openai/threads/{thread_id}?api-version={v}",
            "/openai/vector_stores?api-version={v}",
        ])
        assert summary["status"] == "bounded"
        assert (summary["publishableCount"], summary["unpublishableCount"]) == (1, 3)
        assert [entry["group"] for entry in summary["unpublishable"]] == ["threads", "vectorStores"]

    def test_wildcard_surface_is_unbounded_not_empty(self):
        # Reporting zero inference routes would read as "nothing to migrate".
        summary = detect.summarize_surface(["/*", "/*"])
        assert summary["status"] == "unbounded"
        assert summary["publishableCount"] == 0
        assert "cannot be read from configuration" in summary["note"]

    def test_no_operations_is_unknown_not_empty(self):
        summary = detect.summarize_surface([])
        assert summary["status"] == "unknown"
        assert "undetermined rather than empty" in summary["note"]


class TestDialects:
    def test_inference_paths_map_to_dialects(self):
        assert detect.api_dialect_for_paths(["/chat/completions"]) == ["openAIChatCompletions"]
        assert detect.api_dialect_for_paths(["/v1/messages"]) == ["anthropicMessages"]
        assert detect.api_dialect_for_paths(["/embeddings"]) == ["openAIEmbeddings"]

    def test_unrelated_paths_yield_nothing(self):
        assert detect.api_dialect_for_paths(["/orders/{id}"]) == []
