import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import smoke
from core import MigrationError, digest, read_json, validate_schema


def asset(kind, mode, bound, max_tokens=None):
    limits = {"maxRequests": bound}
    if max_tokens is not None:
        limits["maxTokens"] = max_tokens
    request = ({"mode": "minimal-inference", "api": "v1/chat/completions"}
               if kind == "alias" else
               {"mode": "mcp-initialize-tools-list", "protocolVersion": "2025-06-18"})
    if mode == "custom":
        request["mode"] = mode
    return {
        "id": "test-asset", "kind": kind, "action": "create",
        "smokeTests": [{
            "required": True, "request": request,
            "credentialInputs": [], "bounds": limits,
        }],
    }


class SmokeTests(unittest.TestCase):
    def test_inventory_requires_one_standard_bounded_test_per_asset(self):
        self.assertEqual(
            smoke._approved_checks({"assets": [asset("alias", "minimum", 1, 1)]})[0]["id"],
            "test-asset",
        )
        self.assertEqual(
            smoke._approved_checks(
                {"assets": [asset("mcp", "minimum", 3)]})[0]["kind"],
            "mcp",
        )
        for candidate in (
            asset("alias", "minimum", 2, 1),
            asset("alias", "minimum", 1, 2),
            asset("alias", "custom", 1, 1),
            {**asset("mcp", "minimum", 3), "smokeTests": []},
        ):
            with self.subTest(candidate=candidate), self.assertRaises(MigrationError):
                smoke._approved_checks({"assets": [candidate]})

    def test_alias_uses_advertised_endpoint_and_one_token_request(self):
        alias = {"name": "alias-resource", "properties": {"aliasName": "Callable.Name"}}
        endpoints = [
            {"api": "v1/responses",
             "url": "https://gateway.example/default/models/openai/v1/responses"},
            {"api": "v1/chat/completions",
             "url": "https://gateway.example/default/models/openai/v1/chat/completions"},
        ]
        url, headers, body, route = smoke._model_request(
            alias, endpoints, "gateway.example", "v1/chat/completions")
        self.assertEqual(route, "v1/chat/completions")
        self.assertEqual(url, endpoints[1]["url"])
        self.assertEqual(body["model"], "Callable.Name")
        self.assertEqual(body["max_completion_tokens"], 1)
        with self.assertRaises(MigrationError):
            smoke._model_request(alias, endpoints, "gateway.example", "v1/messages")
        image_test = asset("alias", "minimum", 1)
        image_test["smokeTests"][0]["request"]["api"] = "v1/images/generations"
        with self.assertRaises(MigrationError):
            smoke._approved_checks({"assets": [image_test]})

    def test_mcp_check_runs_only_initialize_notification_and_tools_list(self):
        server = {"properties": {
            "versions": ["2025-06-18"],
            "gatewayEndpoints": [{"api": "mcp", "url": "https://gateway.example/tools"}],
        }}
        replies = [
            (200, {"Mcp-Session-Id": "session-1"},
             {"id": 1, "result": {"protocolVersion": "2025-06-18"}}),
            (202, {}, None),
            (200, {}, {"id": 2, "result": {"tools": [{"name": "echo"}]}}),
        ]
        calls = []

        def fake_request(url, token, body, session_id=None, version=None):
            calls.append((body, session_id, version))
            return replies.pop(0)

        with patch.object(smoke, "_mcp_request", side_effect=fake_request):
            result = smoke._mcp_check(server, "gateway.example", "not-recorded", "2025-06-18")

        self.assertEqual([call[0].get("method") for call in calls],
                         ["initialize", "notifications/initialized", "tools/list"])
        self.assertEqual(calls[1][1:], ("session-1", "2025-06-18"))
        self.assertEqual(result["tools"], ["echo"])
        self.assertEqual(len(calls), 3)

    def test_endpoint_must_match_read_back_gateway_hostname(self):
        with self.assertRaises(MigrationError):
            smoke._endpoint_url(
                {"url": "https://guessed.example/default/models/chat"},
                "gateway.example",
            )

    def test_confirmation_must_bind_the_exact_inventory_digest(self):
        digest = "sha256:" + "a" * 64
        confirmation = {
            "schemaVersion": "1.0", "inventoryDigest": digest,
            "confirmation": {"confirmedAt": "2026-01-01T00:00:00Z",
                             "evidence": "User confirmed the reviewed inventory."},
            "assets": [],
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.json"
            path.write_text(json.dumps(confirmation))
            smoke._validate_confirmation(path, digest)
            with self.assertRaises(MigrationError):
                smoke._validate_confirmation(path, "sha256:" + "b" * 64)

    def test_resume_selects_only_unchecked_assets(self):
        def candidate(name):
            item = asset("alias", "minimum", 1, 1)
            item["id"] = name
            item["targetId"] = f"/aliases/{name}"
            item["smokeTests"][0]["id"] = "minimal"
            return item

        previous = candidate("previous")
        unchecked = candidate("unchecked")
        for status in ("passed", "failed", "blocked", "skipped"):
            with self.subTest(status=status):
                check = {"id": "smoke-minimal", "status": status, "evidence": "Prior receipt."}
                receipt = {"checks": [dict(check)]}
                pending, all_passed = smoke._pending_checks(
                    [previous, unchecked], {"previous": receipt})
                self.assertEqual(pending, [unchecked])
                self.assertEqual(all_passed, status == "passed")
                self.assertEqual(receipt["checks"], [check])
                with self.assertRaises(MigrationError):
                    smoke._pending_checks([previous], {"previous": receipt})

        prior = [candidate(status) for status in ("passed", "failed", "blocked")]
        receipts = {
            item["id"]: {"checks": [{"id": "smoke-minimal", "status": item["id"],
                                     "evidence": "Prior receipt."}]}
            for item in prior
        }
        pending, all_passed = smoke._pending_checks(prior + [unchecked], receipts)
        self.assertEqual(pending, [unchecked])
        self.assertFalse(all_passed)

        with self.assertRaises(MigrationError):
            smoke._pending_checks([], {})
        with self.assertRaises(MigrationError):
            smoke._pending_checks([previous, {**unchecked, "targetId": "/ALIASES/PREVIOUS"}], {})
        with self.assertRaises(MigrationError):
            smoke._pending_checks([previous, {**unchecked, "id": "previous"}], {})
        duplicate = {"id": "smoke-minimal", "status": "passed", "evidence": "Prior receipt."}
        with self.assertRaises(MigrationError):
            smoke._pending_checks(
                [previous, unchecked],
                {"previous": {"checks": [duplicate, dict(duplicate)]}},
            )

    def test_runner_uses_read_back_url_and_persists_receipt_without_replay(self):
        destination = (
            "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.ApiManagement/"
            "aigateways/gateway"
        )
        alias_id = destination + "/workspaces/default/aliases/callable"
        inventory = {
            "schemaVersion": "1.0", "revision": 1,
            "sourceId": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.ApiManagement/service/source",
            "destinationId": destination,
            "evidence": [{"path": "source.json", "digest": "sha256:" + "a" * 64,
                          "capturedAt": "2026-01-01T00:00:00Z", "scope": "test"}],
            "decisions": [], "exclusions": [], "blockers": [], "inputs": [],
            "assets": [{
                "id": "test-alias", "kind": "alias", "action": "reuse",
                "targetId": alias_id, "sourceIds": ["source-alias"], "dependsOn": [],
                "configuration": {"aliasName": "Callable"},
                "preconditions": ["Alias exists."], "commands": [], "outputs": [],
                "readBack": [{"command": {"argv": ["az", "aigateway", "model-alias",
                                                   "show", "--name", "callable"],
                                           "purpose": "Read alias."},
                              "assertions": {"id": alias_id}}],
                "smokeTests": [{
                    "id": "minimal", "required": True, "purpose": "Minimal inference.",
                    "request": {"mode": "minimal-inference", "api": "v1/chat/completions"},
                    "credentialInputs": [], "bounds": {"maxRequests": 1, "maxTokens": 1},
                    "expected": "Successful inference.", "skipWhen": "No route.",
                }],
                "verificationLimits": "Does not establish output quality.",
                "sideEffects": "One bounded inference request.", "rollback": "No writes.",
            }],
        }
        approved_digest = digest(inventory)
        confirmation = {
            "schemaVersion": "1.0", "inventoryDigest": approved_digest,
            "confirmation": {"confirmedAt": "2026-01-01T00:00:00Z",
                             "evidence": "User confirmed this inventory."},
            "assets": [],
        }
        endpoint = "https://gateway.example/default/models/openai/v1/chat/completions"

        def fake_az(argv):
            if argv[1:3] == ["aigateway", "show"]:
                return {"id": destination,
                        "properties": {"frontend": {"defaultHostname": "gateway.example"}}}
            if argv[1:4] == ["aigateway", "model-alias", "list"]:
                return [{"id": alias_id, "name": "callable",
                         "properties": {"aliasName": "Callable",
                                        "gatewayEndpoints": [{"api": "v1/chat/completions",
                                                             "url": endpoint}]}}]
            if argv[1:4] == ["aigateway", "mcp", "list"]:
                return []
            if argv[1:3] == ["account", "get-access-token"]:
                return {"accessToken": "not-persisted"}
            raise AssertionError(argv)

        with tempfile.TemporaryDirectory() as folder:
            inventory_path = Path(folder) / "inventory.json"
            confirmation_path = Path(folder) / "confirmation.json"
            output_path = Path(folder) / "results.json"
            inventory_path.write_text(json.dumps(inventory))
            confirmation_path.write_text(json.dumps(confirmation))
            with patch.object(smoke, "run_az", side_effect=fake_az), \
                    patch.object(smoke, "_http", return_value=(
                        200, {"Content-Type": "application/json"},
                        b'{"choices":[{"message":{"content":"OK"}}]}',
                    )) as request:
                self.assertTrue(smoke.run_smoke_tests(
                    inventory_path, confirmation_path, approved_digest, output_path))
                request.assert_called_once()
                self.assertEqual(request.call_args.args[1], endpoint)
            results = read_json(output_path)
            validate_schema(results, "migration-results")
            check = results["assets"][0]["checks"][0]
            self.assertEqual(check["status"], "passed")
            self.assertNotIn("not-persisted", output_path.read_text())
            with patch.object(smoke, "run_az") as azure:
                with self.assertRaises(MigrationError):
                    smoke.run_smoke_tests(inventory_path, output_path, approved_digest,
                                          Path(folder) / "retry.json")
                azure.assert_not_called()

            next_id = destination + "/workspaces/default/aliases/next"
            next_endpoint = "https://gateway.example/default/models/v1/chat/completions"
            next_asset = json.loads(json.dumps(inventory["assets"][0]))
            next_asset["id"] = "next-alias"
            next_asset["targetId"] = next_id
            next_asset["configuration"]["aliasName"] = "Next"
            next_asset["readBack"][0]["command"]["argv"][-1] = "next"
            next_asset["readBack"][0]["assertions"]["id"] = next_id
            inventory["assets"].append(next_asset)
            resumed_digest = digest(inventory)
            inventory_path.write_text(json.dumps(inventory))
            resumed_confirmation = {
                "schemaVersion": "1.0", "inventoryDigest": resumed_digest,
                "confirmation": {"confirmedAt": "2026-01-01T00:00:00Z",
                                 "evidence": "User confirmed both aliases."},
                "assets": [{
                    "assetId": "test-alias", "provisioning": "succeeded",
                    "checks": [{"id": "smoke-minimal", "status": "failed",
                                "evidence": "Earlier request failed."}],
                    "notes": "",
                }],
            }
            resumed_confirmation_path = Path(folder) / "resumed-confirmation.json"
            resumed_confirmation_path.write_text(json.dumps(resumed_confirmation))

            def fake_resume_az(argv):
                if argv[1:4] == ["aigateway", "model-alias", "list"]:
                    return [{"id": next_id, "name": "next",
                             "properties": {"aliasName": "Next",
                                            "gatewayEndpoints": [{"api": "v1/chat/completions",
                                                                 "url": next_endpoint}]}}]
                return fake_az(argv)

            resumed_path = Path(folder) / "resumed.json"
            with patch.object(smoke, "run_az", side_effect=fake_resume_az), \
                    patch.object(smoke, "_http", return_value=(
                        200, {"Content-Type": "application/json"},
                        b'{"choices":[{"message":{"content":"OK"}}]}',
                    )) as request:
                self.assertFalse(smoke.run_smoke_tests(
                    inventory_path, resumed_confirmation_path, resumed_digest, resumed_path))
                request.assert_called_once()
                self.assertEqual(request.call_args.args[1], next_endpoint)
            resumed = read_json(resumed_path)
            self.assertEqual(resumed["assets"][0]["checks"][0]["status"], "failed")
            self.assertEqual(resumed["assets"][1]["checks"][0]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
