"""AI source discovery across public protocols and scoped routing dependencies."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import MigrationError, validate_schema
from inventory import apply_export, export_digest, source_inventory
from fixtures import Azure, SOURCE


def fixture(paths=(), properties=None, scope=SOURCE):
    azure = Azure()
    if scope != SOURCE:
        azure.collections[SOURCE + "/workspaces"] = {"value": [{"id": scope}]}
    api = scope + "/apis/frontend"
    azure.collections[scope + "/apis"] = {"value": [{
        "id": api, "properties": {"type": "http", **(properties or {})}}]}
    azure.collections[api + "/operations"] = {"value": [
        {"id": api + "/operations/op-" + str(index),
         "properties": {"method": method, "urlTemplate": path}}
        for index, (method, path) in enumerate(paths)]}
    return azure, api


def add_policy(azure, parent, xml, domain="policies"):
    collection = parent + "/" + domain
    azure.collections[collection] = {"value": [
        {"id": collection + "/policy", "properties": {"value": xml}}]}


def record(source, identifier):
    return next(item for item in source["items"] if item["id"] == identifier)


class AIInventoryTests(unittest.TestCase):
    def test_mcp_inventory_preserves_configuration_and_resolves_tools_and_backends(self):
        azure, api = fixture([("POST", "/invoke")], {
            "type": "http",
            "backendId": "upstream",
            "mcpProperties": {"transportType": "streamable", "endpoints": {
                "custom-endpoint": {"uriTemplate": "/toolservers/demo/mcp?code=NEVER_PERSIST"}}},
        })
        backend = SOURCE + "/backends/upstream"
        operation = api + "/operations/op-0"
        tool = api + "/tools/run"
        azure.collections[SOURCE + "/backends"] = {"value": [{"id": backend}]}
        azure.collections[backend] = {"id": backend, "properties": {
            "url": "https://tools.example", "credentials": {
                "header": {"x-functions-key": "SECRET"},
                "authorization": {"scheme": "Bearer", "parameter": "AUTH_SECRET"},
                "certificateIds": ["client-cert"], "certificate": ["thumbprint"]}}
        }
        policy = api + "/policies/policy"
        azure.collections[api + "/policies"] = {"value": [{"id": policy}]}
        azure.collections[policy] = {"id": policy, "properties": {"value":
            '<policies><inbound><set-backend-service backend-id="upstream"/>'
            '<rewrite-uri template="/version?key=NEVER_PERSIST"/></inbound></policies>'}}
        azure.collections[api + "/tools"] = {"value": [{"id": tool, "properties": {
            "displayName": "run_tool", "description": "Run a tool", "operationId": "/apis/frontend/operations/op-0"}}]}

        source = source_inventory(SOURCE, azure)
        api_item = record(source, api)
        config = api_item["facts"]["mcpConfiguration"]
        self.assertEqual(api_item["facts"]["role"], "mcp")
        self.assertEqual(config["transportType"], "streamable")
        self.assertEqual(config["endpoints"], [{
            "name": "custom-endpoint", "uriTemplate": "/toolservers/demo/mcp?code=%5Bredacted%5D"}])
        self.assertEqual(config["backend"]["id"], backend)
        self.assertEqual(config["backend"]["headerNames"], ["x-functions-key"])
        self.assertEqual(config["backend"]["authorizationScheme"], "Bearer")
        self.assertTrue(config["backend"]["authorizationParameterPresent"])
        self.assertEqual(config["backend"]["certificateReferenceIds"], ["client-cert"])
        self.assertEqual(config["backend"]["certificateReferenceCount"], 2)
        self.assertEqual(config["policyBackends"][0]["backendId"], backend)
        policy_shape = record(source, policy)["policyShape"]
        rewrite = next(node for node in policy_shape if node["statement"] == "rewrite-uri")
        self.assertEqual(rewrite["routing"]["uriTemplate"], "/version?key=%5Bredacted%5D")
        self.assertEqual(config["tools"][0]["resolvedOperationId"], operation)
        self.assertNotIn("NEVER_PERSIST", json.dumps(source))
        self.assertNotIn("SECRET", json.dumps(source))
        self.assertNotIn("thumbprint", json.dumps(source))
        self.assertNotIn("SECRET", json.dumps(source))
        validate_schema(source, "source-inventory")

    def test_mcp_endpoint_array_and_unresolved_tool_links_are_retained(self):
        azure, api = fixture([], {"type": "mcp", "mcpProperties": {
            "transportType": "sse",
            "endpoints": [{"name": "events", "uriTemplate": "/events"},
                          {"name": "messages", "uriTemplate": "/messages"}]}})
        azure.collections[api + "/tools"] = {"value": [{"id": api + "/tools/search",
            "properties": {"displayName": "search", "operationId": "/apis/other/operations/search"}}]}
        source = source_inventory(SOURCE, azure)
        config = record(source, api)["facts"]["mcpConfiguration"]
        self.assertEqual(config["endpoints"], [
            {"name": "events", "uriTemplate": "/events"},
            {"name": "messages", "uriTemplate": "/messages"},
        ])
        self.assertEqual(config["tools"][0]["operationResolution"], "unresolved")
        self.assertTrue(next(item for item in source["coverage"]
                             if item["scope"] == api and item["domain"] == "api-tools")["establishesCompleteness"])

    def test_rest_exported_mcp_links_backing_api_backend_policies_and_published_endpoint(self):
        azure, mcp_api = fixture([], {"type": "mcp", "path": "echo-mcp"})
        azure.source["properties"]["gatewayUrl"] = "https://apim.example"
        rest_api = SOURCE + "/apis/echo"
        operation = rest_api + "/operations/get"
        backend = SOURCE + "/backends/echo-backend"
        azure.collections[SOURCE + "/apis"]["value"].append({"id": rest_api, "properties": {
            "type": "http", "path": "echo", "serviceUrl": "https://echo.example/api",
            "backendId": "echo-backend"}})
        azure.collections[rest_api + "/operations"] = {"value": [
            {"id": operation, "properties": {"method": "GET", "urlTemplate": "/resource"}}]}
        azure.collections[SOURCE + "/backends"] = {"value": [{"id": backend}]}
        azure.collections[backend] = {"id": backend, "properties": {
            "url": "https://echo.example/api", "credentials": {"header": {"x-key": "SECRET"}}}}
        add_policy(azure, operation, "<policies><inbound><cache-lookup/></inbound></policies>")
        azure.collections[mcp_api + "/tools"] = {"value": [{"id": mcp_api + "/tools/get",
            "properties": {"displayName": "getResource", "operationId": operation}}]}

        source = source_inventory(SOURCE, azure)
        config = record(source, mcp_api)["facts"]["mcpConfiguration"]
        self.assertIsNone(config["backend"])
        self.assertEqual(len(config["restSources"]), 1)
        rest = config["restSources"][0]
        self.assertEqual((rest["apiId"], rest["serviceUrl"], rest["operationIds"]),
                         (rest_api, "https://echo.example/api", [operation]))
        self.assertEqual((rest["backend"]["id"], rest["backend"]["headerNames"]), (backend, ["x-key"]))
        self.assertIn(operation + "/policies/policy", config["policySourceIds"])
        self.assertEqual(config["publishedEndpoint"]["url"], "https://apim.example/echo-mcp/mcp")
        self.assertNotIn("SECRET", json.dumps(source))
        validate_schema(source, "source-inventory")

    def test_tool_associations_are_discovered_on_non_mcp_api_types(self):
        azure, api = fixture([], {"type": "http"})
        azure.collections[api + "/tools"] = {"value": [{"id": api + "/tools/search",
            "properties": {"displayName": "search", "operationId": "/apis/frontend/operations/missing"}}]}
        source = source_inventory(SOURCE, azure)
        item = record(source, api)
        self.assertEqual(item["facts"]["role"], "mcp")
        self.assertEqual(item["facts"]["mcpConfiguration"]["tools"][0]["operationResolution"], "unresolved")

    def test_inference_protocols_include_azure_deployments_versions_and_source_only_operations(self):
        cases = {
            "/chat/completions": "/chat/completions",
            "/v1/chat/completions": "/chat/completions",
            "/openai/v1/chat/completions": "/chat/completions",
            "/openai/deployments/{deployment-id}/chat/completions?api-version={api-version}": "/chat/completions",
            "/deployments/production/embeddings?api-version=2024-06-01": "/embeddings",
            "/openai/responses?api-version={api-version}": "/responses",
            "/models/chat/completions?api-version=2024-05-01-preview": "/chat/completions",
            "/openai/deployments/{deployment}/images/generations": "/images/generations",
            "/v1/audio/transcriptions": "/audio/transcriptions",
            "/v1/images/edits": "/images/edits",
            "/anthropic/v1/messages": "/messages",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                azure, api = fixture([("POST", path), ("GET", "/openai/files")])
                source = source_inventory(SOURCE, azure)
                self.assertEqual(record(source, api)["facts"]["role"], "model-protocol")
                operation = record(source, api + "/operations/op-0")
                self.assertEqual(operation["facts"]["modelOperation"], expected)
                self.assertEqual(record(source, api)["facts"]["modelProtocolPaths"], [path.split("?")[0]])
                self.assertNotIn("modelOperation", record(source, api + "/operations/op-1")["facts"])
                self.assertEqual(record(source, api)["facts"]["operationCount"], 2)
                validate_schema(source, "source-inventory")

    def test_direct_and_backend_endpoints_identify_ai_even_behind_opaque_public_paths(self):
        for endpoint in ("https://account.services.ai.azure.com/",
                         "https://account.openai.azure.com/openai",
                         "https://account.privatelink.openai.azure.com/",
                         "https://account.openai.azure.us/",
                         "https://deployment.eastus.models.ai.azure.com/",
                         "https://deployment.inference.ai.azure.com/",
                         "https://api.openai.com/v1",
                         "https://api.openai.com/v1?sig=HIDDEN",
                         "https://private.example/v1/chat/completions"):
            for use_backend in (False, True):
                with self.subTest(endpoint=endpoint, backend=use_backend):
                    props = {"backendId": "upstream"} if use_backend else {"serviceUrl": endpoint}
                    azure, api = fixture([("POST", "/invoke"), ("GET", "/*")], props)
                    if use_backend:
                        azure.collections[SOURCE + "/backends"] = {"value": [{
                            "id": SOURCE + "/backends/upstream", "properties": {"url": endpoint}}]}
                    source = source_inventory(SOURCE, azure)
                    facts = record(source, api)["facts"]
                    self.assertEqual(facts["role"], "model-protocol")
                    self.assertTrue(facts["roleEstablished"])
                    self.assertEqual(facts["modelProtocolPaths"], [])
                    self.assertTrue(facts["modelEvidence"])
                    self.assertNotIn("HIDDEN", json.dumps(source))

    def test_routing_follows_scoped_fragments_pools_and_all_member_boundaries(self):
        for scope in (SOURCE, SOURCE + "/workspaces/team"):
            with self.subTest(scope=scope):
                azure, api = fixture([("POST", "/invoke")], scope=scope)
                add_policy(azure, api, '<policies><inbound><include-fragment fragment-id="route"/></inbound></policies>')
                fragment = scope + "/policyFragments/route"
                azure.collections[scope + "/policyFragments"] = {"value": [
                    {"id": fragment, "properties": {"value": '<fragment><set-backend-service backend-id="pool"/>'
                     '<include-fragment fragment-id="route"/></fragment>'}}]}
                backends = [{"id": scope + "/backends/pool", "properties": {
                    "type": "Pool", "pool": {"services": [
                        {"id": scope + "/backends/first", "priority": 1, "weight": 40},
                        {"id": scope + "/backends/second", "priority": 1, "weight": 60}]}}},
                    {"id": scope + "/backends/first", "properties": {"url": "https://one.openai.azure.com"}},
                    {"id": scope + "/backends/second", "properties": {"url": "https://two.services.ai.azure.com"}}]
                azure.collections[scope + "/backends"] = {"value": backends}
                if scope != SOURCE:
                    azure.collections[SOURCE + "/backends"] = {"value": [{
                        "id": SOURCE + "/backends/first", "properties": {"url": "https://unrelated.openai.azure.com"}}]}
                source = source_inventory(SOURCE, azure)
                facts = record(source, api)["facts"]
                self.assertEqual(facts["role"], "model-protocol")
                self.assertEqual({entry["sourceId"] for entry in facts["modelEvidence"]},
                                 {scope + "/backends/first", scope + "/backends/second"})
                self.assertEqual(facts["unresolvedModelRouting"], [])

    def test_policy_evidence_uses_inheritance_and_operation_and_product_scopes(self):
        for level in ("service", "product", "api", "operation"):
            with self.subTest(level=level):
                azure, api = fixture([("POST", "/invoke")])
                parent = {"service": SOURCE, "product": SOURCE + "/products/tools",
                          "api": api, "operation": api + "/operations/op-0"}[level]
                if level == "product":
                    azure.collections[SOURCE + "/products"] = {"value": [{"id": parent}]}
                    azure.collections[parent + "/apis"] = {"value": [{"id": api}]}
                add_policy(azure, parent, '<policies><inbound><set-backend-service '
                           'base-url="https://account.services.ai.azure.com/"/></inbound></policies>')
                source = source_inventory(SOURCE, azure)
                self.assertEqual(record(source, api)["facts"]["role"], "model-protocol")
                if level in ("service", "product"):
                    add_policy(azure, api, '<policies><inbound><set-header name="x-local">'
                               '<value>not-ai</value></set-header></inbound></policies>')
                    source = source_inventory(SOURCE, azure)
                    self.assertEqual(record(source, api)["facts"]["role"], "rest")
                    add_policy(azure, api, "<policies><inbound><base/></inbound></policies>")
                    source = source_inventory(SOURCE, azure)
                    self.assertEqual(record(source, api)["facts"]["role"], "model-protocol")

    def test_ai_policies_and_protocol_rewrites_discover_private_or_aliased_routes(self):
        for xml in ('<azure-openai-token-limit tokens-per-minute="100"/>',
                    '<llm-token-limit tokens-per-minute="100"/>',
                    '<rewrite-uri template="/openai/deployments/private/chat/completions?api-version=2024-06-01"/>'):
            with self.subTest(xml=xml):
                azure, api = fixture([("POST", "/invoke")], {"serviceUrl": "https://private.example"})
                add_policy(azure, api, "<policies><inbound>" + xml + "</inbound></policies>")
                source = source_inventory(SOURCE, azure)
                self.assertEqual(record(source, api)["facts"]["role"], "model-protocol")
                self.assertNotIn("modelOperation", record(source, api + "/operations/op-0")["facts"])

    def test_routing_named_values_are_not_secrets_or_evaluated_expressions(self):
        for secret in (False, True):
            with self.subTest(secret=secret):
                azure, api = fixture([("POST", "/invoke")], {"backendId": "upstream"})
                azure.collections[SOURCE + "/backends"] = {"value": [{
                    "id": SOURCE + "/backends/upstream", "properties": {"url": "{{endpoint}}"}}]}
                azure.collections[SOURCE + "/namedValues"] = {"value": [{
                    "id": SOURCE + "/namedValues/endpoint-record",
                    "properties": {"displayName": "endpoint", "secret": secret,
                                   "value": "https://private.services.ai.azure.com/?sig=HIDDEN"}}]}
                source = source_inventory(SOURCE, azure)
                facts = record(source, api)["facts"]
                self.assertEqual(facts["role"], "rest" if secret else "model-protocol")
                self.assertTrue(facts["unresolvedModelRouting"])
                self.assertNotIn("HIDDEN", json.dumps(source))
                self.assertFalse(any("listValue" in str(call) for call in azure.calls))
        azure, api = fixture([("POST", "/invoke")])
        add_policy(azure, api, '<policies><inbound><set-backend-service '
                   'backend-id="@(&quot;upstream&quot;)"/></inbound></policies>')
        source = source_inventory(SOURCE, azure)
        self.assertEqual(record(source, api)["facts"]["role"], "rest")
        self.assertTrue(record(source, api)["facts"]["unresolvedModelRouting"])
        azure, api = fixture([("POST", "/invoke")])
        add_policy(azure, api, '<policies><inbound><set-header name="x-unrelated">'
                   '<value>{{endpoint}}</value></set-header></inbound></policies>')
        azure.collections[SOURCE + "/namedValues"] = {"value": [{
            "id": SOURCE + "/namedValues/endpoint",
            "properties": {"secret": False, "value": "https://account.openai.azure.com"}}]}
        self.assertEqual(record(source_inventory(SOURCE, azure), api)["facts"]["role"], "rest")

    def test_account_identity_is_a_discovery_lead_not_proof_of_model_or_inference_support(self):
        account = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/models"
        for resource_id in (account, "https://management.azure.com" + account):
            with self.subTest(resource_id=resource_id):
                azure, api = fixture([("POST", "/invoke")], {"backendId": "private"})
                azure.collections[SOURCE + "/backends"] = {"value": [{
                    "id": SOURCE + "/backends/private", "properties": {
                        "url": "https://private.example", "resourceId": resource_id}}]}
                source = source_inventory(SOURCE, azure)
                facts = record(source, api)["facts"]
                self.assertEqual(facts["role"], "model-candidate")
                self.assertFalse(facts["roleEstablished"])
                self.assertEqual(facts["modelEvidence"][0]["resourceId"], account)

    def test_names_lookalike_hosts_wildcards_and_management_operations_are_not_inference(self):
        for properties, method, path in (
                ({"displayName": "OpenAI Foundry"}, "GET", "/models"),
                ({"serviceUrl": "https://api.openai.com.attacker.example"}, "POST", "/invoke"),
                ({"serviceUrl": "https://notopenai.azure.com"}, "POST", "/invoke"),
                ({}, "POST", "/*"),
                ({}, "GET", "/chat/completions"),
                ({}, "GET", "/openai/responses/{response_id}"),
                ({}, "DELETE", "/openai/responses/{response_id}"),
                ({}, "POST", "/openai/deployments/*/chat/completions"),
                ({}, "POST", "/unrelated/chat/completions")):
            with self.subTest(properties=properties, method=method, path=path):
                azure, api = fixture([(method, path)], properties)
                source = source_inventory(SOURCE, azure)
                self.assertNotEqual(record(source, api)["facts"]["role"], "model-protocol")
                self.assertNotIn("modelOperation", record(source, api + "/operations/op-0")["facts"])
        azure, api = fixture([("POST", "/chat/completions")], {"type": "mcp"})
        self.assertEqual(record(source_inventory(SOURCE, azure), api)["facts"]["role"], "mcp")

    def test_ai_evidence_never_repairs_missing_backend_coverage(self):
        for result in (MigrationError("Forbidden."), {"value": [{
                "id": SOURCE + "/backends/missing",
                "properties": {"pool": {"services": [{"priority": 1}]}}}]}):
            with self.subTest(result=result):
                azure, api = fixture([("POST", "/openai/responses")], {"backendId": "missing"})
                azure.collections[SOURCE + "/backends"] = result
                source = source_inventory(SOURCE, azure)
                self.assertEqual(record(source, api)["facts"]["role"], "model-protocol")
                self.assertTrue(record(source, api)["facts"]["unresolvedModelRouting"])
                coverage = next(entry for entry in source["coverage"] if entry["domain"] == "backends")
                self.assertFalse(coverage["establishesCompleteness"])

    def test_export_recovery_reclassifies_without_stale_or_duplicate_evidence(self):
        azure, api = fixture([("POST", "/invoke")], {"backendId": "upstream"})
        azure.collections[SOURCE + "/backends"] = MigrationError("Forbidden.")
        source = source_inventory(SOURCE, azure)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "backends/upstream/backendInformation.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"properties": {"url": "https://account.openai.azure.com"}}))
            apply_export(source, root, "apiops", export_digest(root))
            self.assertEqual(record(source, api)["facts"]["role"], "model-protocol")
            before = copy.deepcopy(record(source, api)["facts"])
            apply_export(source, root, "apiops", export_digest(root))
            self.assertEqual(record(source, api)["facts"], before)
            self.assertEqual(record(source, SOURCE + "/backends/upstream")["authority"], "advisory")
            validate_schema(source, "source-inventory")


if __name__ == "__main__":
    unittest.main()
