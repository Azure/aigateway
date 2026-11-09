import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from jsonschema import Draft7Validator

from author import documents
from grade import ROOT, behavior_expected, cases, evaluate, plan_matches
from verify_planning import verify, verify_result, verify_preflight


def answer(case):
    return {"scenario": case["id"], **behavior_expected(case),
            "commands": list(case.get("required_commands", [])),
            "pendingCommands": [], "executed": False}


class Planning(unittest.TestCase):
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
            self.assertNotIn("files", task["inputs"])
            prompt = task["inputs"]["prompt"]
            self.assertIn("Synthetic evidence:", prompt)
            self.assertNotIn("gateIdentifiers", prompt)
            self.assertNotIn("required_commands", prompt)
            self.assertNotIn("grade.py", prompt)

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
