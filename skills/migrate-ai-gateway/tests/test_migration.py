"""Offline contract tests; no login, credentials, or Azure writes."""

import copy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from core import GATEWAY_TYPE, MigrationError, State, clean, digest, read_json, resource_id, semantic, validate_schema
from execution import (
    approve, execute, initialize, mutation_argv, record_behavior, refresh, report, verify_final_resources,
)
import migration
from gateway import capabilities, catalog, destination_inventory, gateway_commands
from inventory import Reader, apply_export, export_digest, policy_shape, source_inventory
from planning import gap_id, initial_mapping, plan_digest, validate_plan
from planning import contains_secret, meaningful_assertion


SOURCE = "/subscriptions/sub/resourceGroups/source-rg/providers/Microsoft.ApiManagement/service/source"
TARGET = "/subscriptions/sub/resourceGroups/target-rg/providers/Microsoft.ApiManagement/aigateways/target"


def cli():
    commands = {}
    for cap in catalog()["capabilities"]:
        commands[" ".join(cap["command"])] = ["--" + option for option in cap["options"]]
        commands.setdefault(" ".join(cap["read"]), [])
    for options in commands.values():
        options.extend(["--subscription", "--resource-group", "--name", "--gateway-name", "--provider-name"])
    commands["list"] = ["--subscription", "--resource-group"]
    commands["model-provider sync"] = ["--subscription", "--resource-group", "--name",
                                       "--gateway-name", "--dry-run"]
    return {"schemaVersion": "1.0", "producer": "skill-local", "toolVersion": "1.0.0",
            "extension": {"extensionName": "aigateway", "extensionVersion": "test",
                          "apiVersion": "2025-09-01-preview"},
            "resourceCommands": {"aigateways": list(commands)},
            "commands": commands, "fingerprint": digest(commands)}


class Azure:
    def __init__(self, sku="BasicV2"):
        self.source = {"id": SOURCE, "name": "source", "sku": {"name": sku},
                       "properties": {"provisioningState": "Succeeded"}}
        self.gateway = None
        self.calls = []
        self.fail_mutation = False
        self.unknown_success = False
        self.collections = {}

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[:3] == ["az", "cloud", "show"]:
            return "https://management.azure.com/"
        if argv[:2] == ["az", "rest"]:
            assert argv[argv.index("--method") + 1] == "get"
            path = urlsplit(argv[argv.index("--url") + 1]).path
            if path == SOURCE:
                return copy.deepcopy(self.source)
            response = self.collections.get(path, {"value": []})
            if path not in self.collections:
                for collection in self.collections.values():
                    if isinstance(collection, dict) and isinstance(collection.get("value"), list):
                        match = next((item for item in collection["value"] if item.get("id") == path), None)
                        if match is not None:
                            response = {**match, "properties": match.get("properties", {})}
                            break
            if isinstance(response, Exception):
                raise response
            return copy.deepcopy(response)
        command = argv[2:]
        if command[0] == "list":
            return [copy.deepcopy(self.gateway)] if self.gateway else []
        if command[0] == "show":
            if self.gateway is None:
                raise MigrationError("Missing gateway.")
            return copy.deepcopy(self.gateway)
        if command[0] == "create":
            if self.fail_mutation:
                raise MigrationError("Unknown outcome.")
            self.gateway = {"id": TARGET, "type": GATEWAY_TYPE, "name": "target", "location": "eastus2",
                            "sku": {"name": "Consumption"},
                            "properties": {"provisioningState": "Succeeded"}}
            if "--subnet" in argv:
                self.gateway["properties"]["backend"] = {
                    "subnet": {"id": argv[argv.index("--subnet") + 1]}}
            if self.unknown_success:
                raise MigrationError("Unknown outcome after successful server response.")
            return copy.deepcopy(self.gateway)
        if command[1] == "list":
            return []
        if command[0] in ("identity", "network"):
            if command[:3] == ["network", "private-endpoint-connection", "list"]:
                return []
            return {}
        raise AssertionError(argv)


def bundle(azure=None):
    azure = azure or Azure()
    source = source_inventory(SOURCE, azure)
    destination = destination_inventory(TARGET, azure)
    value = initialize(source, destination, capabilities(cli()))
    return value, azure


def ready_bundle(azure=None):
    value, azure = bundle(azure)
    mapping = value["mapping.json"]["items"][0]
    mapping.update(classification="ready", capabilityId="gateway.create",
                   semanticDecision="Operator confirmed a new gateway and accepted its exact configuration.",
                   question=None)
    todo = {
        "id": "create-gateway", "mappingIds": [mapping["id"]],
        "capabilityId": "gateway.create",
        "target": {"subscription": "sub", "resourceGroup": "target-rg", "gateway": "target",
                   "workspace": "default", "name": None, "provider": None},
        "arguments": {"location": "eastus2"},
        "desiredState": {"type": GATEWAY_TYPE, "location": "eastus2",
                         "properties": {"provisioningState": "Succeeded"}},
        "dependsOn": [], "precondition": {"exists": False, "stateDigest": None},
        "approval": {"status": "pending", "planDigest": None, "approvedAt": None},
        "status": "pending", "attempts": [],
        "behaviorResults": {bid: {"status": "pending", "method": "control-plane",
                                  "evidenceDigest": None, "recordedAt": None}
                            for bid in mapping["behaviorIds"]},
    }
    value["todos.json"]["items"].append(todo)
    value["plan-validation.json"] = validate_plan(value)
    return value, azure


