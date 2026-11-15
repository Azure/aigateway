"""What the compiler has to catch.

Most of these fixtures are not hypothetical. `mcp import` and
`model-provider import --foundry` are the two capabilities that shipped in the
b30 catalog and passed every test in this suite, because the offline probe
answers whatever the fake says. The dead-rule cases are the shapes that were
sitting in rules.json. A compiler nobody has watched fail is not worth trusting,
so each check is exercised against the defect it exists for.
"""

import copy
import json

import pytest

from migrate_apim import dispatch
from migrate_apim.capability import CAPABILITIES_DIR, DEFAULT_CATALOG
from migrate_apim.compile import compile_contract, find_surface

CLI_DIR = CAPABILITIES_DIR.parent.parent.parent / "cli"


@pytest.fixture(scope="module")
def shipped():
    catalog = json.loads((CAPABILITIES_DIR / DEFAULT_CATALOG).read_text(encoding="utf-8"))
    rules = json.loads((CAPABILITIES_DIR / "rules.json").read_text(encoding="utf-8"))
    surface = json.loads(find_surface(catalog).read_text(encoding="utf-8"))
    return catalog, rules, surface


@pytest.fixture
def compile_with(tmp_path, shipped):
    """Compile a variation on the shipped contract, and return its diagnostics."""
    def run(*, catalog=None, rules=None, surface=None, cli_dir=None):
        base_catalog, base_rules, base_surface = shipped
        catalog = catalog if catalog is not None else base_catalog
        rules = rules if rules is not None else base_rules
        surface = surface if surface is not None else base_surface
        version = (catalog.get("cliEvidence") or {}).get("documentedVersion")
        paths = {}
        for name, payload in (
            (f"aigateway-{version}.json", catalog),
            ("rules.json", rules),
            (f"cli-surface-{version}.json", surface),
        ):
            path = tmp_path / name
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            paths[name] = path
        return compile_contract(
            paths[f"aigateway-{version}.json"],
            paths["rules.json"],
            paths[f"cli-surface-{version}.json"],
            cli_dir=cli_dir,
        )
    return run


def codes(result):
    return {d.check for d in result.errors}


class TestTheShippedContractCompiles:
    def test_it_has_no_errors(self, compile_with):
        result = compile_with()
        assert result.errors == [], "\n".join(str(d) for d in result.errors)

    def test_the_real_catalog_and_rules_compile_in_place(self):
        catalog_path = CAPABILITIES_DIR / DEFAULT_CATALOG
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        result = compile_contract(
            catalog_path, CAPABILITIES_DIR / "rules.json", find_surface(catalog),
            cli_dir=CLI_DIR if CLI_DIR.is_dir() else None,
        )
        assert result.errors == [], "\n".join(str(d) for d in result.errors)


class TestCommandsThatCannotBeExecuted:
    """The b30 defects, as they shipped."""

    def test_a_command_in_no_release_is_caught(self, compile_with, shipped):
        catalog = copy.deepcopy(shipped[0])
        catalog["capabilities"].append({
            "id": "mcp.import", "command": ["mcp", "import"], "read": ["mcp", "show"],
            "kind": "create", "options": ["sources"], "required": ["sources"],
            "approvalClass": "consequential", "limitations": [],
        })
        result = compile_with(catalog=catalog)
        assert "command-exists" in codes(result)
        assert any("mcp import" in str(d) for d in result.errors)

    def test_a_misspelled_required_flag_is_caught(self, compile_with, shipped):
        catalog = copy.deepcopy(shipped[0])
        for capability in catalog["capabilities"]:
            if capability["id"] == "provider.import":
                capability["options"] = ["foundry"]
                capability["required"] = ["foundry"]
        result = compile_with(catalog=catalog)
        assert "required-option-exists" in codes(result)
        assert any("--foundry" in str(d) for d in result.errors)

    def test_a_required_option_it_does_not_declare_is_caught(self, compile_with, shipped):
        catalog = copy.deepcopy(shipped[0])
        catalog["capabilities"][0]["required"] = ["not-in-options"]
        assert "required-subset-of-options" in codes(compile_with(catalog=catalog))


