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

from migrate_apim import compile, dispatch
from migrate_apim.capability import CAPABILITIES_DIR, DEFAULT_CATALOG
from migrate_apim.compile import compile_contract, find_surface


@pytest.fixture(scope="module")
def shipped():
    catalog = json.loads((CAPABILITIES_DIR / DEFAULT_CATALOG).read_text(encoding="utf-8"))
    rules = json.loads((CAPABILITIES_DIR / "rules.json").read_text(encoding="utf-8"))
    surface = json.loads(find_surface(catalog).read_text(encoding="utf-8"))
    return catalog, rules, surface


@pytest.fixture
def compile_with(tmp_path, shipped):
    """Compile a variation on the shipped contract, and return its diagnostics."""
    def run(*, catalog=None, rules=None, surface=None, newest_release=None):
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
            newest_release=newest_release,
        )
    return run


def codes(result):
    return {d.check for d in result.errors}


def one_newer(version: str) -> str:
    """A release after this one, derived rather than written down.

    A literal here is the same trap as a literal in the catalog: it is newer
    than today's pin and older than tomorrow's, so the case it was meant to
    exercise quietly stops firing on the first adoption.
    """
    head, _, beta = version.rpartition("b")
    return f"{head}b{int(beta) + 1}"


class TestTheShippedContractCompiles:
    def test_it_has_no_errors(self, compile_with):
        result = compile_with()
        assert result.errors == [], "\n".join(str(d) for d in result.errors)

    def test_the_real_catalog_and_rules_compile_in_place(self):
        catalog_path = CAPABILITIES_DIR / DEFAULT_CATALOG
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        result = compile_contract(
            catalog_path, CAPABILITIES_DIR / "rules.json", find_surface(catalog),
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
        assert any("azcli_aigw_export" in str(d) for d in result.errors)


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

    def test_an_asset_rule_matching_on_nothing_is_rejected(self, compile_with, shipped):
        # Reachability cannot catch this one: an empty match is a subset of
        # every site's keys, so every site governs it -- and none ever selects
        # it, because selection compares values.
        rules = copy.deepcopy(shipped[1])
        rules["assets"].append({"match": {}, "verdict": "gap"})
        assert "schema" in codes(compile_with(rules=rules))

    def test_a_structural_rule_without_a_verdict_is_rejected(self, compile_with, shipped):
        # `_structural` consults the rule for its verdict now, rather than
        # hardcoding one per branch, so the exemption these had is gone.
        rules = copy.deepcopy(shipped[1])
        rules["structural"] = [
            {k: v for k, v in r.items() if k != "verdict"} if r["match"]["kind"] == "telemetry"
            else r
            for r in rules["structural"]
        ]
        result = compile_with(rules=rules)
        assert {"schema", "rule-has-verdict"} & codes(result)


class TestTheCatalogCarriesWhatTheCliInsistsOn:
    """The snapshot records which options the CLI marks [Required]. That half of
    it was written and read by nobody, so a release making an option mandatory
    compiled clean and failed at run time instead."""

    def test_an_option_the_cli_requires_must_be_declared(self, compile_with, shipped):
        surface = copy.deepcopy(shipped[2])
        surface["commands"]["mcp create"]["required"].append("failure-mode")
        result = compile_with(surface=surface)
        assert "cli-required-option-declared" in codes(result)
        assert any("--failure-mode" in str(d) for d in result.errors)

    def test_identity_arguments_are_not_held_against_the_catalog(self, compile_with, shipped):
        # `apply` supplies --gateway-name and friends from the plan's target, so
        # the catalog has no reason to carry them and the shipped one does not.
        surface = copy.deepcopy(shipped[2])
        surface["commands"]["mcp create"]["required"] = sorted(
            {*surface["commands"]["mcp create"]["required"], "gateway-name", "name"}
        )
        assert "cli-required-option-declared" not in codes(compile_with(surface=surface))


class TestEveryRuleFieldHasAReader:
    """A field nothing reads is the same defect as an unreadable match key --
    something written expecting an effect it does not have."""

    def test_a_field_no_site_reads_is_reported(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rules["structural"] = [
            {**r, "prerequisiteWhen": ["flatten"]} if r["match"]["kind"] == "workspace" else r
            for r in rules["structural"]
        ]
        result = compile_with(rules=rules)
        unread = [d for d in result.warnings if d.check == "rule-field-unread"]
        assert any("prerequisiteWhen" in str(d) for d in unread), result.warnings

    def test_the_same_field_is_fine_where_a_site_does_read_it(self, compile_with, shipped):
        # The telemetry branch reads prerequisiteWhen; the workspace one does not.
        # Which is the point of asking the site rather than keeping a list here.
        assert not [d for d in compile_with().warnings if d.check == "rule-field-unread"]

    def test_match_and_note_are_never_reported(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rules["assets"][0] = {**rules["assets"][0], "note": "for a human reader"}
        assert not [d for d in compile_with(rules=rules).warnings
                    if d.check == "rule-field-unread"]

    def test_an_unreachable_rule_is_not_also_reported_field_by_field(
        self, compile_with, shipped
    ):
        """Nothing can select it, so every field is unread by construction.
        Saying so once per field buries the reachability error underneath."""
        rules = copy.deepcopy(shipped[1])
        rules["structural"].append({
            "match": {"kind": "policyFragments"}, "verdict": "handled",
            "itemKind": "accept-loss", "rationale": "x", "proposal": "accept",
        })
        result = compile_with(rules=rules)
        assert "match-value-known" in codes(result)
        assert not [d for d in result.warnings
                    if d.check == "rule-field-unread" and "policyFragments" in str(d)]

    def test_the_shipped_rules_leave_nothing_unread(self, compile_with):
        """--strict has to be a mode that can actually pass on this repo's data."""
        assert compile_with().ok(strict=True), [
            str(d) for d in compile_with().diagnostics
        ]


class TestEveryPolicyPassIsCheckedForTies:
    """Ties were checked for the element pass only. The family and expression
    passes are first-match too, and a second rule there was simply never used."""

    def test_two_rules_with_the_same_family_are_caught(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rules["policies"].append({"match": {"family": "transform"}, "verdict": "gap"})
        assert "rule-unique" in codes(compile_with(rules=rules))

    def test_two_expression_fallbacks_are_caught(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rules["policies"].append({"match": {"hasExpression": True}, "verdict": "gap"})
        assert "rule-unique" in codes(compile_with(rules=rules))

    def test_one_repeated_element_among_many_is_still_caught(self, compile_with, shipped):
        rules = copy.deepcopy(shipped[1])
        rules["policies"].append(
            {"match": {"element": ["brand-new", "ip-filter"]}, "verdict": "gap"})
        result = compile_with(rules=rules)
        assert "rule-unique" in codes(result)
        assert any("ip-filter" in str(d) for d in result.errors)


class TestTheCatalogKeepsUpWithTheCli:
    def test_a_newer_release_than_the_catalog_is_reported(self, compile_with, shipped):
        newer = one_newer(shipped[0]["cliEvidence"]["documentedVersion"])
        result = compile_with(newest_release=f"cli-v{newer}")
        assert any(f"{newer} has been released" in str(d) for d in result.suggestions)

    def test_a_newer_release_does_not_fail_the_build(self, compile_with, shipped):
        """A gateway release is not this tool's build to redden. The catalog is
        a claim about one release and stays true when a newer one ships, so
        falling behind is reported and adopted deliberately -- not under the
        duress of every change being blocked until somebody does it."""
        result = compile_with(newest_release="cli-v1.0.0b32")
        assert result.ok(), [str(d) for d in result.errors]

    def test_not_even_strict_fails_on_somebody_elses_release(self, compile_with, shipped):
        """--strict promotes warnings, and this is not one. The catalog is
        right about the release it documents; another one existing is a thing
        to consider, not a defect, and nobody should have to adopt a release
        to get a green build."""
        newer = one_newer(shipped[0]["cliEvidence"]["documentedVersion"])
        result = compile_with(newest_release=f"cli-v{newer}")
        assert result.ok(strict=True), [str(d) for d in result.diagnostics]

    def test_the_release_it_documents_is_not_a_complaint(self, compile_with, shipped):
        documented = shipped[0]["cliEvidence"]["documentedVersion"]
        assert "release-pin" not in codes(compile_with(newest_release=documented))

    def test_an_older_tag_is_not_a_complaint(self, compile_with):
        assert "release-pin" not in codes(compile_with(newest_release="cli-v1.0.0b6"))

    def test_an_unparseable_version_warns_rather_than_passing_quietly(self, compile_with):
        result = compile_with(newest_release="cli-vnightly")
        assert "release-pin" not in codes(result)
        assert any(d.check == "release-pin" for d in result.warnings)

    def test_nothing_to_compare_against_is_silent(self, compile_with):
        """No tags at all is a shallow clone, not a stale catalog."""
        assert compile_with(newest_release="   ").ok()

    def test_it_picks_the_newest_out_of_every_tag(self, compile_with):
        """CI hands it the whole tag list rather than git's idea of the newest,
        so `1.0.0b100` has to beat `1.0.0b99` here and not in `git --sort`."""
        tags = "cli-v1.0.0b6 cli-v1.0.0b99 cli-v1.0.0b31 cli-v1.0.0b100"
        result = compile_with(newest_release=tags)
        assert any("1.0.0b100 has been released" in str(d) for d in result.suggestions)

    def test_an_unreadable_tag_among_readable_ones_is_ignored(self, compile_with, shipped):
        documented = shipped[0]["cliEvidence"]["documentedVersion"]
        result = compile_with(newest_release=f"cli-vnightly cli-v{documented}")
        assert result.ok(strict=True), [str(d) for d in result.diagnostics]

    def test_pinning_an_unpublished_release_is_said_out_loud(self, compile_with):
        """Legitimate while a candidate is being prepared. Worth saying anyway:
        until the tag exists there is no wheel to check the snapshot against,
        so the claim the whole arrangement rests on is unverifiable."""
        result = compile_with(newest_release="cli-v1.0.0b6 cli-v1.0.0b30")
        assert result.ok()
        assert any("newest published release" in str(d) for d in result.warnings)

    @pytest.mark.parametrize("newer,older", [
        ("1.0.0b32", "1.0.0b31"), ("1.0.0b100", "1.0.0b99"),
        ("1.1.0b1", "1.0.0b99"), ("2.0.0b1", "1.9.9b9"),
    ])
    def test_releases_order_by_version_not_by_string(self, newer, older):
        # "1.0.0b100" < "1.0.0b99" as strings, which is how a lexical compare
        # would quietly stop reporting anything after the ninety-ninth release.
        assert compile.release_order(newer) > compile.release_order(older)


class TestTheRegistryDescribesThePlanner:
    """If the registry were a second declaration it would drift; it is not."""

    def test_every_section_has_at_least_one_site(self):
        sections = {selector.section for selector in dispatch.REGISTRY}
        assert sections == {"assets", "structural", "policies"}

    def test_each_structural_branch_declares_its_own_reads(self):
        """One selector for all six branches would have to declare the union of
        what they read, which excuses a field on one rule because another branch
        happens to read it."""
        structural = [s for s in dispatch.REGISTRY if s.section == "structural"]
        assert len(structural) > 1
        telemetry = next(s for s in structural if "telemetry" in s.site)
        workspace = next(s for s in structural if "workspace" in s.site)
        assert "prerequisiteWhen" in telemetry.reads
        assert "prerequisiteWhen" not in workspace.reads

    def test_a_selector_can_go_in_a_set(self):
        # A frozen dataclass holding a Mapping generates a __hash__ that raises.
        assert len(set(dispatch.REGISTRY)) == len(dispatch.REGISTRY)

    def test_a_selector_rejects_a_rule_pinning_a_key_it_ignores(self):
        site = next(s for s in dispatch.REGISTRY if s.site == "plan._agent")
        assert site.governs({"match": {"family": "agents"}})
        # An extra key would be silently ignored at selection time, so the rule
        # would match more broadly than it reads.
        assert not site.governs({"match": {"family": "agents", "pattern": "passthrough"}})

    def test_a_selector_rejects_a_value_it_never_compares_against(self):
        site = next(s for s in dispatch.REGISTRY if s.site == "plan._agent")
        assert not site.governs({"match": {"family": "models"}})


class TestACleanRunSaysWhatItChecked:
    """A compile that only speaks up on failure leaves the reader of a green
    run unable to tell thorough from vacuous -- and this contract shipped a
    command that existed in no release, through a green suite."""

    def test_every_check_reports_what_it_covered(self, compile_with, shipped):
        documented = shipped[0]["cliEvidence"]["documentedVersion"]
        covered = compile_with(newest_release=f"cli-v{documented}").covered
        assert len(covered) == 5, covered

    def test_the_counts_are_the_real_ones(self, compile_with, shipped):
        catalog, rules, surface = shipped
        covered = " ".join(compile_with().covered)
        assert f"{len(catalog['capabilities'])} capabilities" in covered
        assert f"{len(surface['commands'])} commands" in covered

    def test_without_tags_the_release_line_is_absent(self, compile_with):
        """Nothing was compared, so claiming a check ran would be a lie."""
        covered = " ".join(compile_with().covered)
        assert "published release" not in covered