class CliContractTests(unittest.TestCase):
    def test_new_rp_dispatch_is_inspected_without_executing_extension_code(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            path = package / "_rp.py"
            path.write_text(
                'raise RuntimeError("must not execute")\n'
                'SUPPORTED_NEW_COMMANDS = {"aigateway create", "aigateway show"}\n'
                'CHILD_READS = {"aigateway model show"}\n'
                'SUPPORTED_NEW_COMMANDS.update(CHILD_READS)\n'
                'CHILD_WRITES = {"aigateway mcp create"}\n'
                'SUPPORTED_NEW_COMMANDS.update(CHILD_WRITES)\n')
            self.assertEqual(gateway_commands(package),
                             ["create", "mcp create", "model show", "show"])
            for content in ('SUPPORTED_NEW_COMMANDS = discover_commands()\n',
                            'SUPPORTED_NEW_COMMANDS = {"aigateway create"}\n'
                            'SUPPORTED_NEW_COMMANDS.update(discover_commands())\n'):
                path.write_text(content)
                with self.assertRaises(MigrationError):
                    gateway_commands(package)
            path.unlink()
            with self.assertRaises(MigrationError):
                gateway_commands(package)

    def test_help_does_not_authorize_legacy_only_or_missing_selector_commands(self):
        for change in (
                lambda value: value.pop("resourceCommands"),
                lambda value: value["resourceCommands"]["aigateways"].remove("model create"),
                lambda value: value["commands"]["model create"].remove("--gateway-name")):
            inspected = cli()
            change(inspected)
            contract = capabilities(inspected)
            cap = next(cap for cap in contract["capabilities"] if cap["id"] == "model.create")
            self.assertEqual(cap["support"], "unavailable")
        inspected = cli()
        inspected["resourceCommands"]["aigateways"].remove("network update")
        contract = capabilities(inspected)
        self.assertEqual(next(cap for cap in contract["capabilities"]
                              if cap["id"] == "network.update")["support"], "unavailable")

    def test_b14_model_lifecycle_is_available_only_with_new_rp_dispatch(self):
        inspected = cli()
        inspected["extension"]["extensionVersion"] = "1.0.0b14"
        inspected["resourceCommands"]["aigateways"].remove("network update")
        for release, supported in (("1.0.0b14", True), ("1.0.0b12", False)):
            inspected["extension"]["extensionVersion"] = release
            if not supported:
                for command in ("model create", "model update", "model policy set"):
                    inspected["resourceCommands"]["aigateways"].remove(command)
            entries = {cap["id"]: cap for cap in capabilities(inspected)["capabilities"]}
            for cid in ("model.create", "model.update", "model.policy"):
                self.assertEqual(entries[cid]["support"], "conditional" if supported else "unavailable")
            self.assertEqual(entries["network.update"]["support"], "unavailable")

    def test_source_and_destination_resource_families_are_not_interchangeable(self):
        for identifier, family in ((SOURCE, "aigateways"), (TARGET, "service")):
            with self.assertRaises(MigrationError):
                resource_id(identifier, family)
        with self.assertRaises(MigrationError):
            destination_inventory(TARGET.replace("/aigateways/", "/service/"), Azure())
        with self.assertRaises(MigrationError):
            source_inventory(SOURCE.replace("/service/", "/aigateways/"), Azure())


class InventoryTests(unittest.TestCase):
    def test_policy_reads_negotiate_json_while_requesting_raw_xml_values(self):
        azure = Azure()
        policy = SOURCE + "/policies/policy"
        azure.collections[SOURCE + "/policies"] = {"value": [{"id": policy}]}
        azure.collections[policy] = {"id": policy, "properties": {
            "value": "<policies><inbound><base/></inbound></policies>"}}

        def runner(argv):
            if "--url" in argv and "/policies/policy?" in argv[argv.index("--url") + 1]:
                if "--headers" not in argv or "Accept=application/json" not in argv:
                    return "<policies/>"
                self.assertIn("format=rawxml", argv[argv.index("--url") + 1])
            return azure(argv)

        source = source_inventory(SOURCE, runner)
        coverage = next(c for c in source["coverage"] if c["domain"] == "policies")
        self.assertTrue(coverage["establishesCompleteness"])
        self.assertTrue(any(item["id"] == policy for item in source["items"]))

    def test_relative_revision_records_are_normalized_only_within_the_exact_api(self):
        for scope in (SOURCE, SOURCE + "/workspaces/team"):
            api = scope + "/apis/chat"
            relative = api[len(SOURCE):] + ";rev=1"
            record = {"id": relative + "/revisions/chat;rev=1", "apiId": relative,
                      "apiRevision": "1", "isCurrent": True}
            azure = Azure()
            azure.collections[api + "/revisions"] = {"value": [record]}
            with self.subTest(scope=scope):
                result = Reader(SOURCE, azure).collection(api + "/revisions")
                self.assertTrue(result[0]["id"].startswith(api + "/revisions/"))
                self.assertEqual(result[0]["observedId"], record["id"])
                self.assertEqual(result[0]["apiId"], api + ";rev=1")
                self.assertEqual(result[0]["observedApiId"], relative)
            absolute = {**record, "id": api + "/revisions/1", "apiId": api + ";rev=1"}
            azure.collections[api + "/revisions"] = {"value": [absolute]}
            with self.subTest(scope=scope, absolute=True):
                result = Reader(SOURCE, azure).collection(api + "/revisions")
                self.assertEqual(result[0]["id"], api + "/revisions/observed-" + digest("1")[7:])
                self.assertEqual(result[0]["observedId"], absolute["id"])
            for change in (
                    {"id": "/apis/other;rev=1/revisions/other;rev=1"},
                    {"id": SOURCE + "/apis/other/revisions/1"},
                    {"id": relative + "/revisions/chat;rev=2"},
                    {"apiId": "/apis/other;rev=1"},
                    {"apiId": TARGET + "/apis/chat;rev=1"},
                    {"apiRevision": "1/../../other"},
                    {"apiId": None},
                    {"id": relative.replace("chat", "%63hat") + "/revisions/chat;rev=1"}):
                with self.subTest(scope=scope, change=change):
                    azure.collections[api + "/revisions"] = {"value": [{**record, **change}]}
                    with self.assertRaises(MigrationError):
                        Reader(SOURCE, azure).collection(api + "/revisions")
            azure.collections[scope + "/apis"] = {"value": [{"id": relative}]}
            with self.assertRaises(MigrationError):
                Reader(SOURCE, azure).collection(scope + "/apis")

    def test_matching_current_revision_reuses_the_verified_api_configuration(self):
        azure = Azure()
        api = SOURCE + "/apis/chat"
        relative = "/apis/chat;rev=1"
        azure.collections[SOURCE + "/apis"] = {"value": [{"id": api, "properties": {
            "type": "http", "apiRevision": "1", "isCurrent": True}}]}
        azure.collections[api + "/revisions"] = {"value": [{
            "id": relative + "/revisions/chat;rev=1", "apiId": relative,
            "apiRevision": "1", "isCurrent": True}]}
        source = source_inventory(SOURCE, azure)
        coverage = next(c for c in source["coverage"]
                        if c["domain"] == "api-revision-configurations")
        self.assertTrue(coverage["establishesCompleteness"])
        self.assertEqual(len([i for i in source["items"] if i["domain"] == "apis"]), 1)
        self.assertFalse(any(api + ";rev=1?" in call[call.index("--url") + 1]
                             for call in azure.calls if "--url" in call))
        azure.collections[api + "/revisions"]["value"][0]["isCurrent"] = False
        source = source_inventory(SOURCE, azure)
        self.assertFalse(next(c for c in source["coverage"]
                              if c["domain"] == "api-revision-configurations")["establishesCompleteness"])

    def test_inventory_is_independent_of_destination_catalog(self):
        with patch("gateway.catalog", side_effect=AssertionError("Destination contract unavailable")):
            source = source_inventory(SOURCE, Azure())
        validate_schema(source, "source-inventory")
        self.assertNotIn("capabilityId", json.dumps(source))

    def test_policy_bodies_and_workspace_details_are_fetched_individually(self):
        azure = Azure()
        workspace = SOURCE + "/workspaces/team"
        api = workspace + "/apis/chat"
        policy = api + "/policies/policy"
        backend = workspace + "/backends/model"
        logger = workspace + "/loggers/telemetry"
        azure.collections[SOURCE + "/workspaces"] = {"value": [{"id": workspace}]}
        azure.collections[workspace + "/apis"] = {"value": [{"id": api}]}
        azure.collections[api] = {"id": api, "properties": {
            "type": "http", "path": "inference", "subscriptionRequired": False}}
        azure.collections[api + "/policies"] = {"value": [{"id": policy}]}
        azure.collections[policy] = {"id": policy, "properties": {"value":
            '<policies><inbound><base/><include-fragment fragment-id="auth"/>'
            '<set-backend-service backend-id="model"/><set-header name="Authorization"><value>{{model-key}}'
            'SECRET</value></set-header></inbound></policies>'}}
        azure.collections[workspace + "/backends"] = {"value": [{"id": backend}]}
        azure.collections[backend] = {"id": backend, "properties": {"url": "https://model.example/"}}
        azure.collections[workspace + "/loggers"] = {"value": [{"id": logger}]}
        source = source_inventory(SOURCE, azure)
        validate_schema(source, "source-inventory")
        self.assertTrue(any(item["domain"] == "loggers" for item in source["items"]))
        self.assertTrue(any(behavior.get("statement") == "set-header" for behavior in source["behaviors"]))
        self.assertNotIn("SECRET", json.dumps(source))
        references = [reference for item in source["items"] for node in item["policyShape"]
                      for reference in node["references"]]
        for domain, name in (("policyFragments", "auth"), ("backends", "model"), ("namedValues", "model-key")):
            self.assertIn({"domain": domain, "name": name}, references)
        urls = [call[call.index("--url") + 1] for call in azure.calls if "--url" in call]
        self.assertTrue(any(policy in url and "format=rawxml" in url for url in urls))
        self.assertFalse(any("/tools?" in url for url in urls))

    def test_missing_policy_body_and_failed_api_details_remain_gaps(self):
        azure = Azure()
        api = SOURCE + "/apis/chat"
        policy = SOURCE + "/policies/policy"
        azure.collections[SOURCE + "/apis"] = {"value": [{"id": api, "properties": {"type": "http"}}]}
        azure.collections[api] = MigrationError("Forbidden SECRET")
        azure.collections[SOURCE + "/policies"] = {"value": [{"id": policy}]}
        source = source_inventory(SOURCE, azure)
        gaps = {item["domain"]: item for item in source["coverage"]}
        for domain in ("apis", "policies"):
            self.assertFalse(gaps[domain]["establishesCompleteness"])
            self.assertEqual(gaps[domain]["status"], "failed")
        self.assertEqual(gaps["apis"]["failedResourceIds"], [api])
        self.assertNotIn("SECRET", json.dumps(source))

    def test_workspace_relationships_use_link_endpoints_and_preserve_scope(self):
        azure = Azure()
        workspace = SOURCE + "/workspaces/team"
        api, product, group, tag = (workspace + "/" + suffix for suffix in (
            "apis/chat", "products/ai", "groups/consumers", "tags/models"))
        azure.collections[SOURCE + "/workspaces"] = {"value": [{"id": workspace}]}
        for domain, rid in (("apis", api), ("products", product), ("groups", group), ("tags", tag)):
            azure.collections[workspace + "/" + domain] = {"value": [{"id": rid}]}
        for parent, path, key, target in (
                (product, "apiLinks", "apiId", api), (product, "groupLinks", "groupId", group),
                (tag, "apiLinks", "apiId", api), (tag, "productLinks", "productId", product)):
            azure.collections[parent + "/" + path] = {"value": [{
                "id": parent + "/" + path + "/link", "properties": {key: target}}]}
        source = source_inventory(SOURCE, azure)
        validate_schema(source, "source-inventory")
        for domain in ("product-apis", "product-groups", "api-tags", "product-tags"):
            self.assertTrue(any(item["domain"] == domain for item in source["items"]))
        self.assertTrue(next(c for c in source["coverage"] if c["scope"] == api
                             and c["domain"] == "api-tags")["establishesCompleteness"])
        urls = [call[call.index("--url") + 1] for call in azure.calls if "--url" in call]
        self.assertFalse(any(product + "/apis?" in url or api + "/tags?" in url for url in urls))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {
                "workspaces/team/products/ai/apis/chat/productApiInformation.json":
                    {"properties": {"apiId": api}},
                "workspaces/team/tags/models/apis/chat/tagApiInformation.json":
                    {"properties": {"apiId": api}},
            }
            for name, value in files.items():
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(json.dumps(value))
            apply_export(source, root, "apiops", export_digest(root))
            self.assertEqual(source["conflicts"], [])
        azure.collections[tag + "/apiLinks"]["value"][0]["properties"]["apiId"] = SOURCE + "/apis/foreign"
        source = source_inventory(SOURCE, azure)
        self.assertFalse(next(c for c in source["coverage"] if c["scope"] == api
                              and c["domain"] == "api-tags")["establishesCompleteness"])

    def test_noncurrent_revisions_have_their_own_operations_and_policies(self):
        azure = Azure()
        api = SOURCE + "/apis/chat"
        revision = api + ";rev=2"
        policy = revision + "/policies/policy"
        azure.collections[SOURCE + "/apis"] = {"value": [{
            "id": api, "properties": {"type": "http"}}]}
        azure.collections[api + "/revisions"] = {"value": [{"apiRevision": "2"}]}
        azure.collections[revision] = {"id": revision, "properties": {"type": "http", "apiRevision": "2"}}
        azure.collections[revision + "/policies"] = {"value": [{
            "id": policy, "properties": {"value": "<policies><inbound><base/></inbound></policies>"}}]}
        source = source_inventory(SOURCE, azure)
        self.assertTrue(any(item["id"] == policy for item in source["items"]))
        self.assertTrue(any(item["scope"] == revision and item["domain"] == "api-operations"
                            and item["establishesCompleteness"] for item in source["coverage"]))
        self.assertEqual(len({item["id"] for item in source["items"]}), len(source["items"]))

    def test_live_json_schema_structure_is_retained_without_payload_examples(self):
        azure = Azure()
        api = SOURCE + "/apis/chat"
        schema = api + "/schemas/request"
        azure.collections[SOURCE + "/apis"] = {"value": [{"id": api, "properties": {"type": "http"}}]}
        azure.collections[api + "/schemas"] = {"value": [{"id": schema}]}
        azure.collections[schema] = {"id": schema, "properties": {
            "contentType": "application/json",
            "document": {"value": json.dumps({"type": "object", "properties": {
                "messages": {"type": "array", "items": {"type": "string"}, "example": ["SECRET"]}}})}}}
        source = source_inventory(SOURCE, azure)
        validate_schema(source, "source-inventory")
        observed = next(item for item in source["items"] if item["id"] == schema)
        shape = observed["resource"]["properties"]["document"]["structure"]
        self.assertEqual(shape["properties"]["messages"]["items"]["type"], "string")
        self.assertNotIn("SECRET", json.dumps(source))
        azure.collections[schema]["properties"]["document"]["value"] = "{invalid"
        source = source_inventory(SOURCE, azure)
        self.assertFalse(next(c for c in source["coverage"] if c["scope"] == api
                              and c["domain"] == "api-schemas")["establishesCompleteness"])

    def test_direct_openapi_schema_documents_preserve_structure_but_not_raw_values(self):
        azure = Azure()
        api = SOURCE + "/apis/chat"
        schema = api + "/schemas/request"
        azure.collections[SOURCE + "/apis"] = {"value": [{"id": api, "properties": {"type": "http"}}]}
        azure.collections[api + "/schemas"] = {"value": [{"id": schema}]}
        azure.collections[schema] = {"id": schema, "properties": {
            "contentType": "application/vnd.oai.openapi.components+json",
            "document": {"components": {"schemas": {"Request": {
                "type": "object", "description": "SECRET", "properties": {
                    "messages": {"type": "array", "items": {"type": "string"}, "example": ["SECRET"]}}}}}}}}
        source = source_inventory(SOURCE, azure)
        validate_schema(source, "source-inventory")
        item = next(i for i in source["items"] if i["id"] == schema)
        document = item["resource"]["properties"]["document"]
        shape = document["structure"]["components"]["schemas"]["Request"]
        self.assertEqual(shape["properties"]["messages"]["items"]["type"], "string")
        self.assertNotIn("components", {key: value for key, value in document.items() if key != "structure"})
        self.assertNotIn("SECRET", json.dumps(source))
        for invalid in (None, [], {"value": None}, {"value": "{invalid"}):
            with self.subTest(invalid=invalid):
                azure.collections[schema]["properties"]["document"] = invalid
                source = source_inventory(SOURCE, azure)
                self.assertFalse(next(c for c in source["coverage"] if c["scope"] == api
                                      and c["domain"] == "api-schemas")["establishesCompleteness"])

    def test_apiops_policies_contracts_and_associations_are_source_evidence(self):
        for prefix in ("", "workspaces/team/"):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = source_inventory(SOURCE, Azure())
                contents = {
                    "apis/chat/apiInformation.json": json.dumps({"properties": {"type": "http"}}),
                    "apis/chat/policy.xml": "<policies><inbound><base/></inbound></policies>",
                    "apis/chat/operations/invoke/policy.xml":
                        '<policies><inbound><set-header name="x-key"><value>SECRET</value>'
                        '</set-header></inbound></policies>',
                    "apis/chat/specification.yaml":
                        'openapi: 3.0.1\npaths:\n  /chat/completions:\n    post:\n'
                        '      operationId: inference\n      description: SECRET\n'
                        '      requestBody:\n        content:\n          application/json:\n'
                        '            schema:\n              type: object\n              properties:\n'
                        '                messages:\n                  type: array\n'
                        '                  items:\n                    type: string\n'
                        '                  example: SECRET\n',
                    "policy fragments/auth/policyFragmentInformation.json":
                        json.dumps({"properties": {"description": "shared auth"}}),
                    "policy fragments/auth/policy.xml": "<fragment><base/></fragment>",
                    "products/ai/apis/chat/productApiInformation.json": "{}",
                    "loggers/ai/loggerInformation.json": json.dumps({"properties": {"loggerType": "azureMonitor"}}),
                }
                for name, content in contents.items():
                    file = root / (prefix + name)
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text(content)
                apply_export(source, root, "apiops", export_digest(root))
                validate_schema(source, "source-inventory")
                self.assertNotIn("SECRET", json.dumps(source))
                fragment = next(item for item in source["items"] if item["domain"] == "policyFragments")
                self.assertEqual([node["statement"] for node in fragment["policyShape"]], ["fragment", "base"])
                self.assertTrue(any(b.get("statement") == "set-header" for b in source["behaviors"]))
                contract = next(item for item in source["items"] if item["domain"] == "api-contracts")
                self.assertIn("/chat/completions", contract["resource"]["properties"]["structure"]["paths"])
                request = contract["resource"]["properties"]["structure"]["paths"][
                    "/chat/completions"]["post"]["requestBody"]["content"]["application/json"]
                self.assertEqual(request["schema"]["properties"]["messages"]["items"]["type"], "string")
                link = next(item for item in source["items"] if item["domain"] == "product-apis")
                scope = SOURCE + ("/workspaces/team" if prefix else "")
                self.assertEqual(link["resource"]["properties"]["targetResourceId"], scope + "/apis/chat")
                self.assertFalse(next(c for c in source["coverage"] if c["scope"] == scope + "/apis/chat"
                                      and c["domain"] == "api-tools")["establishesCompleteness"])

    def test_apiops_projection_and_relative_ids_do_not_create_false_conflicts(self):
        azure = Azure()
        api = SOURCE + "/apis/chat"
        fragment = SOURCE + "/policyFragments/auth"
        xml = "<fragment><base/></fragment>"
        azure.collections[SOURCE + "/apis"] = {"value": [{"id": api, "properties": {
            "type": "http", "apiVersionSetId": SOURCE + "/apiVersionSets/models",
            "isCurrent": True}}]}
        azure.collections[SOURCE + "/policyFragments"] = {"value": [{
            "id": fragment, "properties": {"description": "auth", "value": xml, "format": "rawxml"}}]}
        source = source_inventory(SOURCE, azure)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, content in {
                "apis/chat/apiInformation.json": json.dumps({"properties": {
                    "apiVersionSetId": "/apiVersionSets/models"}}),
                "policy fragments/auth/policyFragmentInformation.json": json.dumps({"properties": {
                    "description": "auth"}}),
                "policy fragments/auth/policy.xml": xml,
            }.items():
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            apply_export(source, root, "apiops", export_digest(root))
            self.assertEqual(source["conflicts"], [])
            (root / "policy fragments/auth/policy.xml").write_text("<fragment><return-response/></fragment>")
            apply_export(source, root, "apiops", export_digest(root))
            self.assertTrue(any(c["sourceId"] == fragment for c in source["conflicts"]))

    def test_apiops_contract_errors_and_unknown_artifacts_are_explicit(self):
        for name, content in (
                ("specification.yaml", "openapi: 3.0.1\npaths: &paths {}\nextra: *paths"),
                ("specification.yaml", "openapi: 3.0.1\npaths: {}\npaths: {}"),
                ("specification.json", '{"openapi":"3.0.1","paths":[]}'),
                ("unsupportedInformation.json", "{}")):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                file = root / "apis/chat" / name
                file.parent.mkdir(parents=True)
                file.write_text(content)
                with self.assertRaises(MigrationError):
                    apply_export(source_inventory(SOURCE, Azure()), root, "apiops", export_digest(root))

    def test_supported_and_future_profiles(self):
        for sku in ("BasicV2", "StandardV2", "PremiumV2"):
            source = source_inventory(SOURCE, Azure(sku))
            validate_schema(source, "source-inventory")
            self.assertEqual(source["sku"], sku)
        for sku in ("Basic", "Standard", "Premium", "AIGateway", "Developer", "unknown"):
            with self.assertRaises(MigrationError):
                source_inventory(SOURCE, Azure(sku))

    def test_reads_are_explicit_and_source_only(self):
        source, azure = bundle()
        self.assertEqual(len(source["source-inventory.json"]["items"]), 1)
        for call in azure.calls:
            if call[:2] == ["az", "rest"]:
                self.assertIn("get", call)
                self.assertIn(SOURCE, call[call.index("--url") + 1])
                self.assertIn("--subscription", call)

    def test_workspace_and_policy_graph(self):
        azure = Azure()
        workspace = SOURCE + "/workspaces/team"
        api = workspace + "/apis/chat"
        operation = api + "/operations/chat"
        azure.collections[SOURCE + "/workspaces"] = {"value": [{"id": workspace}]}
        azure.collections[workspace + "/apis"] = {"value": [{"id": api}]}
        azure.collections[api + "/operations"] = {"value": [{"id": operation}]}
        azure.collections[operation + "/policies"] = {"value": [{
            "id": operation + "/policies/policy",
            "properties": {"value": '<policies><inbound><base/><rate-limit calls="10" renewal-period="60"/></inbound></policies>'}
        }]}
        source = source_inventory(SOURCE, azure)
        self.assertTrue(any(item.get("statement") == "base" for item in source["behaviors"]))
        self.assertTrue(any(item["scope"] == workspace for item in source["coverage"]))
        self.assertNotIn('calls="10"', json.dumps(source))
        self.assertIn("renewal-period", json.dumps(source))

    def test_failed_and_partial_collections_never_empty(self):
        azure = Azure()
        azure.collections[SOURCE + "/backends"] = MigrationError("Forbidden sensitive detail")
        value, _ = bundle(azure)
        source = value["source-inventory.json"]
        coverage = next(c for c in source["coverage"] if c["domain"] == "backends")
        self.assertEqual(coverage["status"], "failed")
        self.assertFalse(coverage["establishesCompleteness"])
        self.assertNotIn("sensitive", json.dumps(source))
        self.assertTrue(any(gap_id(coverage) in m["sourceIds"]
                            for m in value["mapping.json"]["items"]))

    def test_malformed_policy_fragment_details_are_explicit_gaps(self):
        azure = Azure()
        fragment = SOURCE + "/policyFragments/shared"
        azure.collections[SOURCE + "/policyFragments"] = {"value": [{"id": fragment}]}
        azure.collections[fragment] = None
        source = source_inventory(SOURCE, azure)
        validate_schema(source, "source-inventory")
        coverage = next(c for c in source["coverage"] if c["domain"] == "policyFragments")
        self.assertEqual(coverage["status"], "failed")
        self.assertFalse(coverage["establishesCompleteness"])

    def test_pagination_and_unsafe_continuations(self):
        base = "https://management.azure.com" + SOURCE + "/apis?api-version=2024-05-01"
        page2 = base + "&$skip=1"
        responses = {base: {"value": [{"id": SOURCE + "/apis/a"}], "nextLink": page2},
                     page2: {"value": [{"id": SOURCE + "/apis/b"}]}}
        reader = Reader(SOURCE, lambda a: responses[a[a.index("--url") + 1]],
                        "https://management.azure.com/")
        self.assertEqual(len(reader.collection(SOURCE + "/apis")), 2)
        for link in ("https://evil.example/steal", base, base.replace("/apis?", "/backends?"),
                     base.replace("2024-05-01", "2000-01-01")):
            responses[base]["nextLink"] = link
            with self.assertRaises(MigrationError):
                reader.collection(SOURCE + "/apis")

    def test_secret_redaction_and_xml_entities(self):
        output = clean({"credentials": {"value": "TOPSECRET"},
                        "value": "TOPSECRET",
                        "endpoint": "https://example.com/?sig=TOPSECRET",
                        "description": "password=TOPSECRET"})
        self.assertNotIn("TOPSECRET", json.dumps(output))
        for xml in ('<!DOCTYPE policies [<!ENTITY x SYSTEM "file:///etc/passwd">]><policies/>',
                    "<broken>"):
            with self.assertRaises(MigrationError):
                policy_shape(xml)

    def test_export_approval_identity_and_conflict(self):
        value, _ = bundle()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backendInformation.json"
            path.write_text(json.dumps({"id": SOURCE + "/backends/a",
                                        "properties": {"url": "https://backend/"}}))
            with self.assertRaises(MigrationError):
                apply_export(value["source-inventory.json"], path, "apiops", None)
            source = apply_export(value["source-inventory.json"], path, "apiops", export_digest(path))
            self.assertEqual(source["provenance"][-1]["authority"], "advisory")
            self.assertEqual(source["items"][-1]["id"], SOURCE + "/backends/a")
            path.write_text(json.dumps({"id": TARGET + "/backends/a"}))
            with self.assertRaises(MigrationError):
                apply_export(source, path, "apiops", export_digest(path))

    def test_standard_apiops_completeness_recovers_only_claimed_domain(self):
        azure = Azure()
        azure.collections[SOURCE + "/backends"] = MigrationError("failed")
        source = source_inventory(SOURCE, azure)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "backends/b").mkdir(parents=True)
            (root / "backends/b/backendInformation.json").write_text(json.dumps({
                "properties": {"url": "https://backend.example/"}}))
            (root / "inventory-metadata.json").write_text(json.dumps({
                "schemaVersion": "1.0", "sourceResourceId": SOURCE,
                "collections": [{"scope": SOURCE, "domain": "backends",
                                 "resourceIds": [SOURCE + "/backends/b"], "complete": True}]}))
            apply_export(source, root, "apiops", export_digest(root))
            coverage = next(c for c in source["coverage"] if c["domain"] == "backends")
            self.assertTrue(coverage["establishesCompleteness"])
            self.assertTrue(coverage["evidence"].startswith("apiops:"))
            self.assertEqual(source["items"][-1]["authority"], "authoritative")
            self.assertNotIn(str(root), json.dumps(source))

    def test_export_cannot_turn_live_absence_into_authoritative_presence(self):
        value, _ = bundle()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "backendInformation.json"
            path.write_text(json.dumps({"id": SOURCE + "/backends/local-only",
                                        "properties": {"url": "https://backend/"}}))
            source = apply_export(value["source-inventory.json"], path, "apiops", export_digest(path))
            self.assertEqual(source["items"][-1]["authority"], "advisory")
            self.assertTrue(source["conflicts"])

    def test_arm_literal_identity_is_advisory_and_expressions_are_not_evaluated(self):
        value, _ = bundle()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "template.json"
            path.write_text(json.dumps({"resources": [{
                "type": "Microsoft.ApiManagement/service", "name": "source",
                "resources": [{"type": "backends", "name": "literal",
                               "properties": {"url": "[parameters('endpoint')]"}}]}]}))
            source = apply_export(value["source-inventory.json"], path, "arm", export_digest(path))
            self.assertEqual(source["provenance"][-1]["authority"], "advisory")
            self.assertEqual(source["items"][-1]["id"], SOURCE + "/backends/literal")

    def test_revision_and_product_associations_keep_distinct_evidence(self):
        azure = Azure()
        api = SOURCE + "/apis/chat"
        product = SOURCE + "/products/internal"
        azure.collections[SOURCE + "/apis"] = {"value": [{
            "id": api, "properties": {"type": "http"}}]}
        azure.collections[api + "/revisions"] = {"value": [{"apiRevision": "1", "isCurrent": True}]}
        azure.collections[SOURCE + "/products"] = {"value": [{"id": product}]}
        azure.collections[product + "/apis"] = {"value": [{"id": api}]}
        source = source_inventory(SOURCE, azure)
        self.assertTrue(any(item["domain"] == "product-apis" for item in source["items"]))
        self.assertTrue(any(item["domain"] == "api-revisions" for item in source["items"]))

    def test_service_mcp_tools_are_collected_but_workspace_tools_are_not_probed(self):
        azure = Azure()
        api = SOURCE + "/apis/tools"
        azure.collections[SOURCE + "/apis"] = {"value": [{
            "id": api, "properties": {"type": "mcp"}}]}
        azure.collections[api + "/tools"] = {"value": [{"id": api + "/tools/search"}]}
        source = source_inventory(SOURCE, azure)
        self.assertTrue(any(item["domain"] == "api-tools" for item in source["items"]))

    def test_hidden_pagination_and_malformed_gateway_lists_do_not_establish_absence(self):
        for response in ({"value": [], "next_token": "more"}, [{}], [None]):
            with self.assertRaises(MigrationError):
                destination_inventory(TARGET, lambda _: response)

    def test_incomplete_destination_cannot_establish_absence(self):
        def runner(argv):
            return {"value": [], "nextLink": "next"}
        with self.assertRaises(MigrationError):
            destination_inventory(TARGET, runner)

    def test_multiple_conflict_reasons_keep_one_mapping_and_all_evidence(self):
        value, _ = bundle()
        source = value["source-inventory.json"]
        source["conflicts"] = [
            {"sourceId": SOURCE, "evidenceDigest": digest("export"), "reason": reason}
            for reason in ("Conflicting properties.", "Conflicting completeness.")
        ]
        mapping = initial_mapping(source)
        self.assertEqual(len(source["conflicts"]), 2)
        self.assertEqual(len([item for item in mapping["items"]
                              if item["sourceIds"][0].startswith("conflict:")]), 1)

    def test_malformed_identity_and_network_are_explicit_destination_gaps(self):
        azure = Azure()
        azure.gateway = {"id": TARGET, "sku": {"name": "AIGateway"}, "identity": "invalid"}
        def runner(argv):
            return None if argv[2:4] == ["network", "show"] else azure(argv)
        value = destination_inventory(TARGET, runner)
        self.assertEqual({error["domain"] for error in value["errors"]}, {"identity", "network"})
        validate_schema(value, "destination-inventory")

    def test_new_destination_inventory_preserves_legacy_list_entries_without_selecting_them(self):
        azure = Azure()
        azure.gateway = {"id": TARGET, "type": GATEWAY_TYPE, "sku": {"name": "Consumption"}}
        legacy = {"id": TARGET.replace("/aigateways/", "/service/"), "sku": {"name": "AIGateway"}}
        def runner(argv):
            if argv[2:] == ["list", "--subscription", "sub", "--resource-group", "target-rg", "-o", "json"]:
                return [legacy, azure.gateway]
            self.assertNotIn("--workspace-name", argv)
            return azure(argv)
        result = destination_inventory(TARGET, runner)
        self.assertTrue(result["exists"])
        self.assertEqual(result["collections"]["gateway"], [azure.gateway])
        self.assertEqual(result["errors"], [])


