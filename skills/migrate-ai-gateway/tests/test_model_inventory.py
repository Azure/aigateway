"""Offline catalog, explicit-selection and graph reconciliation regressions."""

import base64
import copy
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import MigrationError, cli_failure_code, digest, semantic
from execution import approve, execute, initialize, record_behavior, refresh, report, mutation_argv, selectors
from gateway import capabilities, destination_inventory, exposed_options
from inventory import inventory_item, source_inventory
from model_inventory import NoRedirect, collect_models, import_models, validate_catalog
from planning import validate_plan, policy_state, reviewed_arguments
from selection import backend_ids, compile_selection, removal_proposals, validate_selection
from core import State
import migration
from test_migration import Azure, SOURCE, TARGET, cli


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


class GraphAzure(Azure):
    def __init__(self):
        super().__init__()
        self.resources = {group: {} for group in ("model-provider", "model", "model-alias", "mcp", "api-key")}

    def __call__(self, argv):
        if argv[:2] == ["az", "aigateway"] and argv[2] in self.resources:
            self.calls.append(argv)
            group, action = argv[2:4]
            if action == "list":
                return copy.deepcopy(list(self.resources[group].values()))
            name = argv[argv.index("--name") + 1]
            provider = argv[argv.index("--provider-name") + 1] if "--provider-name" in argv else None
            suffix = {
                "model-provider": f"/workspaces/default/modelProviders/{name}",
                "model": f"/workspaces/default/modelProviders/{provider}/models/{name}",
                "model-alias": f"/workspaces/default/aliases/{name}",
                "mcp": f"/workspaces/default/toolServers/{name}", "api-key": f"/apiKeys/{name}",
            }[group]
            rid = TARGET + suffix
            if action == "show":
                if rid not in self.resources[group]:
                    raise MigrationError("Missing selected resource.")
                return copy.deepcopy(self.resources[group][rid])
            if action not in ("create", "update"):
                raise AssertionError(argv)
            properties = copy.deepcopy(self.resources[group].get(rid, {}).get("properties", {}))
            wire = {"kind": "kind", "custom": "custom", "foundry": "foundry",
                    "deployment-config": "deployment", "deployment": "deployment",
                    "api-format": "apiFormat", "supported-endpoints": "supportedEndpoints",
                    "backend-models": "backendModels", "routing-name": "aliasName",
                    "display-name": "displayName", "endpoints": "endpoints",
                    "versions": "versions", "state": "state", "expiration-date": "expirationDate"}
            for flag, field in wire.items():
                if "--" + flag in argv:
                    value = argv[argv.index("--" + flag) + 1]
                    properties[field] = json.loads(Path(value[1:]).read_text()) if value.startswith("@") else value
            resource = {"id": rid, "name": name, "properties": properties}
            self.resources[group][rid] = resource
            return copy.deepcopy(resource)
        return super().__call__(argv)


def graph_fixture():
    azure = GraphAzure()
    api, backend, key = SOURCE + "/apis/inference", SOURCE + "/backends/upstream", SOURCE + "/namedValues/upstream-key"
    operation = api + "/operations/chat"
    azure.collections[SOURCE + "/apis"] = {"value": [{"id": api, "name": "inference",
        "properties": {"type": "http", "backendId": "upstream"}}]}
    azure.collections[api + "/operations"] = {"value": [{"id": operation, "name": "chat",
        "properties": {"method": "POST", "urlTemplate": "/chat/completions"}}]}
    azure.collections[SOURCE + "/backends"] = {"value": [{"id": backend, "name": "upstream",
        "properties": {"url": "https://provider.example", "credentials": {"header": {"Authorization": ["{{upstream-key}}"]}}}}]}
    azure.collections[SOURCE + "/namedValues"] = {"value": [{"id": key, "name": "upstream-key",
        "properties": {"secret": True, "value": "NEVER_PERSIST"}}]}
    models = catalog()
    bundle = initialize(source_inventory(SOURCE, azure), destination_inventory(TARGET, azure),
                        capabilities(cli()), models)
    selection = {
        "schemaVersion": "1.0", "catalogDigest": digest(semantic(models)),
        "gateway": {"location": "eastus2"},
        "providers": [{"id": "provider-one", "sourceIds": [backend, key], "evidence": "Selected upstream credential boundary.",
            "settings": {"kind": "Custom", "custom": {"endpoint": "https://provider.example",
                "authentication": {"kind": "ApiKey", "apiKey": {"headerName": "Authorization",
                    "value": {"$runtimeSecret": "UPSTREAM_TOKEN"}}}}}}],
        "models": [{"provider": "provider-one", "id": "Model/A", "name": "model-a", "alias": "chat-a",
            "routingName": "customer/model-a", "apiFormat": "OpenAIChatCompletions",
            "endpoints": ["/openai/v1/chat/completions"], "sourceIds": [api, operation],
            "evidence": "Explicit runtime ID and selected chat contract; verify upstream behavior before completion."}],
        "mcp": [], "keys": [{"name": "app-key", "displayName": "Application",
            "sourceIds": [api], "accessDecision": "Explicit gateway-wide key and client endpoint change."}],
        "retained": [],
    }
    return bundle, selection, azure


class ModelInventoryTests(unittest.TestCase):
    def test_only_corroborated_error_codes_can_change_sku_applicability(self):
        code = "MethodNotAllowedInPricingTier"
        self.assertEqual(cli_failure_code('ERROR: Bad Request({"error":{"code":"' + code + '"}})'), code)
        self.assertEqual(cli_failure_code("ERROR: (" + code + ") This tier is unsupported."), code)
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

    def test_catalog_refresh_does_not_reuse_secret_read_approval_implicitly(self):
        bundle, _, azure = graph_fixture()
        provider = bundle["model-catalog.json"]["providers"][0]
        provider.update(credentialSource=apim_credential_source(), provenance="custom-models", complete=True)
        with self.assertRaisesRegex(MigrationError, "separate approval"):
            refresh(bundle, runner=lambda *_: self.fail("Unapproved refresh must not read Azure."))
        with patch("execution.collect_models", return_value=copy.deepcopy(bundle["model-catalog.json"])) as collect:
            refresh(bundle, azure, cli, credential_read_approved=True)
        self.assertEqual(collect.call_args.kwargs["credential_source"], provider["credentialSource"])
        self.assertTrue(collect.call_args.kwargs["credential_read_approved"])
        foreign = copy.deepcopy(bundle["model-catalog.json"])
        foreign["providers"][0]["credentialSource"] = {
            **apim_credential_source(), "sourceId": SOURCE + "-other",
            "resourceId": SOURCE + "-other/namedValues/upstream-key"}
        with self.assertRaisesRegex(MigrationError, "selected migration source"):
            initialize(bundle["source-inventory.json"], bundle["destination-inventory.json"],
                       bundle["capability-contract.json"], foreign)

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
        validate_catalog(models)  # Source facts are not filtered by destination capabilities.

    def test_source_discriminator_and_sku_gaps_are_evidence_based(self):
        azure = Azure()
        api = SOURCE + "/apis/ordinary"
        azure.collections[SOURCE + "/apis"] = {"value": [{"id": api, "properties": {}}]}
        azure.collections[SOURCE + "/gateways"] = MigrationError("Restricted.", code="MethodNotAllowedInPricingTier")
        source = source_inventory(SOURCE, azure)
        self.assertTrue(next(c for c in source["coverage"] if c["domain"] == "api-tools")["establishesCompleteness"])
        self.assertEqual(next(c for c in source["coverage"] if c["domain"] == "gateways")["status"], "notApplicable")
        azure.collections[api + "/tools"] = MigrationError("Forbidden.")
        azure.collections[SOURCE + "/gateways"] = MigrationError("Unclassified server failure.")
        source = source_inventory(SOURCE, azure)
        self.assertFalse(next(c for c in source["coverage"] if c["domain"] == "api-tools")["establishesCompleteness"])
        self.assertFalse(next(c for c in source["coverage"] if c["domain"] == "gateways")["establishesCompleteness"])


