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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import MigrationError, cli_failure_code, digest, semantic
from execution import approve, execute, initialize, record_behavior, report
from gateway import capabilities, destination_inventory
from inventory import source_inventory
from model_inventory import NoRedirect, collect_models, import_models, validate_catalog
from planning import validate_plan
from selection import compile_selection, removal_proposals, validate_selection
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
                    "display-name": "displayName", "endpoints": "endpoints"}
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


if __name__ == "__main__":
    unittest.main()