class PlanningTests(unittest.TestCase):
    def test_plan_validates_and_approval_does_not_change_digest(self):
        value, _ = ready_bundle()
        result = validate_plan(value)
        self.assertEqual(result["errors"], [])
        before = plan_digest(value)
        approve(value, "create-gateway", before)
        self.assertEqual(plan_digest(value), before)

    def test_dropped_behavior_wrong_target_and_arbitrary_options(self):
        for mutation, code in (
            (lambda b: b["mapping.json"]["items"][0].update(behaviorIds=[]), "source-coverage"),
            (lambda b: b["todos.json"]["items"][0]["target"].update(gateway="source"), "wrong-target"),
            (lambda b: b["todos.json"]["items"][0]["arguments"].update(debug=True), "invalid-options"),
            (lambda b: b["todos.json"]["items"][0]["dependsOn"].append("missing"), "dependency"),
            (lambda b: b["todos.json"]["items"][0]["dependsOn"].append("create-gateway"), "cycle"),
        ):
            value, _ = ready_bundle()
            mutation(value)
            self.assertIn(code, {issue["code"] for issue in validate_plan(value)["errors"]})

    def test_modified_capability_catalog_rejected(self):
        value, _ = ready_bundle()
        contract = value["capability-contract.json"]
        contract["capabilities"][0]["command"] = ["delete"]
        contract["contractDigest"] = digest({k: v for k, v in contract.items() if k != "contractDigest"})
        self.assertIn("capability-catalog", {e["code"] for e in validate_plan(value)["errors"]})

    def test_old_state_and_literal_secrets_rejected(self):
        value, _ = ready_bundle()
        value["mapping.json"]["schemaVersion"] = "2.0"
        self.assertEqual(validate_plan(value)["status"], "invalid")
        value, _ = ready_bundle()
        value["todos.json"]["items"][0]["arguments"]["password"] = "TOPSECRET"
        result = validate_plan(value)
        self.assertIn("literal-secret", {e["code"] for e in result["errors"]})
        self.assertNotIn("TOPSECRET", json.dumps(result))
        self.assertTrue(contains_secret({"url": "https://example/?token=TOPSECRET"}))
        self.assertFalse(contains_secret({"token-limit": 1000}))

    def test_unavailable_cli_capability_and_source_health(self):
        value, _ = ready_bundle()
        contract = value["capability-contract.json"]
        next(cap for cap in contract["capabilities"] if cap["id"] == "gateway.create")["support"] = "unavailable"
        contract["contractDigest"] = digest({k: v for k, v in contract.items() if k != "contractDigest"})
        self.assertIn("unsupported-command", {e["code"] for e in validate_plan(value)["errors"]})
        value, _ = ready_bundle()
        value["source-inventory.json"]["service"]["properties"]["provisioningState"] = "Failed"
        self.assertIn("source-health", {e["code"] for e in validate_plan(value)["errors"]})

    def test_unknown_coverage_cannot_be_accepted_residual(self):
        azure = Azure()
        azure.collections[SOURCE + "/apis"] = MigrationError("failure")
        value, _ = bundle(azure)
        mapping = next(m for m in value["mapping.json"]["items"] if m["sourceIds"][0].startswith("gap:"))
        mapping["classification"] = "cannot-import"
        self.assertIn("coverage-gap", {e["code"] for e in validate_plan(value)["errors"]})

    def test_real_configuration_assertions_not_just_existence(self):
        value, _ = ready_bundle()
        value["todos.json"]["items"][0]["desiredState"] = {"properties": {"provisioningState": "Succeeded"}}
        self.assertIn("desired-state", {e["code"] for e in validate_plan(value)["errors"]})

    def test_argument_shapes_and_option_injection_are_rejected(self):
        for arguments in ({"location": "--debug"}, {"location": "@/tmp/input"}):
            value, _ = ready_bundle()
            value["todos.json"]["items"][0]["arguments"] = arguments
            self.assertIn("option-value", {e["code"] for e in validate_plan(value)["errors"]})

    def test_typed_policy_network_identity_and_model_assertions(self):
        caps = {cap["id"]: cap for cap in catalog()["capabilities"]}
        examples = [
            ("model.policy", {"token-limit": 100, "token-period": "hour", "token-counter-key": "IPAddress"},
             {"properties": {"policies": [{"type": "tokenLimit", "count": 100, "period": "hour", "counterKey": ["ipAddress"]}]}}),
            ("network.update", {"subnet": "/subscriptions/sub/subnets/a"},
             {"virtualNetworkType": "External", "virtualNetworkConfiguration": {"subnetResourceId": "/subscriptions/sub/subnets/a"}}),
            ("identity.assign", {"system-assigned": True}, {"type": "SystemAssigned"}),
            ("model.create", {"deployment-config": {"modelName": "gpt-4o"}, "api-format": "OpenAIChatCompletions"},
             {"properties": {"deployment": {"modelName": "gpt-4o"}, "apiFormat": "OpenAIChatCompletions"}}),
            ("model.update", {"deployment": {"modelName": "gpt-4o"}},
             {"properties": {"deployment": {"modelName": "gpt-4o"}}}),
            ("mcp.source.add", {"namespace": "learn", "kind": "mcp", "mcp": {"url": "https://learn.example/mcp"}},
             {"properties": {"endpoints": [{"namespace": "learn", "kind": "mcp", "mcp": {"url": "https://learn.example/mcp"}}]}}),
        ]
        for cid, arguments, desired in examples:
            with self.subTest(capability=cid):
                self.assertTrue(meaningful_assertion({"arguments": arguments, "desiredState": desired}, caps[cid]))
                self.assertFalse(meaningful_assertion({"arguments": arguments, "desiredState": {}}, caps[cid]))

    def test_model_policy_readback_requires_new_rp_counter_arrays(self):
        cap = next(cap for cap in catalog()["capabilities"] if cap["id"] == "model.policy")
        for option, counter in ((None, "identity"), ("Identity", "identity"), ("IPAddress", "ipAddress")):
            with self.subTest(counter=option):
                arguments = {"token-limit": 100}
                if option is not None:
                    arguments["token-counter-key"] = option
                policy = {"type": "tokenLimit", "count": 100, "period": "minute", "counterKey": [counter]}
                todo = {"arguments": arguments, "desiredState": {"properties": {"policies": [policy]}}}
                self.assertTrue(meaningful_assertion(todo, cap))
                policy["counterKey"] = option or "Identity"
                self.assertFalse(meaningful_assertion(todo, cap))
                policy["counterKey"] = ["ipAddress" if counter == "identity" else "identity"]
                self.assertFalse(meaningful_assertion(todo, cap))

    def test_policy_option_dependencies_fail_validation_before_execution(self):
        azure = Azure()
        sid = SOURCE + "/policies/policy"
        azure.collections[SOURCE + "/policies"] = {"value": [{
            "id": sid, "properties": {
                "value": '<policies><inbound><azure-openai-token-limit tokens-per-minute="100"/></inbound></policies>'}
        }]}
        value, _ = ready_bundle(azure)
        value["mapping.json"]["items"][0].update(
            classification="needs-input", capabilityId=None, semanticDecision=None,
            question="Decide remaining source behavior.")
        mapping = next(item for item in value["mapping.json"]["items"] if sid in item["sourceIds"])
        mapping.update(classification="ready", capabilityId="model.policy", question=None,
                       semanticDecision="Apply a model-scoped token limit.")
        todo = value["todos.json"]["items"][0]
        todo.update(capabilityId="model.policy", mappingIds=[mapping["id"]],
                    arguments={"token-limit": 100},
                    desiredState={"properties": {"policies": [{
                        "type": "tokenLimit", "count": 100, "period": "minute", "counterKey": ["identity"]
                    }]}},
                    precondition={"exists": True, "stateDigest": digest("existing-model")},
                    behaviorResults={bid: {"status": "pending", "method": "control-plane",
                                           "evidenceDigest": None, "recordedAt": None}
                                     for bid in mapping["behaviorIds"]})
        todo["target"].update(name="model", provider="provider")
        self.assertEqual(validate_plan(value)["errors"], [])
        for arguments, code in (
                ({"content-safety": "Medium", "token-period": "hour"}, "policy-shape"),
                ({"content-safety": "Medium", "token-counter-key": "Identity"}, "policy-shape"),
                ({"token-limit": 100, "hate-severity": "High"}, "policy-shape"),
                ({"content-safety": "Medium", "violence-severity": "Extreme"}, "option-value")):
            todo["arguments"] = arguments
            self.assertIn(code, {error["code"] for error in validate_plan(value)["errors"]})

    def test_contradictory_final_assertions_for_same_target_are_rejected(self):
        value, _ = ready_bundle()
        other = copy.deepcopy(value["todos.json"]["items"][0])
        other["id"] = "conflicting-gateway"
        other["arguments"]["location"] = "westus"
        other["desiredState"]["location"] = "westus"
        value["todos.json"]["items"].append(other)
        self.assertIn("contradictory-state", {e["code"] for e in validate_plan(value)["errors"]})


