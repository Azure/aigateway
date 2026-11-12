import pytest

from apim_import.capability import CapabilityMap


@pytest.fixture(scope="module")
def caps():
    return CapabilityMap.load()


class TestCatalogue:
    def test_loads_the_pinned_catalogue(self, caps):
        assert caps.cli_version == "1.0.0b26"
        assert len(caps.capabilities) == 30

    def test_declares_what_the_target_cannot_do(self, caps):
        assert "products" in caps.unsupported
        assert "arbitrary-policy-xml" in caps.unsupported
        assert "workspace-creation" in caps.unsupported

    def test_capabilities_carry_their_known_limitations(self, caps):
        model_update = caps.capability("model.update")
        assert model_update is not None
        assert model_update.limitations

    def test_unprobed_capabilities_claim_nothing_about_the_local_cli(self, caps):
        assert caps.probed is False
        assert all(cap.support == "declared" for cap in caps.capabilities.values())


class TestProbe:
    """The catalogue declares what should exist; the probe says what does."""

    def test_a_missing_command_is_unavailable(self):
        caps = CapabilityMap.load().probe(lambda command: None)
        assert all(cap.support == "unavailable" for cap in caps.capabilities.values())
        assert caps.probed is True

    def test_a_present_command_with_its_options_is_conditional(self):
        caps = CapabilityMap.load().probe(lambda command: {"deployment-config", "api-format",
                                                           "supported-endpoints"})
        assert caps.capability("model.create").support == "conditional"

    def test_a_present_command_missing_a_required_option_is_unavailable(self):
        caps = CapabilityMap.load().probe(lambda command: {"api-format"})
        model_create = caps.capability("model.create")
        assert model_create.support == "unavailable"
        assert "deployment-config" in model_create.missing_options

    def test_usable_tracks_support(self):
        caps = CapabilityMap.load().probe(lambda command: None)
        assert not caps.capability("model.create").usable


class TestPolicyRules:
    def test_an_element_rule_wins_over_the_expression_fallback(self, caps):
        # A token limit with an expression counter-key still maps to tokenLimit.
        rule = caps.policy_rule("llm-token-limit", family="tokenLimit", has_expression=True)
        assert rule["target"] == "tokenLimit"
        assert rule["verdict"] == "native"
        assert rule["partialWhen"] == {"attributeIsExpression": "counter-key"}

    def test_a_family_rule_catches_elements_with_no_rule_of_their_own(self, caps):
        rule = caps.policy_rule("rewrite-uri", family="transform")
        assert rule["verdict"] == "gap"

    def test_expression_is_the_fallback_for_unmapped_elements(self, caps):
        rule = caps.policy_rule("some-future-policy", family="other", has_expression=True)
        assert rule["verdict"] == "gap"
        assert (rule.get("match") or {}).get("hasExpression") is True

    def test_an_unmapped_element_without_an_expression_matches_nothing(self, caps):
        assert caps.policy_rule("some-future-policy", family="other") is None

    def test_plumbing_is_explicitly_not_applicable(self, caps):
        for name in ("base", "include-fragment", "choose", "set-variable", "cors"):
            assert caps.policy_rule(name, family="composition")["verdict"] == "notApplicable"

    def test_backend_selection_is_handled_by_the_alias(self, caps):
        assert caps.policy_rule("set-backend-service", family="routing")["verdict"] == "handled"


class TestTargetSurface:
    def test_the_rules_carry_the_four_publishable_routes(self, caps):
        assert sorted(caps.publishable_routes()) == [
            "/openai/v1/chat/completions", "/openai/v1/embeddings",
            "/openai/v1/responses", "/v1/messages",
        ]

    def test_every_asset_rule_names_a_real_capability(self, caps):
        for rule in caps.asset_rules():
            capability_id = rule.get("capabilityId")
            if capability_id:
                assert caps.capability(capability_id) is not None, capability_id

    def test_every_policy_rule_names_a_real_capability(self, caps):
        for rule in caps.rules.get("policies", []):
            capability_id = rule.get("capabilityId")
            if capability_id:
                assert caps.capability(capability_id) is not None, capability_id

    def test_an_unknown_coverage_gap_cannot_be_accepted(self, caps):
        rule = next(
            r for r in caps.structural_rules() if (r.get("match") or {}).get("kind") == "coverageGap"
        )
        assert rule["cannotAccept"] is True
        assert rule["blocking"] is True
