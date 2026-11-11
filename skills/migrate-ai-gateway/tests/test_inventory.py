"""Offline source and destination inventory regressions."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from core import GATEWAY_TYPE, MigrationError, clean, digest, read_json, resource_id, validate_schema
from gateway import destination_inventory
from inventory import Reader, apply_export, export_digest, policy_shape, source_inventory
from fixtures import Azure, SOURCE, TARGET

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

    def test_inventory_is_independent_of_destination_cli_inspection(self):
        with patch("gateway.inspect_cli", side_effect=AssertionError("Destination CLI unavailable")):
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

    def test_every_source_tier_is_collected(self):
        for sku in ("Consumption", "Developer", "Basic", "Standard", "Premium",
                    "BasicV2", "StandardV2", "PremiumV2"):
            source = source_inventory(SOURCE, Azure(sku))
            validate_schema(source, "source-inventory")
            self.assertEqual(source["sku"], sku)
        for sku in ("", None):
            with self.assertRaises(MigrationError):
                source_inventory(SOURCE, Azure(sku))

    def test_reads_are_explicit_and_source_only(self):
        azure = Azure()
        source = source_inventory(SOURCE, azure)
        self.assertEqual(len(source["items"]), 1)
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
        source = source_inventory(SOURCE, azure)
        coverage = next(c for c in source["coverage"] if c["domain"] == "backends")
        self.assertEqual(coverage["status"], "failed")
        self.assertFalse(coverage["establishesCompleteness"])
        self.assertNotIn("sensitive", json.dumps(source))

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
        inventory = source_inventory(SOURCE, Azure())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backendInformation.json"
            path.write_text(json.dumps({"id": SOURCE + "/backends/a",
                                        "properties": {"url": "https://backend/"}}))
            with self.assertRaises(MigrationError):
                apply_export(inventory, path, "apiops", None)
            source = apply_export(inventory, path, "apiops", export_digest(path))
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
        inventory = source_inventory(SOURCE, Azure())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "backendInformation.json"
            path.write_text(json.dumps({"id": SOURCE + "/backends/local-only",
                                        "properties": {"url": "https://backend/"}}))
            source = apply_export(inventory, path, "apiops", export_digest(path))
            self.assertEqual(source["items"][-1]["authority"], "advisory")
            self.assertTrue(source["conflicts"])

    def test_arm_literal_identity_is_advisory_and_expressions_are_not_evaluated(self):
        inventory = source_inventory(SOURCE, Azure())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "template.json"
            path.write_text(json.dumps({"resources": [{
                "type": "Microsoft.ApiManagement/service", "name": "source",
                "resources": [{"type": "backends", "name": "literal",
                               "properties": {"url": "[parameters('endpoint')]"}}]}]}))
            source = apply_export(inventory, path, "arm", export_digest(path))
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

    def test_malformed_identity_and_network_are_explicit_destination_gaps(self):
        azure = Azure()
        azure.gateway = {"id": TARGET, "sku": {"name": "AIGateway"}, "identity": "invalid"}
        def runner(argv):
            return None if argv[2:4] == ["network", "show"] else azure(argv)
        value = destination_inventory(TARGET, runner)
        self.assertEqual({error["domain"] for error in value["errors"]}, {"identity", "network"})
        validate_schema(value, "destination-inventory")

    def test_new_destination_inventory_uses_exact_show_without_scope_enumeration(self):
        azure = Azure()
        azure.gateway = {"id": TARGET, "type": GATEWAY_TYPE, "sku": {"name": "Consumption"}}
        result = destination_inventory(TARGET, azure)
        self.assertTrue(result["exists"])
        self.assertEqual(result["collections"]["gateway"], [azure.gateway])
        self.assertEqual(result["errors"], [])
        self.assertEqual(azure.calls[0][2], "show")
        self.assertFalse(any(call[2] == "list" for call in azure.calls))

    def test_exact_not_found_plus_existing_group_establishes_absence(self):
        azure = Azure()
        result = destination_inventory(TARGET, azure)
        self.assertFalse(result["exists"])
        self.assertEqual(result["collections"]["gateway"], [])
        self.assertEqual(azure.calls[0][2], "show")
        self.assertEqual(azure.calls[1][:3], ["az", "group", "show"])