class ExecutionTests(unittest.TestCase):
    def test_gateway_creation_uses_new_resource_type_and_create_time_subnet(self):
        value, azure = ready_bundle()
        todo = value["todos.json"]["items"][0]
        subnet = "/subscriptions/sub/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/vnet/subnets/integration"
        todo["arguments"]["subnet"] = subnet
        todo["desiredState"]["properties"]["backend"] = {"subnet": {"id": subnet}}
        value["plan-validation.json"] = validate_plan(value)
        self.assertEqual(value["plan-validation.json"]["errors"], [])
        approve(value, todo["id"], plan_digest(value))
        execute(value, todo["id"], plan_digest(value), lambda _: None, azure, cli)
        self.assertEqual(todo["status"], "resource-verified")
        self.assertEqual(azure.gateway["type"], GATEWAY_TYPE)
        mutations = [call for call in azure.calls if call[:3] == ["az", "aigateway", "create"]]
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0], [
            "az", "aigateway", "create", "--subscription", "sub", "--resource-group", "target-rg",
            "--name", "target", "--location", "eastus2", "--subnet", subnet, "-o", "json"])

    def test_standalone_entry_point_uses_selected_python_environment(self):
        result = subprocess.run(
            [sys.executable, "-B", str(Path(migration.__file__)), "--help"],
            capture_output=True, text=True, check=False, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("collect-source", result.stdout)
        self.assertIn("record-verification", result.stdout)

    def test_public_commands_preserve_invalid_candidates_and_complete_verified_workflow(self):
        value, azure = ready_bundle()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            for name in ("source-inventory", "destination-inventory", "capability-contract", "mapping", "todos"):
                (root / (name + ".json")).write_text(json.dumps(value[name + ".json"]))
            state = State(root / "state")
            base = ["--state-dir", str(state.path)]
            self.assertEqual(migration.main([
                "init", *base, "--source-file", str(root / "source-inventory.json"),
                "--destination-file", str(root / "destination-inventory.json"),
                "--capabilities-file", str(root / "capability-contract.json")]), 0)
            self.assertEqual(migration.main([
                "validate-plan", *base, "--mapping-file", str(root / "mapping.json"),
                "--todos-file", str(root / "todos.json")]), 0)
            previous = state.load()["context.json"]["generationId"]
            bad_todos = copy.deepcopy(value["todos.json"])
            bad_todos["items"][0]["arguments"]["debug"] = True
            (root / "invalid.json").write_text(json.dumps(bad_todos))
            self.assertEqual(migration.main([
                "validate-plan", *base, "--todos-file", str(root / "invalid.json")]), 1)
            self.assertEqual(state.load()["context.json"]["generationId"], previous)
            pdigest = state.load()["plan-validation.json"]["planDigest"]
            approved = ["--todo-id", "create-gateway", "--plan-digest", pdigest]
            self.assertEqual(migration.main(["approve", *base, *approved]), 0)
            with patch("migration.execute", side_effect=lambda b, tid, pd, save, exports, credential_read_approved:
                       execute(b, tid, pd, save, azure, cli, exports,
                               credential_read_approved=credential_read_approved)):
                self.assertEqual(migration.main(["execute", *base, *approved]), 0)
            for bid in value["todos.json"]["items"][0]["behaviorResults"]:
                self.assertEqual(migration.main([
                    "record-verification", *base, *approved, "--behavior-id", bid,
                    "--method", "control-plane", "--evidence-digest", digest("verified")]), 0)
            with patch("migration.refresh", side_effect=lambda b, exports, credential_read_approved:
                       refresh(b, azure, cli, exports, credential_read_approved=credential_read_approved)), \
                 patch("migration.verify_final_resources", side_effect=lambda b, snapshot:
                       verify_final_resources(b, snapshot, azure)):
                self.assertEqual(migration.main(["report", *base]), 0)
            self.assertEqual(state.load()["context.json"]["completionStatus"], "complete")
            self.assertEqual(migration.main(["check-state", *base]), 0)
            self.assertEqual(migration.main(["cancel", *base]), 0)
            self.assertEqual(state.load()["context.json"]["completionStatus"], "cancelled")

    def test_native_child_templates_execute_with_exact_json_arguments_and_resource_ids(self):
        cases = [
            ("provider.create", "model-provider", "backends",
             {"kind": "Custom", "custom": {"endpoint": "https://backend.example/"}},
             {"kind": "Custom", "custom": {"endpoint": "https://backend.example/"}}),
            ("provider.update", "model-provider", "backends",
             {"display-name": "Updated provider"}, {"displayName": "Updated provider"}),
            ("model.create", "model", "apis",
             {"deployment-config": {"modelName": "runtime-model"}, "api-format": "OpenAIChatCompletions",
              "supported-endpoints": ["/openai/v1/chat/completions"]},
             {"deployment": {"modelName": "runtime-model"}, "apiFormat": "OpenAIChatCompletions",
              "supportedEndpoints": ["/openai/v1/chat/completions"]}),
            ("model.update", "model", "apis",
             {"deployment": {"modelName": "runtime-v2"}, "api-format": "OpenAIChatCompletions",
              "supported-endpoints": ["/openai/v1/chat/completions"]},
             {"deployment": {"modelName": "runtime-v2"}, "apiFormat": "OpenAIChatCompletions",
              "supportedEndpoints": ["/openai/v1/chat/completions"]}),
            ("model.policy", "model", "policies",
             {"token-limit": 100, "token-period": "hour", "token-counter-key": "IPAddress"},
             {"policies": [{"type": "tokenLimit", "count": 100, "period": "hour", "counterKey": ["ipAddress"]}]}),
            ("mcp.create", "mcp", "apis",
             {"endpoints": [{"namespace": "tools", "kind": "mcp", "mcp": {"url": "https://tools.example/mcp"}}]},
             {"endpoints": [{"namespace": "tools", "kind": "mcp", "mcp": {"url": "https://tools.example/mcp"}}]}),
            ("mcp.update", "mcp", "apis",
             {"endpoints": [{"namespace": "replacement", "kind": "mcp", "mcp": {"url": "https://tools.example/v2"}}]},
             {"endpoints": [{"namespace": "replacement", "kind": "mcp", "mcp": {"url": "https://tools.example/v2"}}]}),
            ("mcp.source.add", "mcp", "apis",
             {"namespace": "added", "kind": "mcp", "mcp": {"url": "https://added.example/mcp"}},
             {"endpoints": [{"namespace": "added", "kind": "mcp", "mcp": {"url": "https://added.example/mcp"}}]}),
        ]
        for cid, group, domain, arguments, properties in cases:
            with self.subTest(capability=cid):
                azure = Azure()
                azure.gateway = {"id": TARGET, "sku": {"name": "AIGateway"},
                                 "properties": {"provisioningState": "Succeeded"}}
                sid = SOURCE + "/" + domain + "/configured"
                source_properties = ({"value": '<policies><inbound><azure-openai-token-limit tokens-per-minute="100"/></inbound></policies>'}
                                     if domain == "policies" else {"type": "http"})
                azure.collections[SOURCE + "/" + domain] = {
                    "value": [{"id": sid, "properties": source_properties}]}
                value, azure = ready_bundle(azure)
                mapping = next(item for item in value["mapping.json"]["items"] if sid in item["sourceIds"])
                value["mapping.json"]["items"][0].update(
                    classification="needs-input", capabilityId=None, semanticDecision=None,
                    question="Decide remaining source behavior.")
                mapping.update(classification="ready", capabilityId=cid, question=None,
                               semanticDecision="Approved synthetic resource and separate behavior checks.")
                todo = value["todos.json"]["items"][0]
                todo.update(id="configure-child", mappingIds=[mapping["id"]], capabilityId=cid,
                            arguments=arguments, desiredState={"properties": properties},
                            behaviorResults={bid: {"status": "pending", "method": "control-plane",
                                                   "evidenceDigest": None, "recordedAt": None}
                                             for bid in mapping["behaviorIds"]})
                todo["target"].update(name="child", provider="parent" if group == "model" else None)
                prefix = TARGET + "/workspaces/default/"
                rid = prefix + {"model-provider": "modelProviders/child",
                                "model": "modelProviders/parent/models/child",
                                "mcp": "toolServers/child"}[group]
                cap = next(cap for cap in catalog()["capabilities"] if cap["id"] == cid)
                existing = None if cap["kind"] == "create" else {
                    "id": rid, "properties": {"displayName": "Existing", "description": "Preserved"}}
                rows = [] if existing is None else [existing]
                mutations = []
                def runner(argv):
                    nonlocal rows
                    if argv[2:2 + len(cap["command"])] == cap["command"]:
                        for key, expected in arguments.items():
                            actual = argv[argv.index("--" + key) + 1]
                            if isinstance(expected, (dict, list)):
                                actual = read_json(actual[1:])
                            else:
                                actual = str(actual)
                                expected = str(expected)
                            self.assertEqual(actual, expected)
                        self.assertNotIn("--foundry-resource-id", argv)
                        mutations.append(cid)
                        rows = [{"id": rid, "properties": {
                            **(existing["properties"] if existing else {}), **properties}}]
                        return copy.deepcopy(rows[0])
                    if argv[2:4] == [group, "list"]:
                        return copy.deepcopy(rows)
                    if argv[2:4] == [group, "show"]:
                        self.assertIn("--gateway-name", argv)
                        self.assertNotIn("--workspace-name", argv)
                        if group == "model":
                            self.assertEqual(argv[argv.index("--provider-name") + 1], "parent")
                        return copy.deepcopy(rows[0])
                    return azure(argv)
                value["destination-inventory.json"] = destination_inventory(TARGET, runner)
                todo["precondition"] = {"exists": existing is not None,
                                        "stateDigest": digest(semantic(existing)) if existing else None}
                value["plan-validation.json"] = validate_plan(value)
                self.assertEqual(value["plan-validation.json"]["errors"], [])
                approve(value, todo["id"], plan_digest(value))
                execute(value, todo["id"], plan_digest(value), lambda _: None, runner, cli)
                self.assertEqual(mutations, [cid])
                self.assertEqual(todo["status"], "resource-verified")
                verify_final_resources(value, value["destination-inventory.json"], runner)

    def test_assign_identity_when_existing_gateway_has_no_identity(self):
        azure = Azure()
        azure.gateway = {"id": TARGET, "name": "target", "location": "eastus2",
                         "sku": {"name": "AIGateway"},
                         "properties": {"provisioningState": "Succeeded"}}
        value, azure = ready_bundle(azure)
        value["mapping.json"]["items"][0]["capabilityId"] = "identity.assign"
        todo = value["todos.json"]["items"][0]
        todo.update(capabilityId="identity.assign", arguments={"system-assigned": True},
                    desiredState={"type": "SystemAssigned"},
                    precondition={"exists": True, "stateDigest": digest({})})
        value["plan-validation.json"] = validate_plan(value)
        self.assertEqual(value["plan-validation.json"]["errors"], [])
        self.assertEqual(value["destination-inventory.json"]["collections"]["identity"], {})
        def runner(argv):
            if argv[2:4] == ["identity", "assign"]:
                azure.gateway["identity"] = {"type": "SystemAssigned", "principalId": "new-principal"}
                return azure.gateway["identity"]
            return azure(argv)
        approve(value, todo["id"], plan_digest(value))
        execute(value, todo["id"], plan_digest(value), lambda _: None, runner, cli)
        self.assertEqual(todo["status"], "resource-verified")

    def test_user_assigned_identity_uses_a_json_array_not_an_object(self):
        azure = Azure()
        azure.gateway = {"id": TARGET, "type": GATEWAY_TYPE}
        identity = "/subscriptions/sub/resourceGroups/identities/providers/Microsoft.ManagedIdentity/userAssignedIdentities/client"
        value, azure = ready_bundle(azure)
        value["mapping.json"]["items"][0]["capabilityId"] = "identity.assign"
        todo = value["todos.json"]["items"][0]
        todo.update(capabilityId="identity.assign", arguments={"user-assigned": {identity: {}}},
                    desiredState={"type": "UserAssigned", "userAssignedIdentities": {identity: {}}},
                    precondition={"exists": True, "stateDigest": digest({})})
        self.assertIn("option-shape", {e["code"] for e in validate_plan(value)["errors"]})
        todo["arguments"] = {"user-assigned": [identity]}
        value["plan-validation.json"] = validate_plan(value)
        self.assertEqual(value["plan-validation.json"]["errors"], [])
        def runner(argv):
            if argv[2:4] == ["identity", "assign"]:
                path = argv[argv.index("--user-assigned") + 1]
                self.assertEqual(read_json(path[1:]), [identity])
                azure.gateway["identity"] = todo["desiredState"]
                return azure.gateway["identity"]
            return azure(argv)
        approve(value, todo["id"], plan_digest(value))
        execute(value, todo["id"], plan_digest(value), lambda _: None, runner, cli)
        self.assertEqual(todo["status"], "resource-verified")

    def test_final_readback_does_not_reuse_superseded_resource_verification(self):
        value, azure = ready_bundle()
        approve(value, "create-gateway", plan_digest(value))
        execute(value, "create-gateway", plan_digest(value), lambda _: None, azure, cli)
        todo = value["todos.json"]["items"][0]
        for bid in todo["behaviorResults"]:
            record_behavior(value, todo["id"], bid, "control-plane", digest("verified"), plan_digest(value))
        verify_final_resources(value, destination_inventory(TARGET, azure), azure)
        azure.gateway["location"] = "westus"
        with self.assertRaises(MigrationError):
            verify_final_resources(value, destination_inventory(TARGET, azure), azure)
        self.assertEqual(todo["status"], "blocked")
        self.assertTrue(all(result["evidenceDigest"] is None for result in todo["behaviorResults"].values()))

    def test_unsupported_behavior_requires_current_digest_residual_acceptance(self):
        azure = Azure()
        product = SOURCE + "/products/existing"
        azure.collections[SOURCE + "/products"] = {"value": [{"id": product}]}
        value, azure = ready_bundle(azure)
        residual = next(item for item in value["mapping.json"]["items"] if product in item["sourceIds"])
        residual.update(classification="cannot-import", question=None, residual={
            "reason": "APIM product access has no equivalent gateway resource.",
            "manualAction": "Redesign client access and validate it separately.",
            "acceptance": "pending", "approvedPlanDigest": None, "decidedAt": None})
        value["plan-validation.json"] = validate_plan(value)
        self.assertEqual(value["plan-validation.json"]["errors"], [])
        pdigest = plan_digest(value)
        approve(value, "create-gateway", pdigest)
        execute(value, "create-gateway", pdigest, lambda _: None, azure, cli)
        todo = value["todos.json"]["items"][0]
        for bid in todo["behaviorResults"]:
            record_behavior(value, todo["id"], bid, "control-plane", digest("verified"), pdigest)
        self.assertEqual(report(value, fresh=True), "incomplete")
        self.assertIn("Redesign client access and validate it separately.", value["migration-report.md"])
        residual["residual"].update(acceptance="accepted", approvedPlanDigest=pdigest, decidedAt="now")
        self.assertEqual(plan_digest(value), pdigest)
        self.assertEqual(report(value, fresh=True), "complete-with-accepted-residuals")
        residual["residual"]["approvedPlanDigest"] = digest("different-plan")
        self.assertEqual(report(value, fresh=True), "incomplete")

    def test_existing_gateway_is_read_only_reuse_not_a_fake_create_precondition(self):
        value, azure = ready_bundle()
        azure.gateway = {"id": TARGET, "type": GATEWAY_TYPE, "name": "target", "location": "eastus2",
                         "sku": {"name": "AIGateway"}, "properties": {"provisioningState": "Succeeded"}}
        value["destination-inventory.json"] = destination_inventory(TARGET, azure)
        value["mapping.json"]["items"][0]["capabilityId"] = "gateway.verify"
        todo = value["todos.json"]["items"][0]
        todo.update(capabilityId="gateway.verify", arguments={},
                    precondition={"exists": True, "stateDigest": digest(semantic(azure.gateway))})
        value["plan-validation.json"] = validate_plan(value)
        self.assertEqual(value["plan-validation.json"]["errors"], [])
        approve(value, todo["id"], plan_digest(value))
        execute(value, todo["id"], plan_digest(value), lambda _: None, azure, cli)
        self.assertEqual(todo["status"], "resource-verified")
        self.assertFalse(any(call[2] == "create" for call in azure.calls
                             if call[:2] == ["az", "aigateway"]))

    def test_full_workflow_and_resume_noop(self):
        value, azure = ready_bundle()
        pdigest = plan_digest(value)
        with tempfile.TemporaryDirectory() as temporary:
            state = State(Path(temporary) / "state")
            with state.locked(create=True):
                state.save(value)
                approve(value, "create-gateway", pdigest)
                state.save(value)
                execute(value, "create-gateway", pdigest, state.save, azure, cli)
                todo = value["todos.json"]["items"][0]
                self.assertEqual(todo["status"], "resource-verified")
                self.assertEqual(report(value, fresh=True), "incomplete")
                for bid in todo["behaviorResults"]:
                    record_behavior(value, todo["id"], bid, "control-plane", digest("verified"), pdigest)
                self.assertEqual(report(value, fresh=True), "complete")
                state.save(value)
                value = state.load()
                before = sum(call[2] == "create" for call in azure.calls if call[:2] == ["az", "aigateway"])
                execute(value, "create-gateway", pdigest, state.save, azure, cli)
                after = sum(call[2] == "create" for call in azure.calls if call[:2] == ["az", "aigateway"])
                self.assertEqual(before, after)
                self.assertEqual(value["todos.json"]["items"][0]["status"], "behavior-verified")

    def test_no_mutation_without_approval_or_with_drift(self):
        value, azure = ready_bundle()
        with self.assertRaises(MigrationError):
            execute(value, "create-gateway", plan_digest(value), lambda _: None, azure, cli)
        approve(value, "create-gateway", plan_digest(value))
        azure.source["tags"] = {"changed": "yes"}
        with self.assertRaises(MigrationError):
            execute(value, "create-gateway", plan_digest(value), lambda _: None, azure, cli)
        self.assertIsNone(azure.gateway)

    def test_cli_drift_is_detected_before_mutation(self):
        value, azure = ready_bundle()
        approve(value, "create-gateway", plan_digest(value))
        def changed():
            result = cli()
            result["extension"]["extensionVersion"] = "changed"
            return result
        with self.assertRaises(MigrationError):
            execute(value, "create-gateway", plan_digest(value), lambda _: None, azure, changed)
        self.assertIsNone(azure.gateway)

    def test_invalid_verification_evidence_is_rejected(self):
        value, _ = ready_bundle()
        todo = value["todos.json"]["items"][0]
        todo["status"] = "resource-verified"
        bid = next(iter(todo["behaviorResults"]))
        with self.assertRaises(MigrationError):
            record_behavior(value, todo["id"], bid, "control-plane", "sha256:invalid", plan_digest(value))

    def test_failed_and_inconclusive_behavior_are_not_completion(self):
        for outcome, expected in (("failed", "failed"), ("inconclusive", "blocked")):
            value, azure = ready_bundle()
            approve(value, "create-gateway", plan_digest(value))
            execute(value, "create-gateway", plan_digest(value), lambda _: None, azure, cli)
            todo = value["todos.json"]["items"][0]
            bid = next(iter(todo["behaviorResults"]))
            record_behavior(value, todo["id"], bid, "administrator-attestation",
                            digest("evidence"), plan_digest(value), outcome)
            self.assertEqual(report(value, fresh=True), expected)

    def test_unknown_outcome_readback_precedes_retry(self):
        value, azure = ready_bundle()
        approve(value, "create-gateway", plan_digest(value))
        azure.unknown_success = True
        with self.assertRaises(MigrationError):
            execute(value, "create-gateway", plan_digest(value), lambda _: None, azure, cli)
        self.assertEqual(value["todos.json"]["items"][0]["status"], "mutation-unknown")
        execute(value, "create-gateway", plan_digest(value), lambda _: None, azure, cli)
        self.assertEqual(value["todos.json"]["items"][0]["status"], "resource-verified")
        self.assertEqual(sum(call[2] == "create" for call in azure.calls
                             if call[:2] == ["az", "aigateway"]), 1)

    def test_runtime_secret_is_only_in_protected_temporary_input(self):
        value, _ = ready_bundle()
        todo = value["todos.json"]["items"][0]
        todo["arguments"] = {"custom": {"authentication": {"apiKey": {
            "value": {"$runtimeSecret": "MIGRATION_TEST_KEY"}}}}}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"MIGRATION_TEST_KEY": "TOPSECRET"}):
            argv = mutation_argv(value, todo, directory)
            self.assertNotIn("TOPSECRET", " ".join(argv))
            path = Path(argv[argv.index("--custom") + 1][1:])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIn("TOPSECRET", path.read_text())
        self.assertFalse(path.exists())

    def test_checkpoint_lock_tampering_and_symlink_rejection(self):
        value, _ = ready_bundle()
        with tempfile.TemporaryDirectory() as directory:
            state = State(Path(directory) / "state")
            with state.locked(create=True):
                state.save(value)
                with self.assertRaises(MigrationError):
                    with state.locked():
                        pass
                path = state.path / "generations" / value["context.json"]["generationId"] / "todos.json"
                path.write_text('{"tampered":true}')
                with self.assertRaises(MigrationError):
                    state.load()
            link = Path(directory) / "link"
            link.symlink_to(state.path)
            with self.assertRaises(MigrationError):
                State(link)

    def test_incomplete_generation_and_legacy_state_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            state = State(directory)
            (Path(directory) / "context.json").write_text('{"schemaVersion":"2.0"}')
            with self.assertRaises(MigrationError):
                state.load()
            self.assertEqual(read_json(Path(directory) / "context.json")["schemaVersion"], "2.0")

    def test_interrupted_promotion_preserves_previous_committed_generation(self):
        value, _ = ready_bundle()
        with tempfile.TemporaryDirectory() as directory:
            state = State(Path(directory) / "state")
            with state.locked(create=True):
                state.save(value)
                previous = state.load()["context.json"]["generationId"]
                with patch("core.os.replace", side_effect=OSError("simulated interruption")):
                    with self.assertRaises(OSError):
                        state.save(value)
                self.assertEqual(state.load()["context.json"]["generationId"], previous)

    def test_noncanonical_numbers_and_duplicate_json_keys_are_rejected(self):
        for number in (float("nan"), float("inf"), 2 ** 54):
            with self.assertRaises(MigrationError):
                digest(number)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"name":"first","name":"second"}')
            with self.assertRaises(MigrationError):
                read_json(path)


if __name__ == "__main__":
    unittest.main()
