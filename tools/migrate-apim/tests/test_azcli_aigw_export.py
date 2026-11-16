"""The exporter's offline half.

`scripts/azcli_aigw_export.py` needs an Azure CLI to walk a command tree, but
not to parse help text or to compare two snapshots. Those two are what CI leans
on -- the parser decides what the snapshot says, and the comparison decides
whether the committed one still holds -- so they are tested here without one.
"""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "azcli_aigw_export.py"


def _load():
    spec = importlib.util.spec_from_file_location("azcli_aigw_export", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export = _load()


SURFACE = {
    "schemaVersion": "1.0",
    "kind": "aigatewayCliSurface",
    "extensionVersion": "1.0.0b31",
    "wheelSha256": "a" * 64,
    "generatedBy": {"method": "help-sections", "azureCliCore": "2.90.0"},
    "commands": {
        "mcp create": {"options": ["endpoints", "url"], "required": ["name"]},
        "policy set": {"options": ["token-limit"], "required": []},
    },
}


class TestComparingTwoSnapshots:
    """What the drift check in migrate-apim.yml actually asks."""

    def test_the_same_surface_reports_nothing(self):
        assert export.differences(SURFACE, copy.deepcopy(SURFACE)) == []

    def test_a_different_azure_cli_is_not_a_difference(self):
        """The runner installs whatever azure-cli is current, and the snapshot
        records it. Comparing it would turn every core release into 'the wheel
        has drifted' -- wrong, and the kind of wrong that gets a check muted."""
        other = copy.deepcopy(SURFACE)
        other["generatedBy"]["azureCliCore"] = "2.91.0"
        assert export.differences(SURFACE, other) == []

    def test_a_different_wheel_is_a_difference(self):
        other = copy.deepcopy(SURFACE)
        other["wheelSha256"] = "b" * 64
        assert any("wheelSha256" in line for line in export.differences(SURFACE, other))

    def test_a_removed_command_is_named(self):
        other = copy.deepcopy(SURFACE)
        del other["commands"]["policy set"]
        report = export.differences(SURFACE, other)
        assert report == ["`az aigateway policy set` is gone"]

    def test_a_new_command_is_named(self):
        other = copy.deepcopy(SURFACE)
        other["commands"]["mcp import"] = {"options": [], "required": []}
        assert export.differences(SURFACE, other) == ["`az aigateway mcp import` is new"]

    def test_a_moved_option_is_named_with_its_command(self):
        """The error message is the whole point: it should say what to re-pin."""
        other = copy.deepcopy(SURFACE)
        other["commands"]["mcp create"]["options"] = ["endpoints", "tool-timeout"]
        report = export.differences(SURFACE, other)
        assert "`az aigateway mcp create` no longer options: --url" in report
        assert "`az aigateway mcp create` newly options: --tool-timeout" in report

    def test_an_option_becoming_required_is_a_difference(self):
        other = copy.deepcopy(SURFACE)
        other["commands"]["policy set"]["required"] = ["token-limit"]
        assert export.differences(SURFACE, other) == [
            "`az aigateway policy set` newly required: --token-limit"
        ]

    def test_it_exits_non_zero_only_when_they_differ(self, tmp_path):
        committed = tmp_path / "committed.json"
        fresh = tmp_path / "fresh.json"
        committed.write_text(json.dumps(SURFACE), encoding="utf-8")
        fresh.write_text(json.dumps(SURFACE), encoding="utf-8")
        assert export.main(["--compare", str(committed), str(fresh)]) == 0

        drifted = copy.deepcopy(SURFACE)
        drifted["commands"]["mcp create"]["options"].append("tool-timeout")
        fresh.write_text(json.dumps(drifted), encoding="utf-8")
        assert export.main(["--compare", str(committed), str(fresh)]) == 1

    def test_a_missing_file_is_reported_rather_than_raised(self, tmp_path):
        present = tmp_path / "one.json"
        present.write_text(json.dumps(SURFACE), encoding="utf-8")
        assert export.main(["--compare", str(present), str(tmp_path / "absent.json")]) == 1


class TestReadingHelpText:
    """Help text is a poor source of truth read loosely. These are the two ways
    the parser can be wrong: inventing an option from prose, and dropping a real
    one. Both are pinned against the shape `az ... --help` actually prints."""

    HELP = """
Command
    az aigateway model-provider create : Register a model provider.
        Pass --kind, and --custom or --foundry.

Arguments
    --gateway-name    [Required] : Name of the gateway.
    --kind            [Required] : Provider kind.  Allowed values: custom, foundry.
    --name -n                    : Provider name.
    --foundry                    : Foundry configuration, inline JSON or @file.
                                   Accepts a resource id.
    --import-models              : Import every deployment.

Global Arguments
    --debug                      : Increase logging verbosity.
    --output -o                  : Output format.  Allowed values: json, table.
"""

    def test_it_reads_the_declared_arguments(self):
        options, required = export.parse_options(self.HELP)
        assert options == ["foundry", "gateway-name", "import-models", "kind", "name"]
        assert required == ["gateway-name", "kind"]

    def test_it_does_not_read_options_out_of_the_summary_prose(self):
        """`--custom` is mentioned above the arguments, not declared. A parser
        taking any line starting with `--` reads it, and `foundry.` with it."""
        options, _ = export.parse_options(self.HELP)
        assert "custom" not in options
        assert "foundry." not in options

    def test_global_arguments_are_left_out(self):
        """They belong to azure-cli-core and move on its schedule, so a snapshot
        carrying them churns on an upgrade that changed nothing here."""
        options, _ = export.parse_options(self.HELP)
        assert "debug" not in options and "output" not in options

    def test_a_wrapped_description_does_not_become_an_option(self):
        options, _ = export.parse_options(self.HELP)
        assert "Accepts" not in options and "resource" not in options

    @pytest.mark.parametrize("line,expected", [
        ("    --url                        : Absolute URL.", ["url"]),
        ("    --blocked --block-list       : Tool names.", ["blocked", "block-list"]),
        ("    --name --tool-server-name -n [Required] : Name.", ["name", "tool-server-name"]),
    ])
    def test_every_spelling_on_a_declaration_line_is_recorded(self, line, expected):
        options, _ = export.parse_options(f"Arguments\n{line}\n")
        assert options == sorted(expected)
