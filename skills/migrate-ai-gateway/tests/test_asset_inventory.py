"""Asset-review contracts and the read-only public entry point."""

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from core import MigrationError, ROOT, digest, read_json, validate_schema
import migration


class AssetInventoryTests(unittest.TestCase):
    def setUp(self):
        self.inventory = read_json(ROOT / "examples/migration-inventory.json")

    def test_asset_contract_requires_commands_assertions_and_secret_boundaries(self):
        validate_schema(self.inventory, "migration-inventory")
        for mutate in (
            lambda d: d["assets"][0].update(commands=[]),
            lambda d: d["assets"][0].update(readBack=[]),
            lambda d: d["assets"][0]["commands"][0].update(argv=["python", "apply.py"]),
            lambda d: d["assets"][0].update(action="reuse"),
            lambda d: d["inputs"].append({"id": "backend-key", "kind": "secret", "purpose": "Backend access"}),
            lambda d: d["inputs"].append({
                "id": "provider-config", "kind": "json-file", "purpose": "Provider JSON", "path": "provider.json"}),
        ):
            candidate = copy.deepcopy(self.inventory)
            mutate(candidate)
            with self.assertRaises(MigrationError):
                validate_schema(candidate, "migration-inventory")

    def test_explicit_output_binding_and_external_scope_are_reviewable(self):
        asset = copy.deepcopy(self.inventory["assets"][1])
        asset.update(
            id="foundry-access", kind="external", action="create",
            targetId="/subscriptions/example-sub/resourceGroups/models/providers/Microsoft.CognitiveServices/accounts/account",
            dependsOn=["gateway-identity"],
            configuration={"roleDefinitionId": "reviewed-role-id", "scope": "exact-account"},
            commands=[{
                "argv": ["az", "role", "assignment", "create", "--assignee-object-id",
                         {"assetId": "gateway-identity", "output": "principal-id"},
                         "--assignee-principal-type", "ServicePrincipal",
                         "--role", "reviewed-role-id", "--scope", "exact-account"],
                "purpose": "Grant only the inventoried role and scope to the verified principal.",
            }])
        self.inventory["assets"].append(asset)
        validate_schema(self.inventory, "migration-inventory")
        asset["commands"][0]["argv"][5] = {"assetId": "gateway-identity"}
        with self.assertRaises(MigrationError):
            validate_schema(self.inventory, "migration-inventory")

    def test_smoke_test_requires_bounded_requests_and_expected_outcome(self):
        smoke = {
            "id": "minimal-chat", "required": True, "purpose": "Check selected model route",
            "request": {"method": "POST", "url": "https://gateway.example/openai/v1/chat/completions",
                        "payload": {"model": "approved-alias", "messages": [{"role": "user", "content": "Hi"}],
                                    "max_tokens": 1}},
            "credentialInputs": ["client-key"],
            "bounds": {"maxRequests": 1, "maxTokens": 1},
            "expected": "Successful response from the selected route",
            "skipWhen": "Unavailable credential blocks required verification.",
        }
        self.inventory["inputs"] = [{
            "id": "client-key", "kind": "secret", "purpose": "Approved smoke test only",
            "source": "Existing securely supplied destination credential",
            "allowedDestination": "https://gateway.example",
            "handling": "Native secure input; no logging or persistence.",
        }]
        self.inventory["assets"][0]["smokeTests"] = [smoke]
        validate_schema(self.inventory, "migration-inventory")
        for field in ("request", "bounds", "expected"):
            candidate = copy.deepcopy(self.inventory)
            del candidate["assets"][0]["smokeTests"][0][field]
            with self.assertRaises(MigrationError):
                validate_schema(candidate, "migration-inventory")
        for bounds in ({"maxRequests": 1, "maxCost": 0.01}, {"maxRequests": 1, "currency": "USD"}):
            candidate = copy.deepcopy(self.inventory)
            candidate["assets"][0]["smokeTests"][0]["bounds"] = bounds
            with self.assertRaises(MigrationError):
                validate_schema(candidate, "migration-inventory")
        smoke["bounds"].update(maxCost=0.01, currency="USD")
        validate_schema(self.inventory, "migration-inventory")

    def test_receipts_keep_unknown_outcomes_and_skips_separate_from_success(self):
        result = {
            "schemaVersion": "1.0", "inventoryDigest": digest(self.inventory),
            "confirmation": {"confirmedAt": "2026-01-01T00:00:00Z", "evidence": "Actual user confirmation"},
            "assets": [{
                "assetId": "gateway", "provisioning": "unknown",
                "checks": [{"id": "read-back", "status": "blocked", "evidence": "Target read failed."},
                           {"id": "smoke", "status": "skipped", "evidence": "No callable route yet."}],
                "notes": "Read exact target before replay.",
            }],
        }
        validate_schema(result, "migration-results")
        result["assets"][0]["checks"][0]["evidence"] = ""
        with self.assertRaises(MigrationError):
            validate_schema(result, "migration-results")

    def test_removed_deployment_commands_cannot_invoke_azure(self):
        for command in ("init", "apply", "execute", "approve", "approve-group", "compile-plan",
                        "validate-plan", "export-plan", "progress", "recover-lock", "report",
                        "record-verification", "accept-residual", "cancel"):
            with self.subTest(command=command), patch("core.subprocess.run") as run, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                migration.main([command, "--state-dir", "old-state"])
            run.assert_not_called()

    def test_document_utilities_are_local_and_inspection_is_explicitly_scoped(self):
        with tempfile.TemporaryDirectory() as folder, patch("core.subprocess.run") as run:
            path = Path(folder) / "inventory.json"
            path.write_text(json.dumps(self.inventory))
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(migration.main(["document-digest", "--path", str(path)]), 0)
            self.assertEqual(output.getvalue().strip(), digest(self.inventory))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(migration.main([
                    "validate-document", "--path", str(path), "--schema", "migration-inventory"]), 0)
            run.assert_not_called()
            with patch("migration.inspect_cli", return_value={"commands": {"create": []}}) as inspect:
                migration.main(["inspect-cli", "--command", "create", "--output-file", str(Path(folder) / "cli.json")])
            inspect.assert_called_once_with(["create"])


if __name__ == "__main__":
    unittest.main()
