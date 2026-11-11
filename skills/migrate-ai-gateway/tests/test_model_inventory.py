"""Offline source catalog and credential-boundary regressions."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from core import MigrationError, cli_failure_code, digest
from inventory import source_inventory
from model_inventory import NoRedirect, collect_models, import_models, validate_catalog
import migration
from fixtures import Azure, SOURCE, TARGET

ACCOUNT = "/subscriptions/sub/resourceGroups/models/providers/Microsoft.CognitiveServices/accounts/account"

def catalog(kind="Custom", complete=False):
    return {"schemaVersion": "1.0", "providers": [{
        "id": "provider-one", "kind": kind, "accountId": ACCOUNT if kind == "Foundry" else None,
        "endpoint": "https://provider.example", "credentialRef": None,
        "capturedAt": "2026-01-01T00:00:00Z",
        "provenance": "foundry-deployments" if kind == "Foundry" else "operator-manifest",
        "complete": complete, "error": None, "models": [{
            "id": "Model/A" if kind == "Custom" else "deployment-a",
            "deploymentId": None if kind == "Custom" else ACCOUNT + "/deployments/deployment-a",
            "family": "family-a", "version": "2", "apiFormat": "OpenAI",
            "endpoints": ["/chat/completions"]}]}]}

def apim_credential_source(resource="namedValues/upstream-key", field="value", scheme=None):
    return {"sourceId": SOURCE, "resourceId": SOURCE + "/" + resource, "field": field, "scheme": scheme}


class ModelInventoryTests(unittest.TestCase):
    def test_only_corroborated_error_codes_can_change_sku_applicability(self):
        code = "MethodNotAllowedInPricingTier"
        self.assertEqual(cli_failure_code('ERROR: Bad Request({"error":{"code":"' + code + '"}})'), code)
        self.assertEqual(cli_failure_code("ERROR: (" + code + ") This tier is unsupported."), code)
        self.assertEqual(cli_failure_code(
            "ERROR: No AI Gateway exists at the specified scope and name."), "ResourceNotFound")
        for error in (
                "ERROR: 403 Forbidden " + code,
                "ERROR: failed to read /service/" + code + "/gateways",
                'ERROR: {"error":{"code":"ServerError","message":"' + code + '"}}'):
            self.assertIsNone(cli_failure_code(error))

    def test_foundry_import_is_read_only_scoped_and_retains_deployment_identity(self):
        calls = []

        def runner(argv):
            calls.append(argv)
            if argv[1:3] == ["cloud", "show"]:
                return "https://management.azure.com/"
            self.assertEqual(argv[argv.index("--method") + 1], "get")
            self.assertEqual(argv[argv.index("--subscription") + 1], "sub")
            if "/deployments?" not in argv[argv.index("--url") + 1]:
                return {"id": ACCOUNT, "kind": "OpenAI", "properties": {"endpoint": "https://account.example"}}
            return {"value": [{"id": ACCOUNT + "/deployments/prod-chat",
                "properties": {"model": {"name": "base-family", "version": "2026", "format": "OpenAI"},
                               "capabilities": {"chatCompletion": "true"}}}]}

        result = collect_models("account-models", "Foundry", "https://account.example",
                                ACCOUNT, approved=True, runner=runner)
        provider = result["providers"][0]
        self.assertTrue(provider["complete"])
        self.assertEqual(provider["models"][0]["id"], "prod-chat")
        self.assertEqual(provider["models"][0]["family"], "base-family")
        self.assertEqual(provider["models"][0]["deploymentId"], ACCOUNT + "/deployments/prod-chat")
        self.assertEqual(provider["models"][0]["endpoints"], ["/chat/completions"])
        self.assertFalse(any("create" in call or "sync" in call for call in calls))

    def test_custom_catalog_keeps_exact_ids_and_never_uses_arm_authentication(self):
        calls = []

        def fetch(url, headers):
            calls.append((url, dict(headers)))
            self.assertEqual(url, "https://custom.example/v1/models")
            self.assertEqual(headers["Authorization"], "Bearer TEST_ONLY")
            return {"data": [{"id": "Owner/ModelCase"}, {"id": "owner/modelcase"}]}

        with patch.dict(os.environ, {"CUSTOM_TOKEN": "Bearer TEST_ONLY"}):
            result = collect_models("custom", "Custom", "https://custom.example/v1",
                credential_ref="CUSTOM_TOKEN", approved=True, fetch=fetch,
                runner=lambda _: self.fail("ARM CLI must not authenticate custom requests"))
        self.assertTrue(result["providers"][0]["complete"])
        self.assertEqual([m["id"] for m in result["providers"][0]["models"]],
                         ["Owner/ModelCase", "owner/modelcase"])
        self.assertNotIn("TEST_ONLY", json.dumps(result))

    def test_control_plane_named_value_credentials_stay_inside_catalog_process(self):
        secret = "offline-upstream-credential"
        source = apim_credential_source(scheme="Bearer")
        calls, requests = [], []

        def runner(argv):
            calls.append(argv)
            if argv[1:3] == ["cloud", "show"]:
                return "https://management.azure.com/"
            self.assertEqual(argv[argv.index("--method") + 1], "post")
            self.assertEqual(argv[argv.index("--url") + 1],
                             "https://management.azure.com" + source["resourceId"]
                             + "/listValue?api-version=2024-05-01")
            self.assertEqual(argv[argv.index("--subscription") + 1], SOURCE.split("/")[2])
            return {"value": secret}

        def fetch(url, headers):
            requests.append(url)
            self.assertEqual(headers["Authorization"], "Bearer " + secret)
            if len(requests) == 1:
                return {"data": [{"id": "ModelOne"}], "next": "?cursor=two"}
            return {"data": [{"id": "ModelTwo"}]}

        output = io.StringIO()
        environment = dict(os.environ)
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(output), \
                patch("migration.collect_models", side_effect=lambda *args, **kwargs:
                      collect_models(*args, **kwargs, runner=runner, fetch=fetch)):
            path = Path(temporary) / "models.json"
            self.assertEqual(migration.main([
                "collect-models", "--provider-id", "custom", "--kind", "Custom",
                "--endpoint", "https://upstream.example/v1", "--source-id", SOURCE,
                "--credential-resource-id", source["resourceId"],
                "--credential-field", "value", "--credential-scheme", "Bearer",
                "--approved-read", "--approved-credential-read", "--output-file", str(path)]), 0)
            result = json.loads(path.read_text())
        provider = result["providers"][0]
        self.assertTrue(provider["complete"])
        self.assertEqual(provider["credentialSource"], source)
        self.assertIsNone(provider["credentialRef"])
        self.assertEqual([model["id"] for model in provider["models"]], ["ModelOne", "ModelTwo"])
        self.assertEqual(requests, ["https://upstream.example/v1/models",
                                    "https://upstream.example/v1/models?cursor=two"])
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, json.dumps(calls))
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(dict(os.environ), environment)

    def test_control_plane_subscription_keys_only_use_the_advertised_apim_origin(self):
        keys = {"primaryKey": "offline-primary-credential", "secondaryKey": "offline-secondary-credential"}
        for field in keys:
            source = apim_credential_source("subscriptions/app", field)
            calls = []

            def runner(argv):
                calls.append(argv)
                if argv[1:3] == ["cloud", "show"]:
                    return "https://management.azure.com/"
                url = argv[argv.index("--url") + 1]
                if argv[argv.index("--method") + 1] == "get":
                    self.assertEqual(url, "https://management.azure.com" + SOURCE + "?api-version=2024-05-01")
                    return {"id": SOURCE, "properties": {
                        "gatewayUrl": "https://apim.example",
                        "hostnameConfigurations": [{"type": "Proxy", "hostName": "catalog.example"}]}}
                self.assertEqual(url, "https://management.azure.com" + source["resourceId"]
                                 + "/listSecrets?api-version=2024-05-01")
                return dict(keys)

            def fetch(url, headers):
                self.assertEqual(url, "https://catalog.example/meta/models")
                self.assertEqual(headers["Ocp-Apim-Subscription-Key"], keys[field])
                self.assertNotIn("Authorization", headers)
                return {"data": [{"id": "ObservedModel"}]}

            with self.subTest(field=field):
                result = collect_models("apim", "Custom", "https://catalog.example/meta",
                    credential_header="Ocp-Apim-Subscription-Key", approved=True,
                    credential_source=source, credential_read_approved=True, runner=runner, fetch=fetch)
                self.assertTrue(result["providers"][0]["complete"])
                for secret in keys.values():
                    self.assertNotIn(secret, json.dumps(result))
                    self.assertNotIn(secret, json.dumps(calls))
        result = collect_models("apim", "Custom", "https://unrelated.example/meta",
            approved=True, credential_source=source, credential_read_approved=True,
            runner=runner, fetch=lambda *_: self.fail("Do not send an APIM key to another origin."))
        self.assertIsNotNone(result["providers"][0]["error"])
        self.assertEqual(calls[-1][calls[-1].index("--method") + 1], "get")

    def test_control_plane_reads_require_approval_and_an_exact_credential_scope(self):
        source = apim_credential_source()
        cases = [
            {"credential_source": source},
            {"credential_source": source, "credential_read_approved": True, "approved": False},
            {"credential_source": source, "credential_read_approved": True, "credential_ref": "TOKEN"},
            {"credential_source": {**source, "resourceId": TARGET + "/namedValues/key"},
             "credential_read_approved": True},
            {"credential_source": {**source, "resourceId": SOURCE + "/namedValues"},
             "credential_read_approved": True},
            {"credential_source": {**source, "resourceId": SOURCE + "/namedValues/key/listValue"},
             "credential_read_approved": True},
            {"credential_source": {**source, "resourceId": SOURCE + "/namedValues/key%2Fother"},
             "credential_read_approved": True},
            {"credential_source": {**source, "field": "primaryKey"}, "credential_read_approved": True},
            {"credential_source": apim_credential_source("subscriptions/app", "primaryKey", "Bearer"),
             "credential_read_approved": True},
            {"credential_source": source, "credential_read_approved": True, "credential_header": "Host"},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(MigrationError):
                collect_models("custom", "Custom", "https://upstream.example",
                    **({"approved": True} | case),
                    runner=lambda *_: self.fail("Invalid or unapproved scope must not read Azure."),
                    fetch=lambda *_: self.fail("Invalid or unapproved scope must not fetch models."))

    def test_secret_read_failures_and_credential_echoes_do_not_leak_or_become_success(self):
        keys = {"primaryKey": "offline-primary-credential", "secondaryKey": "offline-secondary-credential"}
        source = apim_credential_source("subscriptions/app", "primaryKey")

        def runner(argv):
            if argv[1:3] == ["cloud", "show"]:
                return "https://management.azure.com/"
            if argv[argv.index("--method") + 1] == "get":
                return {"id": SOURCE, "properties": {"gatewayUrl": "https://apim.example"}}
            return dict(keys)

        for response in (
                {"data": [{"id": keys["primaryKey"]}]},
                {"data": [{"id": keys["secondaryKey"]}]},
                {"data": [{"id": "Observed"}], "next": "?token=" + keys["primaryKey"]},
                {"data": [{"id": "Observed"}], "next": "https://other.example/models"}):
            requests = []

            def fetch(url, headers):
                requests.append(url)
                return response

            result = collect_models("apim", "Custom", "https://apim.example",
                approved=True, credential_source=source, credential_read_approved=True,
                runner=runner, fetch=fetch)
            self.assertFalse(result["providers"][0]["complete"])
            self.assertIsNotNone(result["providers"][0]["error"])
            self.assertEqual(result["providers"][0]["models"], [])
            self.assertEqual(len(requests), 1)
            for secret in keys.values():
                self.assertNotIn(secret, json.dumps(result))
        def denied(argv):
            if argv[1:3] == ["cloud", "show"]:
                return "https://management.azure.com/"
            raise MigrationError("Denied " + keys["primaryKey"])

        result = collect_models("apim", "Custom", "https://apim.example",
            approved=True, credential_source=source, credential_read_approved=True, runner=denied,
            fetch=lambda *_: self.fail("Do not fetch models after a failed credential read."))
        self.assertIn("Scoped APIM credential read failed", result["providers"][0]["error"])
        self.assertNotIn(keys["primaryKey"], json.dumps(result))

        def missing(argv):
            if "--method" in argv and argv[argv.index("--method") + 1] == "post":
                return {}
            return runner(argv)

        result = collect_models("apim", "Custom", "https://apim.example",
            approved=True, credential_source=source, credential_read_approved=True, runner=missing,
            fetch=lambda *_: self.fail("Do not fetch models without the selected secret."))
        self.assertIn("lacks the selected secret", result["providers"][0]["error"])

        with patch("model_inventory.build_opener") as opener:
            error = HTTPError("https://apim.example/models", 403, keys["primaryKey"], {}, None)
            opener.return_value.open.side_effect = error
            result = collect_models("apim", "Custom", "https://apim.example",
                approved=True, credential_source=source, credential_read_approved=True, runner=runner)
        self.assertTrue(error.closed)
        self.assertIn("HTTP 403", result["providers"][0]["error"])
        self.assertNotIn(keys["primaryKey"], json.dumps(result))

        for secret in (keys["primaryKey"], "bad\r\nheader"):
            def fetch(*_):
                raise MigrationError("Upstream echoed " + keys["primaryKey"])

            with patch("model_inventory.read_apim_credential", return_value=(secret, list(keys.values()))):
                result = collect_models("apim", "Custom", "https://apim.example",
                    approved=True, credential_source=source, credential_read_approved=True, fetch=fetch)
            self.assertFalse(result["providers"][0]["complete"])
            self.assertNotIn(keys["primaryKey"], json.dumps(result))
            self.assertNotIn("bad\r\nheader", json.dumps(result))

    def test_partial_unsafe_and_unavailable_catalogs_require_manual_input_not_empty_success(self):
        for page in (
                {"data": [{"id": "one"}], "next": "https://other.example/models"},
                {"data": [{"id": "one"}], "has_more": True},
                {"data": [{"id": "one"}], "next_token": "unknown-contract"},
                {"data": [{"id": "*"}]}, {"data": [{"id": "one"}, {"id": "one"}]},
                {"unexpected": []}):
            with self.subTest(page=page):
                result = collect_models("custom", "Custom", "https://custom.example",
                                        approved=True, fetch=lambda u, h: page)
                self.assertFalse(result["providers"][0]["complete"])
                self.assertTrue(result["providers"][0]["error"])
                self.assertEqual(result["providers"][0]["models"], [])
        with self.assertRaises(MigrationError):
            collect_models("custom", "Custom", "https://custom.example")
        with self.assertRaises(MigrationError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example/models")

    def test_manual_manifest_approval_and_non_exhaustive_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "models.json"
            models = catalog()
            path.write_text(json.dumps(models))
            self.assertEqual(import_models(path, digest(models)), models)
            with self.assertRaises(MigrationError):
                import_models(path, digest({"different": True}))
            models["providers"][0]["complete"] = True
            with self.assertRaises(MigrationError):
                validate_catalog(models)

    def test_catalog_changes_and_credential_echoes_are_not_successful_discovery(self):
        with patch.dict(os.environ, {"SOURCE_TOKEN": "Bearer CREDENTIAL_TEST_ONLY"}):
            result = collect_models("custom", "Custom", "https://custom.example",
                credential_ref="SOURCE_TOKEN", approved=True,
                fetch=lambda u, h: {"data": [{"id": "CREDENTIAL_TEST_ONLY"}]})
        self.assertFalse(result["providers"][0]["complete"])
        self.assertNotIn("CREDENTIAL_TEST_ONLY", json.dumps(result))
        models = catalog()
        models["providers"][0]["models"][0].update(apiFormat="FutureProtocol", endpoints=["/future"])
        validate_catalog(models)

    def test_source_discriminator_and_sku_gaps_are_evidence_based(self):
        azure = Azure()
        api = SOURCE + "/apis/ordinary"
        azure.collections[SOURCE + "/apis"] = {"value": [{"id": api, "properties": {}}]}
        for domain in ("gateways", "workspaces"):
            azure.collections[SOURCE + "/" + domain] = MigrationError(
                "Restricted.", code="MethodNotAllowedInPricingTier")
        source = source_inventory(SOURCE, azure)
        self.assertTrue(next(c for c in source["coverage"] if c["domain"] == "api-tools")["establishesCompleteness"])
        for domain in ("gateways", "workspaces"):
            self.assertEqual(next(c for c in source["coverage"] if c["domain"] == domain)["status"], "notApplicable")
        azure.collections[SOURCE + "/workspaces"] = {"value": []}
        azure.collections[api + "/tools"] = MigrationError("Forbidden.")
        azure.collections[SOURCE + "/gateways"] = MigrationError("Unclassified server failure.")
        source = source_inventory(SOURCE, azure)
        self.assertFalse(next(c for c in source["coverage"] if c["domain"] == "api-tools")["establishesCompleteness"])
        self.assertFalse(next(c for c in source["coverage"] if c["domain"] == "gateways")["establishesCompleteness"])
