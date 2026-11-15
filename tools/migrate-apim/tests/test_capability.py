import json
import subprocess

import pytest

from migrate_apim.azcli import az_argv
from migrate_apim.capability import (
    CAPABILITIES_DIR,
    DEFAULT_CATALOG,
    CapabilityError,
    CapabilityMap,
    az_option_probe,
)


@pytest.fixture(scope="module")
def caps():
    return CapabilityMap.load()


def _installed_cli_version() -> str | None:
    """The version of the `az aigateway` extension on PATH, if any."""
    try:
        proc = subprocess.run(
            az_argv(["az", "aigateway", "version", "-o", "json"]),
            capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout).get("extensionVersion")
    except json.JSONDecodeError:
        return None


class TestCatalogue:
    def test_loads_the_pinned_catalogue(self, caps):
        assert caps.cli_version == "1.0.0b31"
        assert len(caps.capabilities) == 31

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


class TestProbeNeedsTheExtension:
    """An uninstalled extension is an unknown about the CLI, not a missing target
    capability. Reporting it as absence demotes native mappings to blocking
    losses, so the probe refuses rather than guessing."""

    def test_an_absent_extension_refuses_to_probe(self):
        with pytest.raises(CapabilityError, match="not installed"):
            CapabilityMap.load().probe(lambda command: None, available=lambda: False)

    def test_refusing_leaves_the_table_untouched(self):
        caps = CapabilityMap.load()
        with pytest.raises(CapabilityError):
            caps.probe(lambda command: None, available=lambda: False)
        assert caps.probed is False
        assert all(cap.support == "declared" for cap in caps.capabilities.values())

    def test_a_present_extension_probes_normally(self):
        caps = CapabilityMap.load().probe(lambda command: None, available=lambda: True)
        assert caps.probed is True
        assert all(cap.support == "unavailable" for cap in caps.capabilities.values())

    def test_supplying_a_probe_answers_the_presence_question(self):
        # Tests inject a probe and never shell out; that assertion stands alone.
        caps = CapabilityMap.load().probe(lambda command: {"deployment-config", "api-format",
                                                           "supported-endpoints"})
        assert caps.capability("model.create").support == "conditional"


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


class TestTheDefaultCatalogueResolves:
    """Every entry point that does not pass --capabilities falls back to
    DEFAULT_CATALOG. A rename that leaves the constant behind does not degrade
    `plan`, it stops it, and it takes the whole suite's fixtures with it."""

    def test_the_default_names_a_file_that_exists(self):
        assert (CAPABILITIES_DIR / DEFAULT_CATALOG).is_file(), (
            f"DEFAULT_CATALOG={DEFAULT_CATALOG!r} is not in {CAPABILITIES_DIR}: "
            f"{sorted(p.name for p in CAPABILITIES_DIR.iterdir())}"
        )

    def test_loading_without_a_path_works(self):
        assert CapabilityMap.load().cli_version

    def test_the_filename_matches_the_version_it_documents(self, caps):
        assert DEFAULT_CATALOG == f"aigateway-{caps.cli_version}.json"

    def test_a_plan_records_the_catalogue_it_was_built_against(self):
        # Not the default, when one was supplied: the plan has to say which
        # table it was planned against for a resumed session to be comparable.
        path = CAPABILITIES_DIR / DEFAULT_CATALOG
        assert CapabilityMap.load(catalog_path=path).to_dict()["catalog"] == path.stem


class TestTheCatalogueOnlyDeclaresRealCommands:
    """The catalogue is a claim about an `az aigateway` release. The offline
    suite injects a probe, so a fabricated command or a misspelled flag passes
    every other test here -- `mcp import` and `model-provider import --foundry`
    both shipped that way. This reconciles the claim against the real wheel,
    and skips rather than guesses when that wheel is not installed."""

    def test_required_options_are_declared_options(self, caps):
        for capability in caps.capabilities.values():
            assert set(capability.required) <= set(capability.options), capability.id

    def test_every_declared_command_exists_in_the_documented_release(self, caps):
        installed = _installed_cli_version()
        if installed != caps.cli_version:
            pytest.skip(
                f"needs the documented az aigateway {caps.cli_version} installed "
                f"(found {installed or 'no extension'})"
            )
        unavailable = {}
        for capability in caps.capabilities.values():
            options = az_option_probe(capability.command)
            if options is None:
                unavailable[capability.id] = (
                    f"`az aigateway {' '.join(capability.command)}` does not exist"
                )
                continue
            missing = sorted(set(capability.required) - options)
            if missing:
                unavailable[capability.id] = (
                    f"`az aigateway {' '.join(capability.command)}` exposes no {missing}"
                )
        assert not unavailable, (
            "the catalogue declares what the installed CLI does not expose: "
            + json.dumps(unavailable, indent=2)
        )