class ResourceGraphTests(unittest.TestCase):
    def test_explicit_graph_has_one_behavior_owner_and_multiple_resource_kinds(self):
        bundle, selected, _ = graph_fixture()
        result = compile_selection(bundle, selected)
        validation = validate_plan(result)
        self.assertEqual(validation["status"], "valid", validation["errors"])
        self.assertEqual({t["capabilityId"] for t in result["todos.json"]["items"]},
                         {"gateway.create", "provider.create", "model.create", "alias.create", "key.create"})
        behaviors = [bid for m in result["mapping.json"]["items"] for bid in m["behaviorIds"]]
        self.assertEqual(len(behaviors), len(set(behaviors)))
        self.assertTrue(any(len(m.get("todoIds", [])) >= 3 for m in result["mapping.json"]["items"]))
        self.assertNotIn("NEVER_PERSIST", json.dumps(result))
        self.assertEqual(result["mapping.json"]["removalProposals"], [])

    def test_service_arm_id_casing_does_not_change_source_ownership(self):
        _, selected, azure = graph_fixture()
        azure.source["id"] = SOURCE.lower()
        bundle = initialize(source_inventory(SOURCE, azure), destination_inventory(TARGET, azure),
                            capabilities(cli()), catalog())
        result = compile_selection(bundle, selected)
        validation = validate_plan(result)
        self.assertEqual(validation["status"], "valid", validation["errors"])

    def test_remote_mcp_scope_is_bound_and_does_not_adopt_unrelated_api_behaviors(self):
        bundle, selected, azure = graph_fixture()
        remote = SOURCE + "/apis/remote-tools"
        azure.collections[SOURCE + "/apis"]["value"].append({"id": remote, "properties": {
            "type": "mcp", "serviceUrl": "https://remote.example",
            "mcpProperties": {"endpoints": {"message": {"uriTemplate": "/mcp"}}}}})
        bundle["source-inventory.json"] = source_inventory(SOURCE, azure)
        selected.update(providers=[], models=[], retained=[])
        selected["keys"][0]["sourceIds"] = [remote]
        selected["mcp"] = [{"name": "remote-tools", "sourceIds": [remote],
            "accessDecision": "Explicit client-key scope; upstream identity requires separate verification.",
            "evidence": "Observed remote MCP endpoint; no caller-identity equivalence assumed.",
            "endpoints": [{"kind": "mcp", "namespace": "remote", "mcp": {
                "transport": "streamableHttp", "url": "https://remote.example/mcp"}}]}]
        self.assertEqual(validate_plan(compile_selection(bundle, selected))["status"], "valid")
        selected["mcp"][0]["endpoints"][0]["mcp"]["url"] = "https://unrelated.example/mcp"
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)
        selected["mcp"][0]["endpoints"][0]["mcp"]["url"] = "https://remote.example/mcp"
        selected["mcp"][0]["sourceIds"].append(SOURCE + "/apis/inference")
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)

    def test_selection_rejects_wildcards_unrelated_operations_and_tampered_graphs(self):
        bundle, selected, _ = graph_fixture()
        for field, value in (("id", "*"), ("endpoints", ["/*"]), ("apiFormat", "AnyApi")):
            with self.subTest(field=field):
                changed = copy.deepcopy(selected)
                changed["models"][0][field] = value
                with self.assertRaises(MigrationError):
                    validate_selection(bundle, changed)
        result = compile_selection(bundle, selected)
        model = next(t for t in result["todos.json"]["items"] if t["capabilityId"] == "model.create")
        model["arguments"]["deployment-config"]["modelName"] = "Unselected"
        self.assertEqual(validate_plan(result)["status"], "invalid")
        result = compile_selection(bundle, selected)
        alias = next(t for t in result["todos.json"]["items"] if t["capabilityId"] == "alias.create")
        alias["resourceDependencies"] = []
        self.assertEqual(validate_plan(result)["status"], "invalid")

    def test_catalog_and_target_names_are_independent_and_admission_is_explicit(self):
        bundle, selected, _ = graph_fixture()
        selected["providers"][0]["name"] = "destination-provider"
        result = compile_selection(bundle, selected)
        validation = validate_plan(result)
        self.assertEqual(validation["status"], "valid", validation["errors"])
        model = next(t for t in result["todos.json"]["items"] if t["capabilityId"] == "model.create")
        self.assertEqual(model["target"]["provider"], "destination-provider")
        selected["keys"] = []
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)
        bundle, selected, _ = graph_fixture()
        bundle["model-catalog.json"]["providers"][0]["models"][0]["version"] = "changed"
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)

    def test_dynamic_or_cross_boundary_credentials_are_not_turned_into_shared_static_auth(self):
        bundle, selected, _ = graph_fixture()
        backend = next(i for i in bundle["source-inventory.json"]["items"] if i["domain"] == "backends")
        for field, value in (("credentialExpressions", True), ("queryParameterNames", ["token"]),
                             ("certificateReferences", True), ("headerNames", ["Authorization", "X-Other"])):
            with self.subTest(field=field):
                changed = copy.deepcopy(bundle)
                next(i for i in changed["source-inventory.json"]["items"] if i["id"] == backend["id"])["facts"][field] = value
                with self.assertRaises(MigrationError):
                    compile_selection(changed, selected)
        changed_selection = copy.deepcopy(selected)
        changed_selection["providers"][0]["settings"]["custom"]["authentication"]["apiKey"]["headerName"] = "X-Wrong"
        with self.assertRaises(MigrationError):
            compile_selection(bundle, changed_selection)
        next(c for c in bundle["source-inventory.json"]["coverage"] if c["domain"] == "policies")[
            "establishesCompleteness"] = False
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)

    def test_graph_executes_with_structural_checks_but_requires_mapping_behavior_proof(self):
        bundle, selected, azure = graph_fixture()
        bundle = compile_selection(bundle, selected)
        bundle["plan-validation.json"] = validate_plan(bundle)
        pdigest = bundle["plan-validation.json"]["planDigest"]
        before = copy.deepcopy(bundle)
        with self.assertRaises(MigrationError):
            execute(bundle, "gateway:target", pdigest, lambda b: None, azure, cli)
        self.assertEqual(bundle, before)
        with patch.dict(os.environ, {"UPSTREAM_TOKEN": "TEST_RUNTIME_ONLY"}):
            for todo in bundle["todos.json"]["items"]:
                approve(bundle, todo["id"], pdigest)
                execute(bundle, todo["id"], pdigest, lambda b: None, azure, cli)
        report(bundle, fresh=True)
        self.assertEqual(bundle["context.json"]["completionStatus"], "incomplete")
        for mapping in bundle["mapping.json"]["items"]:
            for bid in mapping.get("behaviorResults", {}):
                record_behavior(bundle, mapping["id"], bid, "administrator-attestation", digest("test evidence"), pdigest)
        report(bundle, fresh=True)
        self.assertEqual(bundle["context.json"]["completionStatus"], "complete")
        self.assertNotIn("TEST_RUNTIME_ONLY", json.dumps(bundle))

    def test_non_destructive_sync_updates_metadata_and_preserves_policies(self):
        bundle, selected, azure = graph_fixture()
        azure.gateway = {"id": TARGET, "type": "Microsoft.ApiManagement/aigateways",
                         "location": "eastus2",
                         "properties": {"provisioningState": "Succeeded"}}
        provider_id = TARGET + "/workspaces/default/modelProviders/provider-one"
        azure.resources["model-provider"][provider_id] = {"id": provider_id, "name": "provider-one",
            "properties": copy.deepcopy(selected["providers"][0]["settings"])}
        model_id = provider_id + "/models/model-a"
        azure.resources["model"][model_id] = {"id": model_id, "name": "model-a", "properties": {
            "deployment": {"modelName": "Model/A", "modelVersion": "1"}, "apiFormat": "OpenAIChatCompletions",
            "supportedEndpoints": ["/openai/v1/chat/completions"], "policies": [{"type": "keep-this-policy"}]}}
        stale_id = provider_id + "/models/old"
        azure.resources["model"][stale_id] = {"id": stale_id, "name": "old",
                                             "properties": {"deployment": {"modelName": "old"}}}
        bundle["destination-inventory.json"] = destination_inventory(TARGET, azure)
        selected["providers"][0]["reuseExisting"] = True
        bundle = compile_selection(bundle, selected)
        bundle["plan-validation.json"] = validate_plan(bundle)
        self.assertEqual(bundle["plan-validation.json"]["status"], "valid", bundle["plan-validation.json"]["errors"])
        pdigest = bundle["plan-validation.json"]["planDigest"]
        for todo in bundle["todos.json"]["items"]:
            approve(bundle, todo["id"], pdigest)
            execute(bundle, todo["id"], pdigest, lambda b: None, azure, cli)
        self.assertEqual(azure.resources["model"][model_id]["properties"]["deployment"]["modelVersion"], "2")
        self.assertEqual(azure.resources["model"][model_id]["properties"]["policies"], [{"type": "keep-this-policy"}])
        self.assertIn(stale_id, azure.resources["model"])
        self.assertFalse(any("delete" in call or "sync" in call for call in azure.calls))

    def test_failed_prerequisite_behavior_blocks_structurally_ready_dependents(self):
        bundle, selected, azure = graph_fixture()
        bundle = compile_selection(bundle, selected)
        bundle["plan-validation.json"] = validate_plan(bundle)
        pdigest = bundle["plan-validation.json"]["planDigest"]
        with patch.dict(os.environ, {"UPSTREAM_TOKEN": "TEST_RUNTIME_ONLY"}):
            for tid in ("gateway:target", "provider:provider-one"):
                approve(bundle, tid, pdigest)
                execute(bundle, tid, pdigest, lambda b: None, azure, cli)
        owner = next(m for m in bundle["mapping.json"]["items"]
                     if any("/backends/" in sid for sid in m["sourceIds"]))
        record_behavior(bundle, owner["id"], owner["behaviorIds"][0], "administrator-attestation",
                        digest("failed proof"), pdigest, status="failed")
        approve(bundle, "model:model-a:provider-one", pdigest)
        with self.assertRaises(MigrationError):
            execute(bundle, "model:model-a:provider-one", pdigest, lambda b: None, azure, cli)
        self.assertEqual(azure.resources["model"], {})

    def test_missing_runtime_input_does_not_create_an_unknown_mutation_attempt(self):
        bundle, selected, azure = graph_fixture()
        bundle = compile_selection(bundle, selected)
        bundle["plan-validation.json"] = validate_plan(bundle)
        pdigest = bundle["plan-validation.json"]["planDigest"]
        approve(bundle, "gateway:target", pdigest)
        execute(bundle, "gateway:target", pdigest, lambda b: None, azure, cli)
        provider = next(t for t in bundle["todos.json"]["items"] if t["id"] == "provider:provider-one")
        approve(bundle, provider["id"], pdigest)
        with patch.dict(os.environ, {"UPSTREAM_TOKEN": ""}), self.assertRaises(MigrationError):
            execute(bundle, provider["id"], pdigest, lambda b: None, azure, cli)
        self.assertEqual(provider["attempts"], [])
        self.assertEqual(provider["status"], "pending")
        self.assertEqual(azure.resources["model-provider"], {})

    def test_existing_aliases_are_preserved_unless_replacement_is_selected(self):
        bundle, selected, azure = graph_fixture()
        azure.gateway = {"id": TARGET, "type": "Microsoft.ApiManagement/aigateways",
                         "location": "eastus2", "properties": {"provisioningState": "Succeeded"}}
        alias_id = TARGET + "/workspaces/default/aliases/chat-a"
        azure.resources["model-alias"][alias_id] = {"id": alias_id, "name": "chat-a", "properties": {
            "aliasName": "existing-route", "backendModels": [{
                "resourceId": TARGET + "/workspaces/default/modelProviders/other/models/old",
                "priority": 0, "weight": 100}], "policies": [{"type": "preserve"}]}}
        bundle["destination-inventory.json"] = destination_inventory(TARGET, azure)
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)
        selected["models"][0]["updateAlias"] = True
        result = compile_selection(bundle, selected)
        self.assertEqual(validate_plan(result)["status"], "valid")
        self.assertTrue(any(t["capabilityId"] == "alias.update" for t in result["todos.json"]["items"]))
        self.assertEqual(azure.resources["model-alias"][alias_id]["properties"]["aliasName"], "existing-route")

    def test_public_catalog_and_graph_commands_persist_versioned_evidence(self):
        bundle, selected, _ = graph_fixture()
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)
            for name in ("source-inventory", "model-catalog", "destination-inventory", "capability-contract"):
                (root / (name + ".json")).write_text(json.dumps(bundle[name + ".json"]))
            (root / "selection.json").write_text(json.dumps(selected))
            state = root / "state"
            self.assertEqual(migration.main([
                "init", "--state-dir", str(state), "--source-file", str(root / "source-inventory.json"),
                "--destination-file", str(root / "destination-inventory.json"),
                "--capabilities-file", str(root / "capability-contract.json"),
                "--model-catalog-file", str(root / "model-catalog.json")]), 0)
            self.assertEqual(migration.main([
                "compile-plan", "--state-dir", str(state), "--selection-file", str(root / "selection.json")]), 0)
            loaded = State(state).load()
            self.assertEqual(loaded["context.json"]["schemaVersion"], "4.0")
            self.assertEqual(loaded["model-catalog.json"], bundle["model-catalog.json"])
            self.assertEqual(loaded["mapping.json"]["selection"], selected)
            digest_output = io.StringIO()
            with redirect_stdout(digest_output):
                migration.main(["model-catalog-digest", "--path", str(root / "model-catalog.json"), "--selection"])
            self.assertEqual(digest_output.getvalue().strip(), selected["catalogDigest"])
            self.assertEqual(migration.main([
                "import-models", "--manifest-file", str(root / "model-catalog.json"),
                "--approved-digest", digest(bundle["model-catalog.json"]),
                "--output-file", str(root / "imported.json")]), 0)
            old_generation = loaded["context.json"]["generationId"]
            refreshed = copy.deepcopy(bundle["model-catalog.json"])
            refreshed["providers"][0]["models"][0]["version"] = "3"
            updated_selection = copy.deepcopy(selected)
            updated_selection["catalogDigest"] = digest(semantic(refreshed))
            (root / "catalog-v3.json").write_text(json.dumps(refreshed))
            (root / "selection-v3.json").write_text(json.dumps(updated_selection))
            self.assertEqual(migration.main([
                "compile-plan", "--state-dir", str(state), "--selection-file", str(root / "selection-v3.json"),
                "--model-catalog-file", str(root / "catalog-v3.json")]), 0)
            latest = State(state).load()
            self.assertEqual(latest["model-catalog.json"]["providers"][0]["models"][0]["version"], "3")
            self.assertNotEqual(latest["context.json"]["generationId"], old_generation)
            preserved = json.loads((state / "generations" / old_generation / "model-catalog.json").read_text())
            self.assertEqual(preserved["providers"][0]["models"][0]["version"], "2")

    def test_catalog_alone_never_recreates_native_staleness_decisions(self):
        bundle, _, _ = graph_fixture()
        bundle["model-catalog.json"] = catalog("Foundry", complete=True)
        bundle["mapping.json"]["selection"] = {"providers": [{"id": "provider-one"}]}
        rid = TARGET + "/workspaces/default/modelProviders/provider-one/models/stale"
        bundle["destination-inventory.json"]["collections"].update({
            "model": [{"id": rid, "properties": {"deployment": {"resourceId": ACCOUNT + "/deployments/removed"}}}],
            "model-alias": [{"properties": {"backendModels": [{"resourceId": rid}]}}],
        })
        self.assertEqual(removal_proposals(bundle), [])
        bundle["model-catalog.json"]["providers"][0]["complete"] = False
        self.assertEqual(removal_proposals(bundle), [])

    def test_selected_mcp_contract_preserves_tool_name_and_path_parameter(self):
        bundle, selected, azure = graph_fixture()
        api = SOURCE + "/apis/colors"
        operation = api + "/operations/getColor"
        tool_api = SOURCE + "/apis/color-tools"
        tool = tool_api + "/tools/tool-id"
        azure.collections[SOURCE + "/apis"] = {"value": [
            {"id": api, "properties": {"type": "http", "serviceUrl": "https://colors.example"}},
            {"id": tool_api, "properties": {"type": "mcp", "subscriptionRequired": False}}]}
        azure.collections[api + "/operations"] = {"value": [{"id": operation, "properties": {
            "method": "GET", "urlTemplate": "/colors/{name}",
            "templateParameters": [{"name": "name", "type": "string", "required": True}],
            "responses": [{"statusCode": 200, "representations": []}]}}]}
        azure.collections[tool_api + "/tools"] = {"value": [{"id": tool, "properties": {
            "displayName": "getAColor", "operationId": operation}}]}
        bundle["source-inventory.json"] = source_inventory(SOURCE, azure)
        selected.update(providers=[], models=[], keys=[], retained=[])
        selected["keys"] = [{"name": "colors-client", "displayName": "Colors client",
            "sourceIds": [tool_api], "accessDecision": "Explicit gateway-key client change accepted."}]
        contract = {"openapi": "3.0.3", "info": {"title": "Colors", "version": "1"},
            "servers": [{"url": "https://colors.example"}], "paths": {"/colors/{name}": {"get": {
                "operationId": "getAColor", "parameters": [{"in": "path", "name": "name", "required": True,
                                                           "schema": {"type": "string"}}],
                "responses": {"200": {"description": "Color"}}}}}}
        def choose():
            return [{"name": "colors", "sourceIds": [api, operation, tool_api, tool],
                     "accessDecision": "Explicit client-key change accepted for this plan.",
                     "evidence": "Approved exact source contract; verify output and admission before completion.",
                     "endpoints": [{"kind": "openApi", "namespace": "colors", "openApi": {"specSource": {
                         "type": "inline", "contentBase64": base64.b64encode(json.dumps(contract).encode()).decode()}}}]}]
        selected["mcp"] = choose()
        self.assertEqual(validate_plan(compile_selection(bundle, selected))["status"], "valid")
        contract["paths"]["/colors/{name}"]["get"]["examples"] = {"unsafe": "Bearer SECRET_TEST"}
        selected["mcp"] = choose()
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)
        del contract["paths"]["/colors/{name}"]["get"]["examples"]
        schema_id = api + "/schemas/color"
        azure.collections[api + "/schemas"] = {"value": [{"id": schema_id}]}
        azure.collections[schema_id] = {"id": schema_id, "properties": {
            "contentType": "application/vnd.oai.openapi.components+json",
            "document": {"components": {"schemas": {"Color": {"type": "object",
                "properties": {"name": {"type": "string"}}, "required": ["name"]}}}}}}
        azure.collections[api + "/operations"]["value"][0]["properties"]["responses"][0]["representations"] = [{
            "contentType": "application/json", "schemaId": "color", "typeName": "Color"}]
        bundle["source-inventory.json"] = source_inventory(SOURCE, azure)
        contract["components"] = {"schemas": {"Color": {"type": "object",
            "properties": {"name": {"type": "string"}}, "required": ["name"]}}}
        contract["paths"]["/colors/{name}"]["get"]["responses"]["200"]["content"] = {
            "application/json": {"schema": {"$ref": "#/components/schemas/Color"}}}
        selected["mcp"] = choose()
        selected["mcp"][0]["sourceIds"].append(schema_id)
        self.assertEqual(validate_plan(compile_selection(bundle, selected))["status"], "valid")
        contract["components"]["schemas"]["Color"]["properties"]["name"]["type"] = "integer"
        selected["mcp"] = choose()
        selected["mcp"][0]["sourceIds"].append(schema_id)
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)
        contract["components"]["schemas"]["Color"]["properties"]["name"]["type"] = "string"
        contract["paths"]["/colors/{name}"]["get"]["operationId"] = "getColor"
        selected["mcp"] = choose()
        selected["mcp"][0]["sourceIds"].append(schema_id)
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)


