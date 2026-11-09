import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from jsonschema import Draft7Validator

from author import documents, task_context
from grade import ROOT, behavior_expected, cases, evaluate, plan_matches, command_matches, normalize_command
from verify_planning import verify, verify_result, verify_preflight


def answer(case):
    return {"scenario": case["id"], **behavior_expected(case),
            "commands": list(case.get("required_commands", [])),
            "pendingCommands": [], "executed": False}


class Planning(unittest.TestCase):
    def test_identity_enum_case_does_not_change_assignment_or_principal_scope(self):
        case = next(c for c in cases() if c["id"] == "selected-rg-bootstrap")
        result = answer(case)
        result["pendingCommands"] = copy.deepcopy(case["pending_commands"])
        approvals = result["pendingCommands"][0]["approvals"]
        gateway = approvals[0]["scope"]
        for spelling in ("SystemAssigned", "systemAssigned", "systemassigned", "SYSTEMASSIGNED"):
            result["observations"]["importIdentity"] = spelling
            approvals[0]["action"] = {"operation": "identity.assign", "identityType": spelling}
            approvals[1]["action"] = {
                "operation": "role.assign", "role": "Foundry User",
                "principal": {"identityType": spelling, "resourceId": gateway}}
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        valid = copy.deepcopy(result)
        for spelling in ("UserAssigned", "SystemAssigned, UserAssigned", "None",
                         "notSystemAssigned", "System Assigned", True, None):
            for target in ("fact", "identity", "principal"):
                result = copy.deepcopy(valid)
                if target == "fact":
                    result["observations"]["importIdentity"] = spelling
                elif target == "identity":
                    result["pendingCommands"][0]["approvals"][0]["action"]["identityType"] = spelling
                else:
                    result["pendingCommands"][0]["approvals"][1]["action"]["principal"]["identityType"] = spelling
                self.assertNotEqual(evaluate(case, json.dumps(result))["status"], "pass",
                                    (target, spelling))

    def test_bootstrap_scope_is_explicit_and_does_not_authorize_bulk_import(self):
        case = next(c for c in cases() if c["id"] == "selected-rg-bootstrap")
        self.assertIn("one selected existing deployment", case["request"])
        self.assertIn("not every deployment", case["request"])
        result = answer(case)
        result["pendingCommands"] = copy.deepcopy(case["pending_commands"])
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        command = result["pendingCommands"][0]["command"]
        result["pendingCommands"][0]["command"] = command.replace(
            "model create", "model-provider create").replace(" --deployment already-exists", "")
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        result["pendingCommands"][0]["command"] = command.replace("already-exists", "other-deployment")
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        bulk = next(c for c in cases() if c["id"] == "approved-foundry-onboarding-scope")
        self.assertIn("separately approved whole-account import", bulk["request"])
        self.assertEqual(evaluate(bulk, json.dumps(answer(bulk)))["status"], "pass")

    def test_all_planning_inputs_preserve_requests_evidence_and_oracle_target_scopes(self):
        variants = yaml.safe_load((ROOT / "holdouts.yaml").read_text())["cases"]
        inventory = cases() + variants
        docs = documents("quality", "gpt-6.1-sol", combined=True)
        self.assertEqual(len(inventory), 21)
        for case in inventory:
            with self.subTest(scenario=case["id"]):
                task = docs[f"tasks/{case['id']}.yaml"]
                self.assertTrue(task["inputs"]["prompt"].startswith(
                    f"SCENARIO_ID={case['id']}\n{case['request']}\n"))
                self.assertEqual(json.loads(task["inputs"]["files"][0]["content"]), case["evidence"])
                self.assertNotIn("pending_commands", task["inputs"]["prompt"])
                self.assertNotIn("supplemental_reads", task["inputs"]["prompt"])
                self.assertNotIn("approval_matches", task["inputs"]["prompt"])
                evidence = case["evidence"]
                gateway_id = evidence.get("gatewayId")
                if not gateway_id and all(k in evidence for k in ("subscription", "resourceGroup", "gateway")):
                    gateway_id = (f"/subscriptions/{evidence['subscription']}/resourceGroups/"
                                  f"{evidence['resourceGroup']}/providers/Microsoft.ApiManagement/"
                                  f"aigateways/{evidence['gateway']}")
                commands = (case.get("required_commands", []) + case.get("supplemental_reads", [])
                            + [row["command"] for row in case.get("pending_commands", [])])
                for command in commands:
                    route, options = normalize_command(command)
                    flags = dict(options)
                    if "--subscription" in flags:
                        self.assertEqual(flags["--subscription"], (evidence["subscription"],))
                    if "--ids" in flags:
                        self.assertEqual(flags["--ids"], (gateway_id,))
                    if "--foundry-resource-id" in flags:
                        self.assertEqual(flags["--foundry-resource-id"], (evidence["foundryAccountId"],))
                    if "--deployment" in flags:
                        self.assertEqual(flags["--deployment"],
                                         (evidence.get("foundryDeployment", evidence.get("deployment")),))
                    if "--resource-group" in flags:
                        selected_rg = evidence.get("resourceGroup")
                        if route[:2] == ("az", "cognitiveservices"):
                            selected_rg = evidence["foundryAccountId"].split("/")[4]
                        self.assertEqual(flags["--resource-group"], (selected_rg,))

    def test_typed_approval_operations_do_not_score_explanatory_sentences(self):
        case = next(c for c in cases() if c["id"] == "selected-rg-bootstrap")
        result = answer(case)
        result["pendingCommands"] = copy.deepcopy(case["pending_commands"])
        approvals = result["pendingCommands"][0]["approvals"]
        gateway = approvals[0]["scope"]
        approvals[0]["action"] = {"operation": "identity.assign", "identityType": "SystemAssigned"}
        approvals[1]["action"] = {
            "operation": "role.assign", "role": "Foundry User",
            "principal": {"identityType": "SystemAssigned", "resourceId": gateway}}
        result["notes"] = ["Account scope, not only the selected deployment.",
                           "This grant covers the entire selected Foundry account."]
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        correct = copy.deepcopy(approvals)
        for index, action in (
            (0, {"operation": "identity.remove", "identityType": "SystemAssigned"}),
            (0, {"operation": "identity.assign", "identityType": "UserAssigned"}),
            (0, {**correct[0]["action"], "approved": True}),
            (1, {**correct[1]["action"], "operation": "role.remove"}),
            (1, {**correct[1]["action"], "operation": "do-not-grant"}),
            (1, {**correct[1]["action"], "role": "Owner"}),
            (1, {**correct[1]["action"], "role": "Foundry User and Contributor"}),
            (1, {**correct[1]["action"], "principal": {
                "identityType": "UserAssigned", "resourceId": gateway}}),
            (1, {**correct[1]["action"], "principal": {
                "identityType": "SystemAssigned", "resourceId": gateway + "-sibling"}}),
        ):
            result["pendingCommands"][0]["approvals"] = copy.deepcopy(correct)
            result["pendingCommands"][0]["approvals"][index]["action"] = action
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail", action)
        result["pendingCommands"][0]["approvals"] = copy.deepcopy(correct)
        result["pendingCommands"][0]["approvals"][1]["scope"] += "/deployments/chat"
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        result["pendingCommands"][0]["approvals"] = copy.deepcopy(correct)
        result["pendingCommands"][0]["approvals"].reverse()
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        result["pendingCommands"][0]["approvals"].pop()
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")

    def test_bootstrap_foundry_prerequisite_reads_keep_selected_scope(self):
        case = next(c for c in cases() if c["id"] == "selected-rg-bootstrap")
        required = case["required_commands"]
        reads = [c for c in case["supplemental_reads"] if "cognitiveservices" in c]
        self.assertEqual(len(reads), 2)
        self.assertTrue(plan_matches(case, reads + required, required))
        for changed in (
                reads[0].replace("sub-eval", "foreign"),
                reads[0].replace("rg-models", "other-rg"),
                reads[0].replace("foundry-eval", "other-account"),
                reads[1].replace("deployment list", "deployment create"),
                reads[1].replace("--subscription sub-eval ", "")):
            self.assertFalse(plan_matches(case, [changed, *required], required))
        self.assertFalse(plan_matches(case, reads, required))
        pending = case["pending_commands"][0]["command"]
        self.assertFalse(plan_matches(case, [*reads, *required, pending], required))

    def test_actual_recorded_launcher_is_fail_closed_and_keeps_both_statuses(self):
        for condition in ("saved-failure", "empty-result", "occupied-result",
                          "changed-source", "missing-identity", "missing-python", "wrong-model"):
            with self.subTest(condition=condition), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                result = "evals/waza/results/fresh.json"
                config = "evals/waza/authorized-combined/eval.yaml"
                (root / result).parent.mkdir(parents=True)
                (root / config).parent.mkdir(parents=True)
                (root / config).write_text(json.dumps({
                    "config": {"model": "gpt-6.1-sol", "trials_per_task": 1},
                }))
                snapshot = root / "snapshot"
                snapshot.mkdir()
                profile = root / "profile"
                profile.mkdir()
                (profile / "settings.json").write_text('{"disableAllHooks":true}')
                source = root / "source.txt"
                source.write_text("frozen")
                identity = root / "evals/waza/results/fresh.identity.json"
                identity.write_text(json.dumps({
                    "result": result, "config": config, "configSnapshot": "snapshot",
                    "model": "gpt-6.1-sol", "trialsPerTask": 1, "sourceCommit": "inert-test",
                    "sourceDigests": {"source.txt": hashlib.sha256(source.read_bytes()).hexdigest()},
                    "originalDigests": {},
                    "profileEvidence": {
                        "hooksDisabled": True, "installedPlugins": 0, "userMcpServers": 0,
                        "managedStartupKeys": 0, "existingAuthentication": True,
                    },
                }))
                binary = root / "bin"
                binary.mkdir()
                uv = binary / "uv"
                uv.write_text("""#!/usr/bin/env bash
set -eu
if [[ "$*" == *"waza run"* ]]; then
  printf 'WAZA_CALLED\\n' >> "$EVENTS"
  printf '{}' > "$RESULT"
  exit 7
fi
if [[ "$*" == *"verify_planning.py"* ]]; then
  if [[ "$*" == *"--result"* ]]; then
    printf 'VERIFIER_CALLED\\n' >> "$EVENTS"
    exit 3
  fi
  exit 0
fi
while test "$1" != python; do shift; done
shift
exec """ + repr(sys.executable) + """ "$@"
""")
                uv.chmod(0o755)
                if condition == "empty-result":
                    result = ""
                elif condition == "occupied-result":
                    (root / result).write_text("original")
                elif condition == "changed-source":
                    source.write_text("changed")
                elif condition == "missing-identity":
                    identity.unlink()
                elif condition == "missing-python":
                    uv.write_text("#!/usr/bin/env bash\nexit 9\n")
                elif condition == "wrong-model":
                    (root / config).write_text('{"config":{"model":"unapproved","trials_per_task":1}}')
                events = root / "events.txt"
                done = subprocess.run(["bash", str(ROOT / "run_planning.sh"), config, result],
                                      cwd=root, env={**os.environ, "PATH": str(binary) + ":" + os.environ["PATH"],
                                                     "PLANNING_HOME": str(profile), "EVENTS": str(events)},
                                      capture_output=True, text=True)
                self.assertNotEqual(done.returncode, 0)
                if condition == "saved-failure":
                    self.assertEqual(events.read_text(), "WAZA_CALLED\nVERIFIER_CALLED\n")
                    status = json.loads((root / "evals/waza/results/fresh.status.json").read_text())
                    self.assertEqual((status["wazaExit"], status["policyExit"]), (7, 3))
                    self.assertEqual(status["changedSource"], [])
                else:
                    self.assertFalse(events.exists(), "Preparation failure launched inert Waza")

    def test_equivalent_fact_formats_preserve_runtime_and_counter_boundaries(self):
        case = next(c for c in cases() if c["id"] == "exact-alias-endpoint-contract")
        result = answer(case)
        result["selected"]["endpoint"] = result["observations"]["url"]
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        for changed in (result["observations"]["url"].replace("gateway.", "provider."),
                        result["observations"]["url"].replace("/default/", "/other/"),
                        result["observations"]["url"].replace("/responses", "/chat/completions")):
            result["selected"]["endpoint"] = changed
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        case = next(c for c in cases() if c["id"] == "token-request-policy-counters")
        result = answer(case)
        result["observations"]["ratePartition"] = "identity/ipAddress"
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        for changed in ("identity", "ipAddress", "two-independent-counters"):
            result["observations"]["ratePartition"] = changed
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")

    def test_pending_approval_language_keeps_role_and_scope_exact(self):
        case = next(c for c in cases() if c["id"] == "selected-rg-bootstrap")
        result = answer(case)
        result["pendingCommands"] = copy.deepcopy(case["pending_commands"])
        approvals = result["pendingCommands"][0]["approvals"]
        approvals[0]["action"] = "Enable the gateway system-assigned managed identity"
        approvals[1]["action"] = "Grant Foundry User to the gateway identity"
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        for changed in ("Do not grant Foundry User to the gateway identity",
                        "Grant Owner to the gateway identity",
                        "Grant Foundry User and Contributor to the gateway identity"):
            approvals[1]["action"] = changed
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        approvals[1]["action"] = "Grant Foundry User to the gateway identity at account scope, not deployment-only scope"
        approvals[1]["scope"] += "/deployments/deployment-chat"
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")

    def test_independent_verification_order_still_requires_create_and_both_reads(self):
        case = next(c for c in cases() if c["id"] == "approved-foundry-onboarding-scope")
        self.assertEqual([command for phase in case["behavior_phases"] for command in phase],
                         case["required_commands"])
        create, models, identity = case["required_commands"]
        self.assertTrue(plan_matches(case, [create, identity, models], case["required_commands"]))
        for commands in ([identity, models, create], [create, identity], [create, models]):
            self.assertFalse(plan_matches(case, commands, case["required_commands"]))
        for read in case["supplemental_reads"]:
            self.assertFalse(plan_matches(case, [
                read.replace("sub-eval", "foreign"), create, models, identity],
                case["required_commands"]))

    def test_colored_json_does_not_accept_table_or_weaken_typed_binding(self):
        expected = "az aigateway show --subscription sub-eval --ids /subscriptions/sub-eval/resourceGroups/rg-eval/providers/Microsoft.ApiManagement/aigateways/gw-eval -o json"
        self.assertTrue(command_matches(expected, expected.replace("-o json", "-o jsonc")))
        self.assertFalse(command_matches(expected, expected.replace("-o json", "-o table")))
        self.assertFalse(command_matches(expected, "az aigateway show --subscription sub-eval -g rg-eval -n gw-eval -o json"))
        self.assertFalse(command_matches(expected, expected + " --subscription foreign"))

    def test_dependency_reads_cannot_replace_or_reorder_alias_mutations(self):
        case = next(c for c in cases() if c["id"] == "alias-routing-sibling-preservation")
        family, before, update, after = case["required_commands"]
        root, sibling, aliases = case["supplemental_reads"]
        for commands in (
                [root, family, before, update, after, sibling],
                [root, aliases, before, family, update, after, aliases],
                [family, before, update, after]):
            self.assertTrue(plan_matches(case, commands, case["required_commands"]))
        for commands in ([root, update, before, after],
                         [root, aliases, before, update, after, aliases],
                         [before, update, family, after],
                         [family, update, before, after],
                         [family, before, after, update],
                         [family, before, update],
                         [family, before, update, after, sibling.replace(" show ", " update ")],
                         [family, before, update, after, sibling.replace("billing-arm-alias", "foreign")]):
            self.assertFalse(plan_matches(case, commands, case["required_commands"]))
        for changed in (
                family.replace("sub-eval", "foreign"),
                family.replace("rg-eval", "foreign-rg"),
                family.replace("gw-eval", "sibling"),
                family.replace("--name gw-eval ", ""),
                family.replace("resource list", "resource delete")):
            self.assertFalse(plan_matches(case, [changed, before, update, after],
                                          case["required_commands"]))
        for changed in (
                aliases.replace("sub-eval", "foreign"),
                aliases.replace("rg-eval", "foreign-rg"),
                aliases.replace("gw-eval", "sibling"),
                aliases.replace("--subscription sub-eval ", ""),
                aliases.replace("model-alias list", "model-alias delete")):
            self.assertFalse(plan_matches(case, [family, before, changed, update, after],
                                          case["required_commands"]))

    def test_composite_counter_representation_does_not_accept_independent_allowances(self):
        case = next(c for c in cases() if c["id"] == "token-request-policy-counters")
        result = answer(case)
        for partition in (
                "identity-and-ip-combination", "identity/ipAddress",
                "identity/ipAddress combination",
                {"dimensions": ["identity", "ipAddress"], "composition": "composite"},
                {"dimensions": ["ipAddress", "identity"], "composition": "composite"}):
            result["observations"]["ratePartition"] = partition
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        for partition in (
                "identity", "ipAddress", "identity/ipAddress independent",
                "not identity/ipAddress combination", "identity/ipAddress combination or pooled",
                {"dimensions": ["identity", "ipAddress"], "composition": "independent"},
                {"dimensions": ["identity", "identity"], "composition": "composite"},
                {"dimensions": ["identity"], "composition": "composite"},
                {"dimensions": ["identity", {"ipAddress": True}], "composition": "composite"},
                {"dimensions": ["identity", None], "composition": "composite"},
                {"dimensions": ["identity", "ipAddress", "subscription"], "composition": "composite"},
                {"dimensions": ["identity", "ipAddress"], "composition": "composite", "bypass": True},
                True, None):
            result["observations"]["ratePartition"] = partition
            self.assertNotEqual(evaluate(case, json.dumps(result))["status"], "pass", partition)

    def test_missing_family_preflight_is_behavior_failure_not_syntax_failure(self):
        case = next(c for c in cases() if c["id"] == "alias-routing-sibling-preservation")
        result = answer(case)
        result["commands"].insert(0, case["supplemental_reads"][-1])
        self.assertEqual(evaluate(case, json.dumps(result), "behavior")["status"], "pass")
        self.assertEqual(evaluate(case, json.dumps(result), "syntax")["status"], "pass")
        result["commands"].remove(case["required_commands"][0])
        self.assertEqual(evaluate(case, json.dumps(result), "behavior")["status"], "fail")
        self.assertEqual(evaluate(case, json.dumps(result), "syntax")["status"], "pass")

    def test_approval_sentence_variants_do_not_accept_negation_or_broader_roles(self):
        case = next(c for c in cases() if c["id"] == "selected-rg-bootstrap")
        result = answer(case)
        result["pendingCommands"] = copy.deepcopy(case["pending_commands"])
        result["observations"]["importIdentity"] = "system-assigned"
        approvals = result["pendingCommands"][0]["approvals"]
        approvals[0]["action"] = "Enable the gateway system-assigned managed identity for Foundry onboarding."
        approvals[1]["action"] = (
            "Grant Foundry User to the gateway system-assigned managed identity "
            "at the entire Foundry account scope, not just the selected deployment.")
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        for field, changed in (
            ("importIdentity", "UserAssigned"),
            ("importIdentity", "SystemAssigned, UserAssigned"),
        ):
            result["observations"][field] = changed
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        result["observations"]["importIdentity"] = "system-assigned"
        for changed in ("Do not enable the gateway system-assigned managed identity.",
                        "Enable the gateway user-assigned managed identity.",
                        "Enable the gateway system-assigned managed identity. Grant Owner too."):
            approvals[0]["action"] = changed
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")

    def test_runtime_metadata_unavailable_is_not_empty_or_runtime_failure(self):
        case = next(c for c in cases() if c["id"] == "runtime-only-known-endpoint")
        result = answer(case)
        result["observations"].update(backendConfiguration="unavailable", policies="unavailable")
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        result["observations"]["policies"] = "empty"
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        case = next(c for c in cases() if c["id"] == "private-endpoint-approval")
        result = answer(case)
        result["observations"]["privateReachability"] = "unavailable"
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")

    def test_combined_selection_keeps_each_independent_input_and_grader(self):
        baseline = documents("quality", "gpt-6.1-sol")
        holdouts = documents("quality", "gpt-6.1-sol", holdouts=True)
        combined = documents("quality", "gpt-6.1-sol", combined=True)
        tasks = {key: value for key, value in combined.items() if key.startswith("tasks/")}
        self.assertEqual(len(tasks), 21)
        for source in (baseline, holdouts):
            for key, value in source.items():
                if key.startswith("tasks/"):
                    self.assertEqual(tasks[key], value)
                    self.assertEqual(len(value["inputs"]["files"]), 1)
                    self.assertNotIn("required_commands", value["inputs"]["prompt"])
        self.assertEqual(combined["eval.yaml"]["config"]["trials_per_task"], 1)
        with self.assertRaises(ValueError):
            documents("quality", "gpt-6.1-sol", holdouts=True, combined=True)

    def test_task_recipes_are_source_context_not_oracle_answers(self):
        docs = documents("quality", "gpt-6.1-sol")
        for case in cases():
            prompt = docs["tasks/" + case["id"] + ".yaml"]["inputs"]["prompt"]
            for reference in case.get("context_sections", []):
                filename, heading = reference.split("#", 1)
                self.assertIn(reference, prompt)
                text = (ROOT.parents[1] / "skills" / case["skill"] / filename).read_text()
                self.assertIn(" " + heading + "\n", text)
            self.assertNotIn("required_commands", prompt)
            self.assertNotIn("behavior_commands", prompt)
            self.assertNotIn("pending_commands", prompt)
            if case["id"] == "runtime-only-known-endpoint":
                self.assertNotIn("Recorded local CLI help", prompt)
        bad = copy.deepcopy(cases()[0])
        for reference in ("../../evals/waza/grade.py#Anything",
                          "references/gateway-lifecycle.md#Missing heading"):
            bad["context_sections"] = [reference]
            with self.assertRaises(ValueError):
                task_context(bad)

    def test_local_probes_never_replace_plans_or_expand_runtime_scope(self):
        case = next(c for c in cases() if c["id"] == "native-task-scoped-discovery")
        probes = ["az aigateway version", "az aigateway model-alias list --help"]
        self.assertTrue(plan_matches(case, probes + case["required_commands"], case["required_commands"]))
        self.assertFalse(plan_matches(case, probes, case["required_commands"]))
        self.assertFalse(plan_matches(case, ["az aigateway fake-command --help"] +
                                      case["required_commands"], case["required_commands"]))
        runtime = next(c for c in cases() if c["id"] == "runtime-only-known-endpoint")
        self.assertFalse(plan_matches(runtime, probes, []))
        scoped = "az aigateway show --subscription sub-eval -g rg-eval -n gw-eval -o json"
        exact = ("az aigateway show --subscription sub-eval --ids "
                 "/subscriptions/sub-eval/resourceGroups/rg-eval/providers/"
                 "Microsoft.ApiManagement/aigateways/gw-eval -o json")
        self.assertTrue(command_matches(scoped, exact))
        self.assertFalse(command_matches(exact, scoped))
        self.assertFalse(command_matches(scoped, exact.replace("/aigateways/", "/service/")))
        self.assertFalse(command_matches(scoped, exact.replace("/rg-eval/", "/foreign/")))

    def test_lro_bounds_and_readback_not_redundant_initial_read(self):
        case = next(c for c in cases() if c["id"] == "lro-readiness-not-acceptance")
        required = case["behavior_commands"]
        self.assertTrue(plan_matches(case, required, required))
        shorter = [required[0].replace("--timeout 1800", "--timeout 60").replace(
            "--interval 20", "--interval 5"), required[1]]
        self.assertTrue(plan_matches(case, shorter, required))
        self.assertFalse(plan_matches(case, shorter[:1], required))
        for changed in (required[0].replace("--timeout 1800", "--timeout 0"),
                        required[0].replace("--interval 20", "--interval 0"),
                        required[0].replace("--timeout 1800", "--timeout 3600"),
                        required[0].replace("aigateways/gw-eval", "service/gw-eval")):
            self.assertFalse(plan_matches(case, [changed, required[1]], required))

    def test_preflight_accepts_only_known_offline_warnings(self):
        docs = documents("quality", "gpt-6.1-sol")
        ids = [task["id"] for name, task in docs.items() if name.startswith("tasks/")]
        path = ROOT / "authorized-quality" / "eval.yaml"
        report = {"kind": "waza.preflight", "schemaVersion": "1.0",
                  "source": str(path), "executor": "copilot-sdk", "complete": True,
                  "tasks": [{"id": identifier, "enabled": True} for identifier in ids],
                  "diagnostics": [{"code": "runtime.availability", "state": "unresolved",
                                   "severity": "warning"}], "dependencies": []}
        for identifier in ids:
            for code in ("boundary.requested_policy", "boundary.post_run",
                         "grader.subprocess", "grader.subprocess"):
                report["diagnostics"].append({"code": code, "state": "unresolved",
                                              "severity": "warning", "task_id": identifier})
            report["dependencies"].append({
                "kind": "boundary", "mode": "requested-deny-all", "state": "unresolved",
                "name": str(ROOT / "planning.agent.md"), "task_id": identifier})
            for name in ("behavior", "syntax"):
                report["dependencies"].append({
                    "kind": "grader", "mode": "subprocess", "state": "unresolved",
                    "name": name, "task_id": identifier})
        with patch("verify_planning.Path.read_text", return_value=yaml.safe_dump(docs["eval.yaml"])), \
                patch("verify_planning.documents", return_value=docs):
            self.assertFalse(verify_preflight(report, path)["runtimePolicyVerified"])
            for code, state in (("eval.schema", "invalid"), ("hooks.execution", "unresolved"),
                                ("runtime.executor", "unsupported"),
                                ("boundary.requested_policy", "invalid")):
                bad = copy.deepcopy(report)
                bad["diagnostics"].append({"code": code, "state": state, "severity": "warning"})
                with self.assertRaises(ValueError):
                    verify_preflight(bad, path)
            for key, value in (("complete", False), ("tasks", []), ("dependencies", []),
                               ("source", "foreign/eval.yaml")):
                bad = {**report, key: value}
                with self.assertRaises(ValueError):
                    verify_preflight(bad, path)
            bad = copy.deepcopy(report)
            bad["dependencies"][0]["mode"] = "requested-allowlist"
            with self.assertRaises(ValueError):
                verify_preflight(bad, path)
            bad = copy.deepcopy(report)
            bad["diagnostics"].pop()
            with self.assertRaises(ValueError):
                verify_preflight(bad, path)

    def test_semantics_do_not_require_labels_or_markers(self):
        for case in cases():
            result = answer(case)
            self.assertNotIn("gates", result)
            self.assertNotIn("decision", result)
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass", case["id"])
            result["executed"] = True
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")

    def test_pending_foundry_work_cannot_enter_approved_plan(self):
        case = cases()[0]
        result = answer(case)
        result["pendingCommands"] = copy.deepcopy(case["pending_commands"])
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        result["commands"] += [result["pendingCommands"][0]["command"]]
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        result = answer(case)
        result["pendingCommands"] = copy.deepcopy(case["pending_commands"])
        result["pendingCommands"][0]["approvals"].pop()
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        result["pendingCommands"][0]["approvals"][0]["scope"] = "/subscriptions/foreign"
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        result = answer(case)
        result["pendingCommands"] = copy.deepcopy(case["pending_commands"])
        result["pendingCommands"][0]["approvals"] = [
            {"action": "Foundry User", "scope": case["pending_commands"][0]["approvals"][1]["scope"]},
            {"action": "SystemAssigned", "scope": case["pending_commands"][0]["approvals"][0]["scope"]}]
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
        result["pendingCommands"][0]["command"] = "az aigateway model create '"
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")

    def test_narrative_is_unscored_not_coerced_to_boolean(self):
        case = next(c for c in cases() if c["id"] == "policy-denial-no-provider-bypass")
        result = answer(case)
        result["observations"]["fallbackPlanned"] = "No fallback is planned."
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "unscored")
        self.assertEqual(evaluate(case, json.dumps(result), "syntax")["status"], "unscored")
        result["observations"]["fallbackPlanned"] = True
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        self.assertEqual(evaluate(case, json.dumps(result), "syntax")["status"], "pass")

    def test_structured_names_are_lossless_not_loose_text_matching(self):
        for scenario, section, field, value in [
            ("mcp-discovery-not-invocation", "selected", "tools", [{"name": "support_search"}]),
            ("apim-assess-not-execute", "observations", "residuals",
             [{"behavior": "unsupported-custom-policy"}]),
        ]:
            case = next(c for c in cases() if c["id"] == scenario)
            result = answer(case)
            result[section][field] = value
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
            result[section][field].append("unselected")
            self.assertNotEqual(evaluate(case, json.dumps(result))["status"], "pass")

    def test_scoped_supplemental_reads_never_approve_extra_mutations(self):
        case = next(c for c in cases() if c["id"] == "native-task-scoped-discovery")
        required = case["required_commands"]
        self.assertTrue(plan_matches(case, case["supplemental_reads"] + required, required))
        self.assertFalse(plan_matches(case, required + ["az aigateway delete --ids foreign"], required))
        self.assertFalse(plan_matches(case, [
            case["supplemental_reads"][0].replace("sub-eval", "foreign"), *required], required))

    def test_runtime_contract_and_sync_preview_remain_strict(self):
        case = next(c for c in cases() if c["id"] == "runtime-only-known-endpoint")
        for key, value in [("endpoint", "https://provider.example.invalid"),
                           ("authHeader", "Api-Key"), ("maximumAttempts", 2)]:
            result = answer(case)
            result["selected"][key] = value
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        case = next(c for c in cases() if c["id"] == "alias-routing-sibling-preservation")
        result = answer(case)
        result["observations"]["intendedBackendModels"][0]["priority"] = False
        self.assertNotEqual(evaluate(case, json.dumps(result))["status"], "pass")
        self.assertNotEqual(evaluate(case, json.dumps(result), "syntax")["status"], "pass")
        result = answer(case)
        result["commands"] = ["az aigateway show --ids foreign"]
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")
        case = next(c for c in cases() if c["id"] == "stale-sync-destructive-approval")
        result = answer(case)
        result["commands"] = [result["commands"][0].replace(" --dry-run", " --yes")]
        self.assertEqual(evaluate(case, json.dumps(result))["status"], "fail")

    def test_generated_policy_is_deny_all_and_contains_no_grader_input(self):
        policy = yaml.safe_load((ROOT / "planning.agent.md").read_text().split("---")[1])
        self.assertEqual(policy["tools"], [])
        docs = documents("quality", "gpt-6.1-sol")
        spec = docs["eval.yaml"]
        self.assertEqual(spec["skill"], policy["name"])
        self.assertEqual(spec["config"]["skill_directories"], [".."])
        self.assertTrue(spec["config"]["inject_skill_body"])
        self.assertNotIn("mcp_servers", spec["config"])
        for name, task in docs.items():
            if not name.startswith("tasks/"):
                continue
            case = next(c for c in cases() if c["id"] == task["id"])
            self.assertEqual(task["inputs"]["files"], [{
                "path": "evidence.json",
                "content": json.dumps(case["evidence"], indent=2) + "\n"}])
            prompt = task["inputs"]["prompt"]
            self.assertIn("Synthetic evidence:", prompt)
            self.assertNotIn("gateIdentifiers", prompt)
            self.assertNotIn("required_commands", prompt)
            self.assertNotIn("grade.py", prompt)

    def test_pinned_empty_sandbox_guard_and_legitimate_resource_loading(self):
        # runner.go:1846-1857 at the commit recorded in sources.json.
        def rejected(prompt, resources):
            return not resources and ("./" in prompt or "../" in prompt)

        self.assertTrue(rejected("Read ./input.md", []))
        self.assertTrue(rejected("Read ../input.md", []))
        self.assertFalse(rejected("All evidence is inline.", []))
        self.assertFalse(rejected("Read ./input.md", [{"path": "input.md", "content": "input"}]))
        matched = 0
        for holdouts in (False, True):
            scenario_cases = (yaml.safe_load((ROOT / "holdouts.yaml").read_text())["cases"]
                              if holdouts else cases())
            docs = documents("quality", "gpt-6.1-sol", holdouts=holdouts)
            for name, task in docs.items():
                if not name.startswith("tasks/"):
                    continue
                files = task["inputs"]["files"]
                case = next(c for c in scenario_cases if c["id"] == task["id"])
                self.assertEqual(len(files), 1)
                self.assertEqual(files[0]["path"], "evidence.json")
                self.assertEqual(json.loads(files[0]["content"]), case["evidence"])
                # runner.go:2092-2098 loads nonempty inline content as ResourceFile.
                loaded = [f for f in files if f.get("content")]
                self.assertEqual(len(loaded), 1)
                self.assertFalse(rejected(task["inputs"]["prompt"], loaded), task["id"])
                matched += rejected(task["inputs"]["prompt"], [])
                with tempfile.TemporaryDirectory() as sandbox:
                    path = Path(sandbox) / files[0]["path"]
                    path.write_text(files[0]["content"])
                    self.assertEqual(json.loads(path.read_text()), case["evidence"])
        # The old generated input failed for 17 baseline tasks; removal must regress.
        self.assertGreaterEqual(matched, 17)

    def test_documented_saved_result_verification_preserves_failure_statuses(self):
        text = (ROOT / "README.md").read_text()
        block = next(block for block in text.split("```bash\n")[1:]
                     if 'RESULT="evals/waza/results/quality-planning-' in block).split("```")[0]
        # Substitute inert commands before execution; never launch uv/Waza/model.
        block, run_count = re.subn(
            r'if (?:COPILOT_HOME|TMPDIR)=.*?--output "\$RESULT"; then',
            'if (printf "{}" > "$RESULT"; exit 7); then', block, flags=re.S)
        block, verifier_count = re.subn(
            r'if uv run.*?--result "\$RESULT"; then',
            'if (printf "VERIFIER_EXECUTED\\\\n"; exit 3); then', block, flags=re.S)
        self.assertEqual((run_count, verifier_count), (1, 1))
        self.assertNotIn("waza run", block)
        self.assertNotIn("uv run", block)
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(["bash", "-c", block], cwd=directory,
                                       env={**os.environ, "PLANNING_HOME": directory},
                                       capture_output=True, text=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("VERIFIER_EXECUTED", completed.stdout)
            self.assertIn("Waza exit: 7", completed.stdout)
            self.assertIn("Policy-check exit: 3", completed.stdout)

    def test_preparation_failure_cannot_launch_documented_paid_command(self):
        text = (ROOT / "README.md").read_text()
        block = next(block for block in text.split("```bash\n")[1:]
                     if 'RESULT="evals/waza/results/quality-planning-' in block).split("```")[0]
        block, count = re.subn(
            r'if (?:COPILOT_HOME|TMPDIR)=.*?--output "\$RESULT"; then',
            'if (printf "UNEXPECTED_LAUNCH\\\\n"; exit 7); then', block, flags=re.S)
        block, verifier_count = re.subn(
            r'if uv run.*?--result "\$RESULT"; then',
            'if false; then', block, flags=re.S)
        self.assertEqual((count, verifier_count), (1, 1))
        self.assertNotIn("waza run", block)
        self.assertNotIn("uv run", block)
        with tempfile.TemporaryDirectory() as directory:
            for prefix in ('unset PLANNING_HOME\n',
                           'PLANNING_HOME="$PWD"\ndate() { return 9; }\n'):
                completed = subprocess.run(["bash", "-c", prefix + block], cwd=directory,
                                           capture_output=True, text=True)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn("UNEXPECTED_LAUNCH", completed.stdout)

    def test_stale_config_and_missing_runtime_evidence_fail_closed(self):
        docs = documents("quality", "gpt-6.1-sol")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "evals" / "waza"
            destination = root / "authorized-quality"
            root.mkdir(parents=True)
            (root / "planning.agent.md").write_text((ROOT / "planning.agent.md").read_text())
            for name, doc in docs.items():
                path = destination / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(doc) if path.suffix == ".json" else yaml.safe_dump(doc))
            with patch("verify_planning.ROOT", root):
                self.assertEqual(verify(destination / "eval.yaml")["configuredToolPolicy"], "deny_all")
                task = destination / next(name for name in docs if name.startswith("tasks/"))
                task.write_text(task.read_text().replace("Fact shape", "Stale format"))
                with self.assertRaisesRegex(ValueError, "stale"):
                    verify(destination / "eval.yaml")
            result = root / "synthetic-result.json"
            def policy_report(digest, events=None):
                result.write_text(json.dumps({"tasks": [{"runs": [{
                    "session_digest": digest, "tool_events": events or []}]}]}))
                return verify_result(result)
            self.assertFalse(policy_report({})["policyEvidencePassed"])
            digest = {"tool_policy_mode": "deny_all", "tool_call_count": 0}
            self.assertTrue(policy_report(digest)["policyEvidencePassed"])
            self.assertFalse(policy_report(
                {**digest, "tool_policy_denials": [{"tool": "synthetic"}]})["policyEvidencePassed"])
            self.assertFalse(policy_report(digest, [{"synthetic": True}])["policyEvidencePassed"])
            self.assertFalse(policy_report({**digest, "tool_call_count": 1})["policyEvidencePassed"])

    def test_holdouts_are_separate_new_inputs_and_schema_valid(self):
        holdouts = yaml.safe_load((ROOT / "holdouts.yaml").read_text())["cases"]
        self.assertEqual(len(holdouts), 3)
        self.assertFalse({c["id"] for c in holdouts} & {c["id"] for c in cases()})
        docs = documents("quality", "gpt-6.1-sol", holdouts=True)
        schemas = {name: json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text())
                   for name in ("task", "eval")}
        for path, document in docs.items():
            if path.startswith("fixtures/"):
                continue
            Draft7Validator(schemas["eval" if path == "eval.yaml" else "task"]).validate(document)
        for case in holdouts:
            result = answer(case)
            if case.get("pending_required"):
                result["pendingCommands"] = copy.deepcopy(case["pending_commands"])
            self.assertEqual(evaluate(case, json.dumps(result))["status"], "pass")
            bad = answer(case)
            bad["commands"] = ["az role assignment create --scope foreign"]
            self.assertEqual(evaluate(case, json.dumps(bad))["status"], "fail")


if __name__ == "__main__":
    unittest.main()