class TestRulesThatCannotBeApplied:
    def test_a_rule_no_site_selects_is_caught(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rules["assets"].append({
            "match": {"family": "models", "modelsStatus": ["resolved"]},
            "verdict": "native", "capabilityId": "model.create",
        })
        result = compile_with(rules=rules)
        assert "rule-reachable" in codes(result)

    def test_an_invented_match_key_is_caught(self, compile_with, shipped):
        # A key no collector emits. The rule looks plausible and selects nothing.
        rules = copy.deepcopy(shipped[1])
        rules["assets"].append({
            "match": {"family": "mcpServers", "isPartOfBulkImportable": True},
            "verdict": "native", "capabilityId": "mcp.create",
        })
        assert "rule-reachable" in codes(compile_with(rules=rules))

    def test_a_match_value_outside_the_vocabulary_is_caught(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rules["assets"].append({
            "match": {"family": "mcpServers", "pattern": "notAPattern"},
            "verdict": "native", "capabilityId": "mcp.create",
        })
        assert "match-value-known" in codes(compile_with(rules=rules))

    def test_a_rule_naming_an_absent_capability_is_caught(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rules["assets"][0] = {**rules["assets"][0], "capabilityId": "mcp.teleport"}
        assert "rule-capability-exists" in codes(compile_with(rules=rules))

    def test_two_rules_one_site_cannot_tell_apart_are_caught(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        first = next(r for r in rules["assets"] if (r["match"].get("pattern")))
        rules["assets"].append(copy.deepcopy(first))
        assert "rule-unique" in codes(compile_with(rules=rules))

    def test_a_partial_rule_without_options_is_caught(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rules["structural"].append({"match": {"kind": "subscriptions"}, "verdict": "partial"})
        assert "partial-needs-options" in codes(compile_with(rules=rules))

    def test_a_proposal_that_is_not_an_option_is_caught(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rule = next(r for r in rules["assets"] if r.get("verdict") == "partial")
        rule["proposal"] = "something-else"
        assert "proposal-is-an-option" in codes(compile_with(rules=rules))


class TestTheSnapshotIsOfThisRelease:
    """The digest is the only thing joining an offline check to a real wheel."""

    def test_a_snapshot_for_another_wheel_is_caught(self, compile_with, shipped):
        surface = copy.deepcopy(shipped[2])
        surface["wheelSha256"] = "0" * 64
        result = compile_with(surface=surface)
        assert "snapshot-matches-catalog" in codes(result)

    def test_a_snapshot_for_another_version_is_caught(self, compile_with, shipped):
        surface = copy.deepcopy(shipped[2])
        surface["extensionVersion"] = "1.0.0b1"
        assert "snapshot-matches-catalog" in codes(compile_with(surface=surface))

    def test_a_missing_snapshot_is_reported_not_ignored(self, tmp_path, shipped):
        catalog, rules, _ = shipped
        catalog_path = tmp_path / f"aigateway-{catalog['cliEvidence']['documentedVersion']}.json"
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        rules_path = tmp_path / "rules.json"
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        result = compile_contract(catalog_path, rules_path, tmp_path / "absent.json")
        assert not result.ok()
        assert any("export_cli_surface" in str(d) for d in result.errors)


class TestThePinsAgree:
    def test_a_catalog_filename_that_lies_is_caught(self, tmp_path, shipped):
        catalog, rules, surface = shipped
        wrong = tmp_path / "aigateway-1.0.0b26.json"
        wrong.write_text(json.dumps(catalog), encoding="utf-8")
        rules_path = tmp_path / "rules.json"
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        surface_path = tmp_path / "surface.json"
        surface_path.write_text(json.dumps(surface), encoding="utf-8")
        result = compile_contract(wrong, rules_path, surface_path)
        assert "catalog-filename" in codes(result)

    def test_rules_targeting_another_catalog_are_caught(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rules["targetCapabilities"] = "aigateway-1.0.0b26"
        assert "rules-target-catalog" in codes(compile_with(rules=rules))

    @pytest.mark.skipif(not CLI_DIR.is_dir(), reason="needs cli/ beside tools/")
    def test_the_installers_carry_the_catalogs_pin(self, compile_with):
        result = compile_with(cli_dir=CLI_DIR)
        assert "installer-pin" not in codes(result), (
            "\n".join(str(d) for d in result.errors)
        )


class TestTheShapesAreClosed:
    """`additionalProperties: false` is the cheapest guard against an invented key."""

    def test_an_unknown_rule_field_is_rejected(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rules["assets"][0] = {**rules["assets"][0], "blockingWhenever": True}
        assert "schema" in codes(compile_with(rules=rules))

    def test_an_unknown_match_key_is_rejected_at_the_shape_level(self, compile_with, shipped):
        # The same defect as test_an_invented_match_key_is_caught, one layer out:
        # the schema rejects it before reachability has to reason about it.
        rules = copy.deepcopy(shipped[1])
        rules["assets"][0]["match"]["isPartOfBulkImportable"] = True
        assert "schema" in codes(compile_with(rules=rules))

    def test_an_unknown_capability_field_is_rejected(self, compile_with, shipped):
        catalog = copy.deepcopy(shipped[0])
        catalog["capabilities"][0]["sources"] = ["x"]
        assert "schema" in codes(compile_with(catalog=catalog))

    def test_a_digest_that_is_not_one_is_rejected(self, compile_with, shipped):
        catalog = copy.deepcopy(shipped[0])
        catalog["cliEvidence"]["wheelSha256"] = "not-a-digest"
        assert "schema" in codes(compile_with(catalog=catalog))

    def test_the_rich_option_shape_is_accepted(self, compile_with, shipped):
        # The telemetry rule carries {value, consequence} options rather than
        # bare strings; both shapes are legitimate.
        rules = copy.deepcopy(shipped[1])
        rule = next(r for r in rules["structural"] if (r["match"]["kind"]) == "telemetry")
        assert any(isinstance(option, dict) for option in rule["options"])
        assert "schema" not in codes(compile_with(rules=rules))


class TestTheRegistryDescribesThePlanner:
    """If the registry were a second declaration it would drift; it is not."""

    def test_every_section_has_at_least_one_site(self):
        sections = {selector.section for selector in dispatch.REGISTRY}
        assert sections == {"assets", "structural", "policies"}

    def test_a_selector_rejects_a_rule_pinning_a_key_it_ignores(self):
        site = next(s for s in dispatch.REGISTRY if s.site == "plan._agent")
        assert site.governs({"match": {"family": "agents"}})
        # An extra key would be silently ignored at selection time, so the rule
        # would match more broadly than it reads.
        assert not site.governs({"match": {"family": "agents", "pattern": "passthrough"}})

    def test_a_selector_rejects_a_value_it_never_compares_against(self):
        site = next(s for s in dispatch.REGISTRY if s.site == "plan._agent")
        assert not site.governs({"match": {"family": "models"}})