class B22GraphTests(unittest.TestCase):
    def selection(self):
        return {"schemaVersion": "1.0", "catalogDigest": digest({"schemaVersion": "1.0", "providers": []}),
                "gateway": {}, "providers": [], "models": [], "mcp": [], "keys": [], "retained": []}

    def binding(self, source, sid, **settings):
        return {"sourceIds": [sid], "behaviorIds": [b["id"] for b in source["behaviors"] if b["sourceId"] == sid],
                "evidence": "Reviewed configuration and independent behavior verification are required.",
                "scopeDecision": "Explicitly selected workspace scope rather than implicit APIM inheritance.",
                **settings}

    def pool_selection(self, priorities=(0, 0)):
        _, selected, azure = graph_fixture()
        api = SOURCE + "/apis/inference"
        pool, other = SOURCE + "/backends/model-pool", SOURCE + "/backends/other"
        policy = api + "/policies/policy"
        members = [SOURCE + "/backends/upstream", other]
        azure.collections[SOURCE + "/apis"]["value"][0]["properties"]["backendId"] = "model-pool"
        azure.collections[SOURCE + "/backends"]["value"].extend([
            {"id": other, "name": "other", "properties": {"url": "https://other.example",
                "credentials": {"header": {"Authorization": ["{{upstream-key}}"]}}}},
            {"id": pool, "name": "model-pool", "properties": {"type": "Pool", "pool": {"services": [
                {"id": sid, "priority": priority, "weight": weight}
                for sid, priority, weight in zip(members, priorities, (75, 25))]}}}])
        azure.collections[api + "/policies"] = {"value": [{"id": policy, "properties": {
            "value": '<policies><inbound><set-backend-service backend-id="model-pool"/></inbound>'
                     '<backend><forward-request/></backend><on-error/></policies>'}}]}
        models = catalog()
        other_catalog = copy.deepcopy(models["providers"][0])
        other_catalog.update(id="provider-two", endpoint="https://other.example")
        other_catalog["models"][0].update(id="Owner/Different", family="different-family")
        models["providers"].append(other_catalog)
        other_provider = copy.deepcopy(selected["providers"][0])
        other_provider.update(id="provider-two", name="destination-provider-two", sourceIds=[other])
        other_provider["settings"]["custom"]["endpoint"] = "https://other.example"
        selected["providers"].append(other_provider)
        for model in selected["models"]:
            model.update(explicitAlias=True)
            model.pop("alias")
            model.pop("routingName")
            model["sourceIds"].append(policy)
        other_model = copy.deepcopy(selected["models"][0])
        other_model.update(provider="provider-two", id="Owner/Different", name="model-b")
        selected["models"].append(other_model)
        selected["aliases"] = [{
            "name": "production", "routingName": "customer/production", "sourcePoolId": pool,
            "sourceIds": [pool, *selected["models"][0]["sourceIds"]],
            "evidence": "Observed route and exact pool-to-model bindings.",
            "scopeDecision": "Preserve routing configuration; runtime failover requires separate proof.",
            "backends": [
                {"provider": provider, "model": model, "sourceBackendId": sid,
                 "priority": priority, "weight": weight}
                for provider, model, sid, priority, weight in zip(
                    ("provider-one", "destination-provider-two"), ("model-a", "model-b"),
                    members, priorities, (75, 25))]}]
        selected["catalogDigest"] = digest(semantic(models))
        value = initialize(source_inventory(SOURCE, azure), destination_inventory(TARGET, azure),
                           capabilities(cli()), models)
        return value, selected, azure

    def test_help_mentions_do_not_enable_removed_arguments(self):
        text = ("Command\n    az aigateway mcp update : --failure-mode is not supported.\n"
                "Arguments\n    --versions : Supported versions.\n"
                "    --name --tool-server-name -n [Required] : Name.\n"
                "Global Arguments\n    --subscription : Subscription.\n")
        self.assertEqual(exposed_options(text), ["--name", "--subscription", "--tool-server-name", "--versions"])

    def test_scoped_policy_graph_executes_with_gateway_selector_and_preserves_siblings(self):
        azure = Azure()
        azure.gateway = {"id": TARGET, "type": "Microsoft.ApiManagement/aigateways",
                         "properties": {"provisioningState": "Succeeded"}}
        sid = SOURCE + "/policies/policy"
        azure.collections[SOURCE + "/policies"] = {"value": [{"id": sid, "properties": {
            "value": '<policies><inbound><rate-limit calls="20" renewal-period="60"/></inbound></policies>'}}]}
        policies = [{"type": "contentSafety", "hateSeverity": "High"}]

        def runner(argv):
            if argv[2:4] == ["policy", "list"]:
                return copy.deepcopy(policies)
            if argv[2:4] == ["policy", "set"]:
                self.assertIn("--gateway-name", argv)
                self.assertNotIn("--name", argv)
                self.assertNotIn("--workspace-name", argv)
                self.assertEqual(json.loads(Path(argv[argv.index("--rate-counter-key") + 1][1:]).read_text()), ["Identity"])
                policies.append({"type": "requestRateLimit", "callsPerPeriod": 20, "periodSeconds": 60,
                                 "counterKey": ["identity"], "scope": "workspace"})
                return copy.deepcopy(policies)
            return azure(argv)

        source = source_inventory(SOURCE, runner)
        value = initialize(source, destination_inventory(TARGET, runner), capabilities(cli()))
        selected = self.selection()
        selected["policies"] = [self.binding(source, sid, scope="workspace",
            settings={"calls-per-period": 20, "period-seconds": 60, "rate-counter-key": ["Identity"]})]
        value = compile_selection(value, selected)
        value["plan-validation.json"] = validate_plan(value)
        self.assertEqual(value["plan-validation.json"]["status"], "valid", value["plan-validation.json"]["errors"])
        pdigest = value["plan-validation.json"]["planDigest"]
        for todo in value["todos.json"]["items"]:
            approve(value, todo["id"], pdigest)
            execute(value, todo["id"], pdigest, lambda _: None, runner, cli)
        self.assertEqual(policies[0], {"type": "contentSafety", "hateSeverity": "High"})
        self.assertEqual(value["todos.json"]["items"][-1]["status"], "resource-verified")
        self.assertNotEqual(value["context.json"]["completionStatus"], "complete")

    def test_multi_backend_selection_shares_models_and_requires_explicit_routing(self):
        value, selected, _ = graph_fixture()
        selected["models"][0]["explicitAlias"] = True
        selected["models"][0].pop("alias")
        selected["models"][0].pop("routingName")
        other = copy.deepcopy(selected["models"][0])
        other["name"] = "model-b"
        selected["models"].append(other)
        selected["aliases"] = [{"name": "production", "routingName": "customer/production",
            "backends": [{"provider": "provider-one", "model": "model-a", "priority": 0, "weight": 75},
                         {"provider": "provider-one", "model": "model-b", "priority": 1, "weight": 25}],
            "sourceIds": selected["models"][0]["sourceIds"], "evidence": "Selected backend pool.",
            "scopeDecision": "Reviewed priority/failover; no implicit retry or circuit-breaker equivalence."}]
        result = compile_selection(value, selected)
        checked = validate_plan(result)
        self.assertEqual(checked["status"], "valid", checked["errors"])
        aliases = [t for t in result["todos.json"]["items"] if t["capabilityId"] == "alias.create"]
        self.assertEqual(len(aliases), 1)
        self.assertEqual(aliases[0]["resourceDependencies"], ["model:model-a:provider-one", "model:model-b:provider-one"])
        self.assertEqual([b["weight"] for b in aliases[0]["arguments"]["backend-models"]], [75, 25])
        selected["aliases"][0]["backends"][0]["model"] = "unselected"
        with self.assertRaises(MigrationError):
            compile_selection(value, selected)

    def test_source_pool_executes_distinct_models_and_providers_with_weights_and_priorities(self):
        for priorities in ((0, 0), (0, 1)):
            with self.subTest(priorities=priorities):
                value, selected, azure = self.pool_selection(priorities)
                result = compile_selection(value, selected)
                result["plan-validation.json"] = validate_plan(result)
                self.assertEqual(result["plan-validation.json"]["status"], "valid",
                                 result["plan-validation.json"]["errors"])
                alias = next(t for t in result["todos.json"]["items"] if t["id"] == "alias:production")
                self.assertEqual(alias["resourceDependencies"],
                                 ["model:model-a:provider-one", "model:model-b:destination-provider-two"])
                expected = [{"resourceId": TARGET + "/workspaces/default/modelProviders/" + backend["provider"]
                             + "/models/" + backend["model"], "priority": backend["priority"],
                             "weight": backend["weight"]} for backend in selected["aliases"][0]["backends"]]
                self.assertEqual(alias["arguments"]["backend-models"], expected)
                pdigest = result["plan-validation.json"]["planDigest"]
                with patch.dict(os.environ, {"UPSTREAM_TOKEN": "TEST_RUNTIME_ONLY"}):
                    for todo in result["todos.json"]["items"]:
                        approve(result, todo["id"], pdigest)
                        execute(result, todo["id"], pdigest, lambda _: None, azure, cli)
                alias_id = TARGET + "/workspaces/default/aliases/production"
                self.assertEqual(azure.resources["model-alias"][alias_id]["properties"]["backendModels"], expected)
                self.assertEqual({model["properties"]["deployment"]["modelName"]
                                  for model in azure.resources["model"].values()}, {"Model/A", "Owner/Different"})
                report(result, fresh=True)
                self.assertEqual(result["context.json"]["completionStatus"], "incomplete")
                self.assertTrue(all(call[call.index("--method") + 1] == "get"
                                    for call in azure.calls if call[:2] == ["az", "rest"]))

    def test_source_pool_rejects_unproven_membership_settings_and_model_surfaces(self):
        for variant in ("missing-pool-binding", "missing-member-binding", "wrong-provider",
                        "changed-priority", "changed-weight", "zero-weight", "null-priority",
                        "omitted-weight", "duplicate-member", "missing-member", "nested-pool",
                        "cross-scope-route", "implicit-model-alias", "different-operations"):
            with self.subTest(variant=variant):
                value, selected, azure = self.pool_selection()
                alias = selected["aliases"][0]
                pool = azure.collections[SOURCE + "/backends"]["value"][-1]
                services = pool["properties"]["pool"]["services"]
                if variant == "missing-pool-binding":
                    alias.pop("sourcePoolId")
                elif variant == "missing-member-binding":
                    alias["backends"][0].pop("sourceBackendId")
                elif variant == "wrong-provider":
                    alias["backends"][0]["sourceBackendId"] = services[1]["id"]
                elif variant == "changed-priority":
                    alias["backends"][0]["priority"] = 1
                elif variant == "changed-weight":
                    alias["backends"][0]["weight"] = 50
                elif variant == "zero-weight":
                    services[0]["weight"] = 0
                elif variant == "null-priority":
                    services[0]["priority"] = None
                elif variant == "omitted-weight":
                    services[0].pop("weight")
                elif variant == "duplicate-member":
                    services[1] = copy.deepcopy(services[0])
                elif variant == "missing-member":
                    services.pop()
                elif variant == "nested-pool":
                    azure.collections[SOURCE + "/backends"]["value"][1]["properties"].update(
                        type="Pool", pool={"services": []})
                elif variant == "cross-scope-route":
                    azure.collections[SOURCE + "/apis"]["value"][0]["properties"]["backendId"] = (
                        SOURCE + "/workspaces/other/backends/model-pool")
                elif variant == "implicit-model-alias":
                    selected["models"][0].update(explicitAlias=False, alias="extra-route",
                                                 routingName="customer/extra")
                else:
                    selected["models"][1]["endpoints"].append("/openai/v1/responses")
                    value["model-catalog.json"]["providers"][1]["models"][0]["endpoints"].append("/responses")
                    selected["catalogDigest"] = digest(semantic(value["model-catalog.json"]))
                value["source-inventory.json"] = source_inventory(SOURCE, azure)
                azure.calls.clear()
                with self.assertRaises(MigrationError):
                    compile_selection(value, selected)
                self.assertEqual(azure.calls, [])

    def test_model_routing_rejects_source_failure_behaviors_even_without_pool_bindings(self):
        for variant in ("circuit-breaker", "retry", "error-handler", "alias-only-error-handler"):
            with self.subTest(variant=variant):
                value, selected, azure = graph_fixture()
                api = SOURCE + "/apis/inference"
                policy = api + "/policies/policy"
                if variant == "circuit-breaker":
                    azure.collections[SOURCE + "/backends"]["value"][0]["properties"]["circuitBreaker"] = {
                        "rules": [{"failureCondition": {"count": 3, "interval": "PT1M",
                                   "statusCodeRanges": [{"min": 429, "max": 429}]},
                                   "tripDuration": "PT1M", "acceptRetryAfter": True}]}
                else:
                    content = ('<backend><retry count="3" interval="1" condition="true">'
                               '<forward-request/></retry></backend>' if variant == "retry" else
                               '<on-error><set-backend-service backend-id="upstream"/></on-error>')
                    azure.collections[api + "/policies"] = {"value": [{"id": policy,
                        "properties": {"value": "<policies>" + content + "</policies>"}}]}
                    if variant == "alias-only-error-handler":
                        model = selected["models"][0]
                        model["explicitAlias"] = True
                        selected["aliases"] = [{"name": model.pop("alias"), "routingName": model.pop("routingName"),
                            "sourceIds": [policy], "evidence": "Not proof of equivalent error handling.",
                            "scopeDecision": "Unsupported behavior must remain blocked.", "backends": [{
                                "provider": "provider-one", "model": "model-a", "priority": 0, "weight": 100}]}]
                    else:
                        selected["models"][0]["sourceIds"].append(policy)
                value["source-inventory.json"] = source_inventory(SOURCE, azure)
                azure.calls.clear()
                with self.assertRaisesRegex(MigrationError, "circuit-breaker|retries|error handlers"):
                    compile_selection(value, selected)
                self.assertEqual(azure.calls, [])

    def test_source_pool_blocks_pool_and_member_circuit_breakers(self):
        for index in (0, -1):
            with self.subTest(backend=index):
                value, selected, azure = self.pool_selection()
                azure.collections[SOURCE + "/backends"]["value"][index]["properties"]["circuitBreaker"] = {
                    "rules": [{"failureCondition": {"count": 1}, "tripDuration": "PT1M"}]}
                value["source-inventory.json"] = source_inventory(SOURCE, azure)
                with self.assertRaisesRegex(MigrationError, "circuit-breaker"):
                    compile_selection(value, selected)

    def test_source_pool_cannot_be_claimed_by_a_model_without_a_bound_alias(self):
        value, selected, azure = graph_fixture()
        pool = SOURCE + "/backends/unrouted-pool"
        azure.collections[SOURCE + "/backends"]["value"].append({
            "id": pool, "properties": {"type": "Pool", "pool": {"services": [
                {"id": SOURCE + "/backends/upstream", "priority": 0, "weight": 100}]}}})
        value["source-inventory.json"] = source_inventory(SOURCE, azure)
        selected["models"][0]["sourceIds"].append(pool)
        with self.assertRaisesRegex(MigrationError, "pool.*alias"):
            compile_selection(value, selected)

    def test_pool_backend_references_preserve_collection_like_service_and_workspace_names(self):
        for root in (SOURCE.replace("/service/source", "/service/apis"),
                     SOURCE + "/workspaces/products", SOURCE + "/workspaces/apis"):
            with self.subTest(root=root):
                item = inventory_item({
                    "id": root + "/apis/inference/policies/policy", "properties": {
                        "value": '<policies><inbound><set-backend-service backend-id="model-pool"/>'
                                 '</inbound></policies>'}}, root + "/apis/inference", "api-policies")
                self.assertEqual(backend_ids(item), {(root + "/backends/model-pool").lower()})

    def test_source_pool_requires_explicit_alias_replacement_and_preserves_siblings(self):
        value, selected, azure = self.pool_selection()
        azure.gateway = {"id": TARGET, "type": "Microsoft.ApiManagement/aigateways",
                         "location": "eastus2",
                         "properties": {"provisioningState": "Succeeded"}}
        root = TARGET + "/workspaces/default/aliases/"
        existing = {"id": root + "production", "name": "production", "properties": {
            "aliasName": "old-route", "backendModels": [], "policies": [{"type": "preserve"}]}}
        unrelated = {"id": root + "unrelated", "name": "unrelated",
                     "properties": {"aliasName": "unrelated-route", "backendModels": []}}
        azure.resources["model-alias"] = {existing["id"]: copy.deepcopy(existing),
                                         unrelated["id"]: copy.deepcopy(unrelated)}
        value["destination-inventory.json"] = destination_inventory(TARGET, azure)
        with self.assertRaises(MigrationError):
            compile_selection(value, selected)
        selected["aliases"][0]["updateExisting"] = True
        result = compile_selection(value, selected)
        result["plan-validation.json"] = validate_plan(result)
        self.assertEqual(result["plan-validation.json"]["status"], "valid",
                         result["plan-validation.json"]["errors"])
        alias = next(t for t in result["todos.json"]["items"] if t["id"] == "alias:production")
        self.assertEqual(alias["capabilityId"], "alias.update")
        tampered = copy.deepcopy(result)
        next(t for t in tampered["todos.json"]["items"] if t["id"] == "alias:production")[
            "arguments"]["backend-models"][0]["priority"] = 10
        self.assertEqual(validate_plan(tampered)["status"], "invalid")
        pdigest = result["plan-validation.json"]["planDigest"]
        with patch.dict(os.environ, {"UPSTREAM_TOKEN": "TEST_RUNTIME_ONLY"}):
            for todo in result["todos.json"]["items"]:
                approve(result, todo["id"], pdigest)
                execute(result, todo["id"], pdigest, lambda _: None, azure, cli)
        self.assertEqual(azure.resources["model-alias"][existing["id"]]["properties"]["policies"],
                         existing["properties"]["policies"])
        self.assertEqual(azure.resources["model-alias"][unrelated["id"]], unrelated)

    def test_policy_lists_cost_numbers_and_ip_ranges_are_validated(self):
        args = {"cost-limit": 12.5, "cost-period": "month", "cost-counter-key": ["Identity", "IPAddress"]}
        self.assertEqual(policy_state(args)[0], {"type": "costLimit", "id": "default", "amount": 12.5,
                                               "period": "month", "counterKey": ["identity", "ipAddress"]})
        for invalid in (float("nan"), float("inf"), -1, True):
            with self.assertRaises(MigrationError):
                policy_state({**args, "cost-limit": invalid})
        with self.assertRaises(MigrationError):
            policy_state({**args, "cost-counter-key": ["All"]})
        with self.assertRaises(MigrationError):
            policy_state({"ip-filter-mode": "allow", "ip-addresses": ["192.0.2.4/24"]}, workspace=True)
        self.assertEqual(policy_state({"ip-filter-mode": "deny", "ip-addresses": ["192.0.2.0/24"]},
                                     workspace=True)[0]["cidrRanges"], ["192.0.2.0/24"])
        cap = next(c for c in capabilities(cli())["capabilities"] if c["id"] == "model.policy")
        todo = {"target": {"subscription": "sub", "resourceGroup": "rg", "gateway": "target",
                           "name": "model", "provider": "provider"}, "arguments": args}
        with tempfile.TemporaryDirectory() as directory:
            argv = mutation_argv({"capability-contract.json": {"capabilities": [cap]}},
                                 {**todo, "capabilityId": cap["id"]}, directory)
            self.assertEqual(argv[argv.index("--cost-limit") + 1], "12.5")

    def test_new_target_selectors_are_not_confused_with_gateway_names(self):
        todo = {"target": {"subscription": "sub", "resourceGroup": "rg", "gateway": "gateway",
                           "name": "connection", "provider": None}}
        options = selectors(todo, {"command": ["network", "private-endpoint-connection", "approve"]})
        self.assertEqual(options[options.index("--gateway-name") + 1], "gateway")
        self.assertEqual(options[options.index("--name") + 1], "connection")
        options = selectors(todo, {"command": ["policy", "set"]})
        self.assertIn("--gateway-name", options)
        self.assertNotIn("--name", options)

    def test_telemetry_requires_runtime_credentials_and_explicit_payload_decision(self):
        azure = Azure()
        sid = SOURCE + "/loggers/insights"
        azure.collections[SOURCE + "/loggers"] = {"value": [{"id": sid, "properties": {
            "loggerType": "applicationInsights", "credentials": {"instrumentationKey": "SOURCE_SECRET"}}}]}
        source = source_inventory(SOURCE, azure)
        value = initialize(source, destination_inventory(TARGET, azure), capabilities(cli()))
        selected = self.selection()
        selected["gateway"] = {"location": "eastus2"}
        entry = self.binding(source, sid, name="insights", settings={"kind": "ApplicationInsights",
            "application-insights": {"connectionString": {"$runtimeSecret": "TELEMETRY_CONNECTION"}},
            "payload-capture": False})
        selected["telemetry"] = [entry]
        result = compile_selection(value, selected)
        checked = validate_plan(result)
        self.assertEqual(checked["status"], "valid", checked["errors"])
        self.assertNotIn("SOURCE_SECRET", json.dumps(result))
        self.assertFalse(result["todos.json"]["items"][-1]["desiredState"]["properties"]["payloadCapture"])
        entry["settings"]["application-insights"]["connectionString"] = "literal"
        with self.assertRaises(MigrationError):
            compile_selection(value, selected)
        with self.assertRaises(MigrationError):
            reviewed_arguments("telemetry.create", {"kind": "OpenTelemetry", "payload-capture": False})

    def test_key_renames_and_expiration_without_timezone_are_rejected(self):
        with self.assertRaises(MigrationError):
            reviewed_arguments("key.update", {"display-name": "renamed"})
        with self.assertRaises(MigrationError):
            reviewed_arguments("key.update", {"expiration-date": "2026-12-01T00:00:00"})
        reviewed_arguments("key.update", {"state": "suspended", "expiration-date": "2026-12-01T00:00:00Z"})

    def test_network_and_connection_execution_preserves_peer_and_orders_private_access(self):
        azure = Azure()
        azure.source["properties"].update(publicNetworkAccess="Enabled", privateEndpointConnections=[],
                                          hostname="source.example")
        azure.gateway = {"id": TARGET, "type": "Microsoft.ApiManagement/aigateways",
                         "properties": {"provisioningState": "Succeeded"}}
        network = {"publicNetworkAccess": "Enabled", "virtualNetworkType": "None",
                   "virtualNetworkConfiguration": None, "provisioningState": "Succeeded"}
        peer = "/subscriptions/sub/resourceGroups/network/providers/Microsoft.Network/privateEndpoints/selected"
        connection = {"id": TARGET + "/privateEndpointConnections/pending", "properties": {
            "privateEndpoint": {"id": peer}, "privateLinkServiceConnectionState": {"status": "Pending"},
            "provisioningState": "Succeeded"}}

        def runner(argv):
            command = argv[2:]
            if command[:3] == ["network", "private-endpoint-connection", "list"]:
                return [copy.deepcopy(connection)]
            if command[:3] == ["network", "private-endpoint-connection", "show"]:
                self.assertEqual(argv[argv.index("--name") + 1], "pending")
                return copy.deepcopy(connection)
            if command[:3] == ["network", "private-endpoint-connection", "approve"]:
                connection["properties"]["privateLinkServiceConnectionState"] = {
                    "status": "Approved", "description": argv[argv.index("--description") + 1]}
                return copy.deepcopy(connection)
            if command[:2] == ["network", "show"]:
                return copy.deepcopy(network)
            if command[:2] == ["network", "update"]:
                self.assertEqual(connection["properties"]["privateLinkServiceConnectionState"]["status"], "Approved")
                network["publicNetworkAccess"] = argv[argv.index("--public-network-access") + 1]
                return copy.deepcopy(network)
            return azure(argv)

        source = source_inventory(SOURCE, runner)
        value = initialize(source, destination_inventory(TARGET, runner), capabilities(cli()))
        selected = self.selection()
        entry = self.binding(source, SOURCE, settings={"public-network-access": "Disabled"},
                             verificationAccess="Selected private link is independently verified.")
        entry["behaviorIds"] = [b["id"] for b in source["behaviors"] if b.get("property") == "publicNetworkAccess"]
        selected["network"] = entry
        entry = self.binding(source, SOURCE, name="pending", peerId=peer, description="Selected migration connection.")
        entry["behaviorIds"] = [b["id"] for b in source["behaviors"] if b.get("property") == "privateEndpointConnections"]
        selected["connections"] = [entry]
        value = compile_selection(value, selected)
        value["plan-validation.json"] = validate_plan(value)
        self.assertEqual(value["plan-validation.json"]["status"], "valid", value["plan-validation.json"]["errors"])
        self.assertIn("connection:pending", next(t for t in value["todos.json"]["items"] if
                                                t["id"] == "network:default")["resourceDependencies"])
        pdigest = value["plan-validation.json"]["planDigest"]
        for tid in ("gateway:target", "connection:pending", "network:default"):
            approve(value, tid, pdigest)
            execute(value, tid, pdigest, lambda _: None, runner, cli)
        self.assertEqual(network["publicNetworkAccess"], "Disabled")
        self.assertEqual(connection["properties"]["privateEndpoint"]["id"], peer)
        self.assertTrue(any(m["classification"] == "cannot-import" and any(
            b.get("property") == "hostname" for b in source["behaviors"] if b["id"] in m["behaviorIds"])
                            for m in value["mapping.json"]["items"]))

    def test_exporter_execution_keeps_runtime_secret_out_of_checkpoint_and_recovers_graph(self):
        azure = Azure()
        sid = SOURCE + "/loggers/insights"
        azure.collections[SOURCE + "/loggers"] = {"value": [{"id": sid, "properties": {"loggerType": "applicationInsights"}}]}
        exporters = []

        def runner(argv):
            if argv[2:4] == ["telemetry-exporter", "list"]:
                return copy.deepcopy(exporters)
            if argv[2:4] == ["telemetry-exporter", "show"]:
                return copy.deepcopy(exporters[0])
            if argv[2:4] == ["telemetry-exporter", "create"]:
                settings = json.loads(Path(argv[argv.index("--application-insights") + 1][1:]).read_text())
                self.assertEqual(settings["connectionString"], "RUNTIME_TELEMETRY_TEST")
                self.assertNotIn("RUNTIME_TELEMETRY_TEST", argv)
                exporters.append({"id": TARGET + "/workspaces/default/telemetryExporters/insights",
                                  "properties": {"kind": "ApplicationInsights", "applicationInsights": settings,
                                                 "payloadCapture": False}})
                return copy.deepcopy(exporters[0])
            return azure(argv)

        source = source_inventory(SOURCE, runner)
        value = initialize(source, destination_inventory(TARGET, runner), capabilities(cli()))
        selected = self.selection()
        selected["gateway"] = {"location": "eastus2"}
        selected["telemetry"] = [self.binding(source, sid, name="insights", settings={
            "kind": "ApplicationInsights", "application-insights": {
                "connectionString": {"$runtimeSecret": "TELEMETRY_CONNECTION"}}, "payload-capture": False})]
        value = compile_selection(value, selected)
        value["plan-validation.json"] = validate_plan(value)
        self.assertEqual(value["plan-validation.json"]["status"], "valid", value["plan-validation.json"]["errors"])
        pdigest = value["plan-validation.json"]["planDigest"]
        with patch.dict(os.environ, {"TELEMETRY_CONNECTION": "RUNTIME_TELEMETRY_TEST"}):
            for tid in ("gateway:target", "telemetry:insights"):
                approve(value, tid, pdigest)
                execute(value, tid, pdigest, lambda _: None, runner, cli)
        checked = validate_plan(value)
        self.assertEqual(checked["status"], "valid", checked["errors"])
        self.assertNotIn("RUNTIME_TELEMETRY_TEST", json.dumps(value))

    def test_incomplete_new_collections_and_wrong_child_ids_do_not_establish_absence(self):
        azure = Azure()
        azure.gateway = {"id": TARGET, "properties": {"provisioningState": "Succeeded"}}

        def runner(argv):
            if argv[2:4] == ["telemetry-exporter", "list"]:
                return [{"id": TARGET + "/apiKeys/not-an-exporter"}]
            return azure(argv)

        snapshot = destination_inventory(TARGET, runner)
        self.assertIn({"domain": "telemetry-exporter", "code": "inconclusive"}, snapshot["errors"])
        with self.assertRaises(MigrationError):
            from selection import current_resource
            current_resource(snapshot, "telemetry-exporter", "new")

    def test_explicit_key_lifecycle_update_does_not_rename_or_retrieve_secrets(self):
        azure = GraphAzure()
        azure.gateway = {"id": TARGET, "type": "Microsoft.ApiManagement/aigateways",
                         "properties": {"provisioningState": "Succeeded"}}
        rid = TARGET + "/apiKeys/existing"
        azure.resources["api-key"][rid] = {"id": rid, "properties": {"displayName": "Existing", "state": "active"}}
        source = source_inventory(SOURCE, azure)
        value = initialize(source, destination_inventory(TARGET, azure), capabilities(cli()))
        selected = self.selection()
        selected["keys"] = [{"name": "existing", "displayName": "Existing", "state": "suspended",
            "expirationDate": "2027-01-01T00:00:00Z", "updateExisting": True, "sourceIds": [SOURCE],
            "accessDecision": "Suspend this selected gateway-wide key explicitly."}]
        value = compile_selection(value, selected)
        value["plan-validation.json"] = validate_plan(value)
        self.assertEqual(value["plan-validation.json"]["status"], "valid", value["plan-validation.json"]["errors"])
        pdigest = value["plan-validation.json"]["planDigest"]
        for tid in ("gateway:target", "key:existing"):
            approve(value, tid, pdigest)
            execute(value, tid, pdigest, lambda _: None, azure, cli)
        self.assertEqual(azure.resources["api-key"][rid]["properties"]["state"], "suspended")
        updates = [call for call in azure.calls if call[2:4] == ["api-key", "update"]]
        self.assertEqual(len(updates), 1)
        self.assertNotIn("--display-name", updates[0])
        self.assertFalse(any("list-secrets" in call or "regenerate" in call for call in azure.calls))

    def test_mcp_versions_only_update_preserves_endpoints_without_secret_reads(self):
        azure = GraphAzure()
        azure.gateway = {"id": TARGET, "type": "Microsoft.ApiManagement/aigateways",
                         "properties": {"provisioningState": "Succeeded"}}
        sid = SOURCE + "/apis/tools"
        endpoint = {"id": "source-1", "namespace": "remote", "kind": "mcp",
                    "mcp": {"url": "https://tools.example/mcp", "transport": "streamableHttp"},
                    "credentials": {"type": "none"}}
        azure.collections[SOURCE + "/apis"] = {"value": [{"id": sid, "properties": {
            "type": "mcp", "serviceUrl": "https://tools.example",
            "mcpProperties": {"endpoints": {"message": {"uriTemplate": "/mcp"}}}}}]}
        rid = TARGET + "/workspaces/default/toolServers/tools"
        azure.resources["mcp"][rid] = {"id": rid, "properties": {"endpoints": [endpoint], "versions": ["2025-03-26"]}}
        source = source_inventory(SOURCE, azure)
        value = initialize(source, destination_inventory(TARGET, azure), capabilities(cli()))
        selected = self.selection()
        selected["mcp"] = [{"name": "tools", "endpoints": [endpoint], "versions": ["2025-06-18"],
            "sourceIds": [sid], "evidence": "Selected exact observed remote MCP endpoint and protocol.",
            "accessDecision": "Explicit destination key admission.", "reuseExisting": True}]
        selected["keys"] = [{"name": "app", "displayName": "Application", "sourceIds": [sid],
                             "accessDecision": "New gateway-wide metadata, not copied client secrets."}]
        value = compile_selection(value, selected)
        value["plan-validation.json"] = validate_plan(value)
        self.assertEqual(value["plan-validation.json"]["status"], "valid", value["plan-validation.json"]["errors"])
        todo = next(t for t in value["todos.json"]["items"] if t["id"] == "mcp:tools")
        self.assertEqual(todo["arguments"], {"versions": ["2025-06-18"]})
        pdigest = value["plan-validation.json"]["planDigest"]
        for tid in ("gateway:target", "mcp:tools"):
            approve(value, tid, pdigest)
            execute(value, tid, pdigest, lambda _: None, azure, cli)
        self.assertEqual(azure.resources["mcp"][rid]["properties"]["endpoints"], [endpoint])
        self.assertEqual(azure.resources["mcp"][rid]["properties"]["versions"], ["2025-06-18"])
        updates = [call for call in azure.calls if call[2:4] == ["mcp", "update"]]
        self.assertNotIn("--endpoints", updates[0])

    def test_new_cost_governance_retains_original_gateway_behavior_owner(self):
        azure = Azure()
        azure.gateway = {"id": TARGET, "type": "Microsoft.ApiManagement/aigateways",
                         "properties": {"provisioningState": "Succeeded"}}
        source = source_inventory(SOURCE, azure)
        value = initialize(source, destination_inventory(TARGET, azure), capabilities(cli()))
        selected = self.selection()
        selected["policies"] = [self.binding(source, SOURCE, scope="workspace", newGovernance=True,
            settings={"cost-limit": 2.5, "cost-period": "day", "cost-counter-key": ["Identity"]})]
        result = compile_selection(value, selected)
        checked = validate_plan(result)
        self.assertEqual(checked["status"], "valid", checked["errors"])
        owner = next(m for m in result["mapping.json"]["items"] if "policy:default" in m.get("todoIds", []))
        self.assertEqual(set(owner["todoIds"]), {"gateway:target", "policy:default"})
        selected["policies"][0].pop("newGovernance")
        with self.assertRaises(MigrationError):
            compile_selection(value, selected)

    def test_opaque_policy_translation_requires_digest_and_cannot_enable_arbitrary_xml(self):
        azure = Azure()
        azure.gateway = {"id": TARGET, "type": "Microsoft.ApiManagement/aigateways",
                         "properties": {"provisioningState": "Succeeded"}}
        sid = SOURCE + "/policies/policy"
        azure.collections[SOURCE + "/policies"] = {"value": [{"id": sid, "properties": {
            "value": '<policies><inbound><rate-limit-by-key calls="10" renewal-period="60" counter-key="opaque"/></inbound></policies>'}}]}
        source = source_inventory(SOURCE, azure)
        value = initialize(source, destination_inventory(TARGET, azure), capabilities(cli()))
        selected = self.selection()
        entry = self.binding(source, sid, scope="workspace",
                             settings={"calls-per-period": 10, "period-seconds": 60, "rate-counter-key": ["Identity"]})
        selected["policies"] = [entry]
        with self.assertRaises(MigrationError):
            compile_selection(value, selected)
        entry["translationDigest"] = digest({key: entry[key] for key in ("sourceIds", "behaviorIds", "settings", "scopeDecision")})
        result = compile_selection(value, selected)
        checked = validate_plan(result)
        self.assertEqual(checked["status"], "valid", checked["errors"])
        entry["settings"]["calls-per-period"] = 11
        with self.assertRaises(MigrationError):
            compile_selection(value, selected)
        source["items"][-1]["policyShape"][-1]["statement"] = "set-header"
        source["behaviors"][-1]["statement"] = "set-header"
        value["source-inventory.json"] = source
        entry["settings"]["calls-per-period"] = 10
        with self.assertRaises(MigrationError):
            compile_selection(value, selected)


if __name__ == "__main__":
    unittest.main()
