import copy
import hashlib
import json
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError as SchemaError

from author import documents, value_shape
from grade import ROOT, cases, check, command_matches, normalize_command
from oracles import compare_budget, discovery_sequence, valid_response


def validate(document, schema):
    Draft7Validator(schema).validate(document)


def golden(case):
    return {
        "scenario": case["id"], **copy.deepcopy(case["expected"]),
        "commands": list(case.get("required_commands", [])),
        "executed": False, "limitations": ["final-output-not-execution-proof"],
    }


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.cases = cases()
        self.schemas = {name: json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text())
                        for name in ["eval", "task"]}

    def test_pinned_schema_digests(self):
        manifest = json.loads((ROOT / "sources.json").read_text())
        self.assertEqual(manifest["wazaTag"], "v0.40.1")
        self.assertEqual(manifest["wazaTagObjectType"], "commit")
        self.assertEqual(manifest["wazaTagRefSha"], "e0c251df896bee4e0f9b38a693a6105bf7eadd19")
        license_info = manifest["license"]
        self.assertEqual(hashlib.sha256((ROOT / license_info["path"]).read_bytes()).hexdigest(),
                         license_info["sha256"])
        for item in manifest["schemas"]:
            with self.subTest(path=item["path"]):
                self.assertEqual(hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest(),
                                 item["sha256"])
                self.assertIn("/v0.40.1/schemas/", item["source"])

    def test_materialized_documents_match_authoring_source(self):
        docs = documents()
        paths = set(ROOT.glob("tasks/*.yaml"))
        self.assertEqual(paths, {ROOT / name for name in docs if name.startswith("tasks/")})
        for name, expected in docs.items():
            with self.subTest(path=name):
                self.assertEqual(yaml.safe_load((ROOT / name).read_text()), expected)

    def test_smoke_and_quality_documents_follow_pinned_schemas(self):
        for mode, model in [("smoke", "offline-mock"), ("quality", "operator-selected-model")]:
            docs = documents(mode, model)
            for name, document in docs.items():
                if name.startswith("fixtures/"):
                    continue
                with self.subTest(mode=mode, path=name):
                    validate(document, self.schemas["eval" if name == "eval.yaml" else "task"])
            config = docs["eval.yaml"]["config"]
            self.assertTrue(config["parallel"])
            self.assertEqual(config["workers"], 2)
            self.assertEqual(config["max_attempts"], 1)
            self.assertEqual(set(config["required_skills"]), (
                {"aigateway-planning"} if mode == "quality" else {
                    "manage-ai-gateway", "use-ai-gateway", "migrate-ai-gateway", "feedback-ai-gateway"}))
            self.assertEqual(config["executor"], "mock" if mode == "smoke" else "copilot-sdk")
            spec_dir = ROOT if mode == "smoke" else ROOT / "authorized-quality"
            self.assertEqual(
                {str((spec_dir / p).resolve()) for p in config["skill_directories"]},
                {str(ROOT.resolve())} if mode == "quality" else
                {str((ROOT.parent.parent / "skills" / skill).resolve())
                 for skill in config["required_skills"]},
            )

    def test_schema_rejects_common_waza_syntax_errors(self):
        original = documents()["eval.yaml"]
        for field, value in [("schemaVersion", "1.4"), ("schemaVersion", "2.1")]:
            bad = copy.deepcopy(original)
            bad[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(SchemaError):
                validate(bad, self.schemas["eval"])
        for change in [
            lambda d: d.update(executor="mock"),
            lambda d: d["config"].update(executor="offline"),
            lambda d: d["config"].update(workers=-1),
            lambda d: d["config"].pop("model"),
            lambda d: d["metrics"][0].update(threshold=1.1),
            lambda d: d.update(tasks=[]),
        ]:
            bad = copy.deepcopy(original)
            change(bad)
            with self.assertRaises(SchemaError):
                validate(bad, self.schemas["eval"])
        task = next(v for k, v in documents().items() if k.startswith("tasks/"))
        for change in [
            lambda d: d["inputs"].update(prompt_file="both.txt"),
            lambda d: d["graders"][0]["config"].update(script="invalid.py"),
            lambda d: d["graders"][0]["config"].pop("command"),
        ]:
            bad = copy.deepcopy(task)
            change(bad)
            with self.assertRaises(SchemaError):
                validate(bad, self.schemas["task"])

    def test_pinned_schemas_are_valid_draft_seven(self):
        def check_local_refs(node):
            if isinstance(node, dict):
                if "$ref" in node:
                    self.assertTrue(node["$ref"].startswith("#/"))
                for child in node.values():
                    check_local_refs(child)
            elif isinstance(node, list):
                for child in node:
                    check_local_refs(child)
        for schema in self.schemas.values():
            Draft7Validator.check_schema(schema)
            check_local_refs(schema)

    def test_scenario_inventory_and_input_no_oracle(self):
        self.assertEqual(len({c["id"] for c in self.cases}), len(self.cases))
        self.assertEqual(len(self.cases), 18)
        self.assertEqual({c["category"] for c in self.cases},
                         {"management", "discovery", "integration", "negative"})
        for case in self.cases:
            task = documents()[f"tasks/{case['id']}.yaml"]
            resource = task["inputs"]["files"][0]
            self.assertEqual(resource["path"], "evidence.json")
            self.assertEqual(json.loads(resource["content"]), case["evidence"])
            self.assertNotIn("expected", json.loads(resource["content"]))
            self.assertNotIn("applicable gate names:", task["inputs"]["prompt"])
            self.assertNotIn("commands", json.loads(resource["content"]))
            self.assertEqual(task["inputs"]["files"][1], {"path": "output-contract.json"})
            self.assertNotIn("responder", task["inputs"])
            self.assertNotIn("environment", task["inputs"])
            self.assertTrue(case["expected"]["gates"])

    def test_synthetic_positive_and_every_field_negative(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                answer = golden(case)
                self.assertIn("no claim", check(case, json.dumps(answer)))
                for key in ["scenario", "decision", "selected", "observations", "gates",
                            "commands", "executed", "limitations"]:
                    bad = copy.deepcopy(answer)
                    del bad[key]
                    with self.subTest(missing=key), self.assertRaises(ValueError):
                        check(case, json.dumps(bad))
                for key, value in case["expected"]["observations"].items():
                    bad = copy.deepcopy(answer)
                    bad["observations"][key] = "invented"
                    with self.subTest(observation=key), self.assertRaises(ValueError):
                        check(case, json.dumps(bad))
                for gate in case["expected"]["gates"]:
                    bad = copy.deepcopy(answer)
                    bad["gates"].remove(gate)
                    with self.subTest(gate=gate), self.assertRaises(ValueError):
                        check(case, json.dumps(bad))
                bad = copy.deepcopy(answer)
                bad["executed"] = True
                with self.assertRaises(ValueError):
                    check(case, json.dumps(bad))

    def test_forbidden_actions_and_synthetic_secret_fail(self):
        for case in self.cases:
            for forbidden in case.get("forbidden_commands", []):
                answer = golden(case)
                answer["commands"] = [*answer["commands"], forbidden]
                with self.subTest(case=case["id"], forbidden=forbidden), self.assertRaises(ValueError):
                    check(case, json.dumps(answer))
            for secret in case.get("forbidden_output", []):
                answer = golden(case)
                answer["extra"] = secret
                with self.assertRaises(ValueError):
                    check(case, json.dumps(answer))
                escaped = json.dumps(answer).replace(secret, "".join(f"\\u{ord(c):04x}" for c in secret))
                self.assertNotIn(secret, escaped)
                with self.assertRaises(ValueError):
                    check(case, escaped)

    def test_explicit_subscription_and_sync_dry_run_required(self):
        for case in self.cases:
            for command in case.get("required_commands", []):
                answer = golden(case)
                answer["commands"] = [c.replace("--subscription sub-eval", "") for c in answer["commands"]]
                with self.subTest(case=case["id"]), self.assertRaises(ValueError):
                    check(case, json.dumps(answer))
        case = next(c for c in self.cases if c["id"] == "stale-sync-destructive-approval")
        answer = golden(case)
        answer["commands"] = [answer["commands"][0].replace(" --dry-run", "")]
        with self.assertRaises(ValueError):
            check(case, json.dumps(answer))

    def test_extra_and_duplicate_commands_fail_closed(self):
        for case in self.cases:
            answer = golden(case)
            answer["commands"] = [*answer["commands"], "echo unreviewed-command"]
            with self.subTest(case=case["id"]), self.assertRaises(ValueError):
                check(case, json.dumps(answer))
            for command in case.get("required_commands", []):
                answer = golden(case)
                answer["commands"] = [*answer["commands"], command]
                with self.assertRaises(ValueError):
                    check(case, json.dumps(answer))

    def test_echo_passes_smoke_only(self):
        for case in self.cases:
            echo = f"Mock response for: SCENARIO_ID={case['id']}\nAnalyzed 2 file(s):\n - evidence.json\n - output-contract.json"
            self.assertIn("not an agent-quality", check(case, echo, "smoke"))
            with self.assertRaises(ValueError):
                check(case, echo, "quality")
            with self.assertRaises(ValueError):
                check(case, json.dumps(golden(case)), "smoke")

    def test_program_grader_stdin_protocol(self):
        case = self.cases[0]
        command = [sys.executable, str(ROOT / "grade.py"), "--scenario", case["id"], "--mode", "quality"]
        good = subprocess.run(command, input=json.dumps(golden(case)), text=True,
                              capture_output=True, check=False)
        self.assertEqual(good.returncode, 0, good.stderr)
        bad = subprocess.run(command, input="not-json", text=True, capture_output=True, check=False)
        self.assertNotEqual(bad.returncode, 0)

    def test_quality_preparation_requires_explicit_authorization_and_model(self):
        for args in [[], ["--model", "operator-selected"], ["--authorized"]]:
            result = subprocess.run([sys.executable, str(ROOT / "author.py"), "--quality", *args],
                                    text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)

    def test_advertised_alias_contract_matches_fixture_expectations(self):
        case = next(c for c in self.cases if c["id"] == "exact-alias-endpoint-contract")
        properties = case["evidence"]["alias"]["properties"]
        self.assertEqual(properties["aliasName"], case["expected"]["selected"]["callable"])
        path = properties["supportedEndpoints"][0]
        self.assertTrue(path.startswith("/openai/"))
        self.assertEqual(case["expected"]["observations"]["url"],
                         case["evidence"]["origin"] + "/default/models" + path)
        self.assertNotEqual(properties["aliasName"], case["evidence"]["alias"]["name"])

    def test_response_shape_fixture_oracles(self):
        case = next(c for c in self.cases if c["id"] == "bounded-response-shapes")
        for protocol, payload in case["evidence"]["shapes"].items():
            with self.subTest(protocol=protocol):
                self.assertTrue(valid_response(protocol, payload))
                for bad in case["evidence"]["invalidShapes"]:
                    self.assertFalse(valid_response(protocol, bad))
                for bad in [None, [], {}, {"error": {}}, {"choices": "not-a-list"},
                            {"content": [{"type": "text", "text": ""}]}]:
                    self.assertFalse(valid_response(protocol, bad))
        for bad in [True, float("nan"), float("inf"), "0.1"]:
            self.assertFalse(valid_response("embeddings", {"data": [{"embedding": [bad]}]}))

    def test_mcp_fixture_requires_handshake_and_cursor_bounds(self):
        case = next(c for c in self.cases if c["id"] == "mcp-discovery-not-invocation")
        methods = case["expected"]["observations"]["protocolSequence"]
        self.assertTrue(discovery_sequence(methods, ["page-2"], 3))
        self.assertFalse(discovery_sequence(methods, case["evidence"]["cursors"], 3))
        self.assertFalse(discovery_sequence(methods, ["p2", "p3", "p4", "p5"], 3))
        self.assertFalse(discovery_sequence(["tools/list"], [], 3))
        self.assertFalse(discovery_sequence([*methods, "tools/call"], [], 3))

    def test_relative_budgets_need_observed_paired_baseline(self):
        # Synthetic samples exercise formulas, not measured performance.
        baseline = {"scenario": "runtime-only-known-endpoint", "evidence": "observed",
                    "contextFingerprint": "same-input-and-scope", "toolCalls": 1, "medianSeconds": 20}
        candidate = {**baseline, "toolCalls": 3, "medianSeconds": 60}
        result = compare_budget(baseline["scenario"], baseline, candidate)
        self.assertEqual(result, {"status": "pass", "toolLimit": 3, "medianSecondsLimit": 60})
        self.assertEqual(compare_budget(baseline["scenario"], None, candidate)["status"], "unscored")
        self.assertEqual(compare_budget("different-scenario", baseline, candidate)["status"], "unscored")
        for key, value in [("evidence", "self-reported"), ("contextFingerprint", "different"),
                           ("contextFingerprint", "")]:
            self.assertEqual(compare_budget(baseline["scenario"], baseline, {**candidate, key: value})["status"],
                             "unscored")
        for key, value in [("toolCalls", 4), ("medianSeconds", 61)]:
            self.assertEqual(compare_budget(baseline["scenario"], baseline, {**candidate, key: value})["status"],
                             "fail")

    def test_approved_foundry_scope_has_separate_side_effect_approvals(self):
        case = next(c for c in self.cases if c["id"] == "approved-foundry-onboarding-scope")
        approvals = case["evidence"]["separateApprovals"]
        expected = case["expected"]["observations"]
        self.assertTrue(approvals["importAllCurrentDeployments"])
        self.assertTrue(approvals["attachGatewaySystemIdentity"])
        self.assertEqual(approvals["foundryUserAccountScope"], expected["importRoleScope"])
        self.assertEqual(expected["importRole"], "Foundry User")
        self.assertEqual(expected["importedDeployments"], case["evidence"]["currentDeployments"])
        self.assertFalse(expected["selectedDeploymentApprovalAuthorizesWholeAccount"])
        self.assertIn("--foundry-resource-id " + expected["importRoleScope"], case["required_commands"][0])
        self.assertIn("--deployment deployment-chat", expected["selectedDeploymentCommand"])
        self.assertEqual(expected["selectedDeploymentPath"], "model-create-foundry-resource-id-and-deployment")

    def test_alias_preserves_unrequested_target_policies_and_siblings(self):
        case = next(c for c in self.cases if c["id"] == "alias-routing-sibling-preservation")
        before = case["evidence"]["alias"]["properties"]
        after = case["expected"]["observations"]
        self.assertEqual(before["backendModels"][2], after["intendedBackendModels"][2])
        self.assertEqual(before["policies"], after["retainedAliasPolicies"])
        self.assertFalse(after["siblingAliasesChanged"])
        self.assertFalse(after["providerOrModelsChanged"])
        self.assertEqual(after["intendedBackendModels"][1]["priority"], 0)
        self.assertEqual([m["weight"] for m in after["intendedBackendModels"]], [75, 25, 10])
        bad = golden(case)
        bad["observations"]["intendedBackendModels"].pop()
        with self.assertRaises(ValueError):
            check(case, json.dumps(bad))
        bad = golden(case)
        bad["observations"]["intendedBackendModels"][0]["priority"] = False
        with self.assertRaises(ValueError):
            check(case, json.dumps(bad))
        bad = golden(case)
        bad["commands"] = [bad["commands"][1], bad["commands"][0], bad["commands"][2]]
        with self.assertRaises(ValueError):
            check(case, json.dumps(bad))
        bad = golden(case)
        bad["commands"][1] = bad["commands"][1].replace("weight=75", "weight=99")
        with self.assertRaises(ValueError):
            check(case, json.dumps(bad))

    def test_shared_neutral_vocabulary_makes_contract_identifiers_expressible(self):
        smoke = documents()["fixtures/output-contract.json"]
        quality = documents("quality", "operator-selected-model")["fixtures/output-contract.json"]
        self.assertNotIn("gateIdentifiers", quality)
        self.assertEqual(set(smoke["gateIdentifiers"]),
                         {gate for case in self.cases for gate in case["expected"]["gates"]})
        self.assertNotIn("cases", smoke)
        self.assertNotIn("expected", smoke)
        self.assertNotIn("required_commands", smoke)
        for case in self.cases:
            self.assertNotIn(case["id"], json.dumps(smoke))
            self.assertTrue(set(case["expected"]["selected"]).issubset(smoke["selectedFieldIdentifiers"]))
            self.assertTrue(set(case["expected"]["observations"]).issubset(smoke["observationFieldIdentifiers"]))
            answer = golden(case)
            answer["gates"] = smoke["gateIdentifiers"]
            with self.assertRaises(ValueError):
                check(case, json.dumps(answer))

    def test_typed_shapes_expose_format_without_expected_answers(self):
        sample = {"flag": False, "count": 3, "ids": ["synthetic-id"],
                  "routing": [{"weight": 75}]}
        self.assertEqual(value_shape(sample), {
            "flag": "boolean", "count": "integer", "ids": ["string"],
            "routing": [{"weight": "integer"}]})
        for case in self.cases:
            prompt = documents("quality")[f"tasks/{case['id']}.yaml"]["inputs"]["prompt"]
            from grade import behavior_expected
            shape = json.loads(prompt.split("Fact shape (types only): ")[1].split("\nSelected skill text:")[0])
            self.assertEqual(shape, value_shape(behavior_expected(case)))

    def test_additional_known_gates_do_not_hide_missing_required_gates(self):
        vocabulary = documents()["fixtures/output-contract.json"]["gateIdentifiers"]
        for case in self.cases:
            answer = golden(case)
            extra = next(gate for gate in vocabulary if gate not in answer["gates"])
            answer["gates"].append(extra)
            check(case, json.dumps(answer))
            answer["gates"].remove(case["expected"]["gates"][0])
            with self.assertRaises(ValueError):
                check(case, json.dumps(answer))
            answer = golden(case)
            answer["gates"].append("unreviewed-gate")
            with self.assertRaises(ValueError):
                check(case, json.dumps(answer))

    def test_equivalent_selected_ids_remain_bound_to_exact_resource(self):
        for case in self.cases:
            evidence = case["evidence"]
            root = evidence.get("gatewayId")
            if not root and all(k in evidence for k in ("subscription", "resourceGroup", "gateway")):
                root = (f"/subscriptions/{evidence['subscription']}/resourceGroups/{evidence['resourceGroup']}"
                        f"/providers/Microsoft.ApiManagement/aigateways/{evidence['gateway']}")
            for key in ("gateway", "connection"):
                if not root or key not in case["expected"]["selected"]:
                    continue
                answer = golden(case)
                selected = root if key == "gateway" else root + "/privateEndpointConnections/" + evidence["connection"]
                answer["selected"][key] = selected
                check(case, json.dumps(answer))
                answer["selected"][key] = selected.replace("/subscriptions/sub-eval/", "/subscriptions/foreign/")
                with self.assertRaises(ValueError):
                    check(case, json.dumps(answer))

    def test_phase_alternatives_preserve_execution_and_safety_checks(self):
        for case in self.cases:
            for decision in case.get("accepted_decisions", []):
                answer = golden(case)
                answer["decision"] = decision
                check(case, json.dumps(answer))
                answer["executed"] = True
                with self.assertRaises(ValueError):
                    check(case, json.dumps(answer))
            answer = golden(case)
            answer["decision"] = "unreviewed-phase"
            with self.assertRaises(ValueError):
                check(case, json.dumps(answer))

    def test_equivalent_cli_flag_order_and_shorthand_assignments_pass(self):
        original = "az aigateway model-alias update --subscription sub-eval -g rg-eval --gateway-name gw-eval -n alias --backend-model resource-id=model-a priority=0 weight=75 --backend-model resource-id=model-b priority=0 weight=25"
        reordered = "az aigateway model-alias update --backend-model weight=25 priority=0 resource-id=model-b --name alias --resource-group rg-eval --backend-model priority=0 weight=75 resource-id=model-a --subscription=sub-eval --gateway-name gw-eval"
        self.assertEqual(normalize_command(original), normalize_command(reordered))
        self.assertTrue(command_matches(original, reordered + " --output json"))
        self.assertFalse(command_matches(original, reordered + " --output json --output json"))
        self.assertFalse(command_matches(original, reordered + " --output table"))
        for case in self.cases:
            answer = golden(case)
            commands = []
            for command in answer["commands"]:
                route, options = normalize_command(command)
                words = list(route)
                for flag, values in reversed(options):
                    words.extend([flag, *(reversed(values) if flag == "--backend-model" else values)])
                commands.append(shlex.join(words))
            answer["commands"] = commands
            check(case, json.dumps(answer))
        case = next(c for c in self.cases if c["id"] == "native-task-scoped-discovery")
        answer = golden(case)
        answer["commands"] = ["az aigateway model-alias list --output json --gateway-name gw-eval --resource-group rg-eval --subscription=sub-eval"]
        check(case, json.dumps(answer))
        answer["commands"][0] += " --subscription sub-eval"
        with self.assertRaises(ValueError):
            check(case, json.dumps(answer))
        case = next(c for c in self.cases if c["id"] == "approved-foundry-onboarding-scope")
        answer = golden(case)
        answer["observations"]["selectedDeploymentCommand"] = (
            "az aigateway model create --deployment deployment-chat --foundry-resource-id "
            + case["evidence"]["foundryAccountId"]
            + " --gateway-name gw-eval --resource-group rg-eval --subscription sub-eval")
        check(case, json.dumps(answer))

    def test_wait_reconciliation_accepts_shorter_positive_bound(self):
        case = next(c for c in self.cases if c["id"] == "lro-readiness-not-acceptance")
        self.assertIn("show", case["required_commands"][0])
        answer = golden(case)
        answer["commands"][1] = answer["commands"][1].replace("--timeout 1800", "--timeout 300")
        check(case, json.dumps(answer))
        for timeout in ("0", "10", "1801", "unbounded"):
            answer = golden(case)
            answer["commands"][1] = answer["commands"][1].replace("--timeout 1800", "--timeout " + timeout)
            with self.assertRaises(ValueError):
                check(case, json.dumps(answer))
        answer = golden(case)
        answer["commands"][0], answer["commands"][1] = answer["commands"][1], answer["commands"][0]
        with self.assertRaises(ValueError):
            check(case, json.dumps(answer))

    def test_allowlist_flags_match_recorded_local_b22_help(self):
        provenance = json.loads((ROOT / "native-help.json").read_text())
        self.assertEqual(provenance["extensionVersion"], "1.0.0b22")
        commands = {entry["command"]: entry for entry in provenance["commands"]}
        for case in self.cases:
            planned = [*case.get("required_commands", [])]
            single = case["expected"]["observations"].get("selectedDeploymentCommand")
            if single:
                planned.append(single)
            for command in planned:
                words = shlex.split(command)
                start = next(i for i, word in enumerate(words) if word.startswith("-"))
                route = " ".join(words[:start])
                with self.subTest(case=case["id"], route=route):
                    self.assertIn(route, commands)
                    for word in words[start:]:
                        if word.startswith("-"):
                            self.assertIn(word.split("=", 1)[0], commands[route]["verifiedFixtureOptions"])
        self.assertIn("--deployment", commands["az aigateway model create"]["verifiedFixtureOptions"])
        self.assertIn("--backend-model", commands["az aigateway model-alias update"]["verifiedFixtureOptions"])


if __name__ == "__main__":
    unittest.main()
