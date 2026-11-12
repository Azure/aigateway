"""A canned ARM surface, shaped after a real APIM instance.

Covers the four shapes that matter: a passthrough MCP server, a tool-projected
MCP server over a REST API, a Foundry-backed model API behind a load-balanced
backend pool, and an ordinary REST API that must be excluded.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from apim_import.arm import ArmResponse

SUB = "00000000-0000-0000-0000-000000000000"
SERVICE = (
    f"/subscriptions/{SUB}/resourceGroups/rg-demo/providers/Microsoft.ApiManagement/service/apim-demo"
)
ACCOUNT = f"/subscriptions/{SUB}/resourceGroups/rg-demo/providers/Microsoft.CognitiveServices/accounts/aif"
WS = f"{SERVICE}/workspaces/finance"

POOL_POLICY = """<policies>
  <inbound>
    <base />
    <authentication-managed-identity resource="https://cognitiveservices.azure.com/" />
    <llm-content-safety backend-id="AI-CS-demo" shield-prompt="true">
      <categories output-type="FourSeverityLevels">
        <category name="Hate" threshold="0" />
        <category name="Violence" threshold="2" />
      </categories>
    </llm-content-safety>
    <azure-openai-token-limit counter-key="@(context.Subscription.Id)" tokens-per-minute="30000"
        estimate-prompt-tokens="false" />
    <azure-openai-emit-token-metric namespace="llm"><dimension name="Subscription" /></azure-openai-emit-token-metric>
    <llm-semantic-cache-lookup score-threshold="0.9" embeddings-backend-id="embed" />
  </inbound>
  <backend><base /></backend><outbound><base /></outbound><on-error><base /></on-error>
</policies>"""

MCP_POLICY = """<policies>
  <inbound>
    <base />
    <include-fragment fragment-id="killswitch" />
    <rate-limit-by-key calls="60" renewal-period="60" counter-key="@(context.Subscription.Id)" />
    <ip-filter action="allow"><address-range from="10.0.0.0" to="10.0.0.255" /></ip-filter>
    <set-header name="x-mcp-caller" exists-action="override"><value>gateway</value></set-header>
  </inbound>
  <backend><base /></backend><outbound><base /></outbound><on-error><base /></on-error>
</policies>"""

FRAGMENT = "<fragment><set-variable name='killswitch' value='{{MCP-KILLSWITCH}}' /></fragment>"


def _api(name, **props):
    base = {
        "displayName": name, "path": name, "protocols": ["https"], "isCurrent": True,
        "apiRevision": "1", "subscriptionRequired": True,
        "subscriptionKeyParameterNames": {"header": "Ocp-Apim-Subscription-Key", "query": "subscription-key"},
        "type": "http", "serviceUrl": None, "backendId": None,
    }
    base.update(props)
    return {"id": f"{SERVICE}/apis/{name}", "name": name, "properties": base}


APIS = [
    _api("aoai-api", backendId="aoai-pool", type="http"),
    _api(
        "support-mcp", type="mcp", backendId="support-backend",
        mcpProperties={"transportType": "streamable", "endpoints": [{"name": "mcp", "uriTemplate": "/mcp"}]},
    ),
    _api(
        "orders-mcp", type="mcp",
        mcpTools=[{"name": "list_orders", "description": "List orders",
                   "operationId": f"{SERVICE}/apis/orders-rest/operations/list_orders"}],
    ),
    _api("orders-rest", serviceUrl="https://orders.contoso.com"),
    # A model API fronting an unrecognized provider through wildcard operations:
    # no host match, no inference path, no LLM policy. Only APIM's AI import
    # naming convention gives it away.
    _api("meta-ai", backendId="meta-ai-openai-endpoint"),
    # A Foundry-hosted A2A agent. Its upstream is in jsonRpcProperties (with
    # PascalCase keys), not in a backend or serviceUrl.
    _api(
        "support-agent", type="a2a", isAgent=True,
        a2aProperties={
            "agentCardBackendUrl": (
                "https://aif.services.ai.azure.com/api/projects/default-project/agents"
                "/support-bot/endpoint/protocols/a2a/.well-known/agent-card.json"
            ),
            "agentCardPath": "/agent-card.json",
        },
        agent={"id": "support-bot", "name": None, "providerName": None, "managementPortalUrl": None},
        jsonRpcProperties={
            "BackendUrl": (
                "https://aif.services.ai.azure.com/api/projects/default-project/agents"
                "/support-bot/endpoint/protocols/a2a/"
            ),
            "Path": "/",
        },
    ),
]

BACKENDS = [
    {
        "id": f"{SERVICE}/backends/aoai-pool", "name": "aoai-pool",
        "properties": {
            "type": "Pool",
            "pool": {"services": [
                {"id": f"{SERVICE}/backends/aoai-east", "priority": 1, "weight": 80},
                {"id": f"{SERVICE}/backends/aoai-west", "priority": 2, "weight": 20},
            ]},
        },
    },
    {
        "id": f"{SERVICE}/backends/aoai-east", "name": "aoai-east",
        "properties": {
            "type": "Single", "protocol": "http", "url": "https://aif.openai.azure.com/",
            # APIM stores this as a management URI, not a bare ARM id.
            "resourceId": f"https://management.azure.com{ACCOUNT}",
            # Undocumented in the published ARM schema, but what the portal's
            # AI API import actually writes for a Foundry backend.
            "credentials": {"managedIdentity": {"clientId": None,
                                                "resource": "https://cognitiveservices.azure.com/"}},
            "circuitBreaker": {"rules": [{"name": "trip", "tripDuration": "PT1M"}]},
        },
    },
    {
        "id": f"{SERVICE}/backends/aoai-west", "name": "aoai-west",
        "properties": {
            "type": "Single", "protocol": "http", "url": "https://aif-west.openai.azure.com/",
            "credentials": {"header": {"api-key": ["{{aoai-key}}"]}},
        },
    },
    {
        # An Azure AI Content Safety endpoint. Same host shape as a Foundry model
        # host, but it serves no models; only the policy says what it is for.
        "id": f"{SERVICE}/backends/AI-CS-demo", "name": "AI-CS-demo",
        "properties": {"type": "Single", "protocol": "http",
                       "url": "https://apim-demo.cognitiveservices.azure.com/",
                       "credentials": {"managedIdentity": {"clientId": None,
                                                           "resource": "https://cognitiveservices.azure.com/"}}},
    },
    {
        "id": f"{SERVICE}/backends/meta-ai-openai-endpoint", "name": "meta-ai-openai-endpoint",
        "properties": {
            "type": "Single", "protocol": "http", "url": "https://api.meta.ai",
            "credentials": {"header": {"Authorization": ["{{meta-ai-Authorization-LLM}}"]}},
        },
    },
    {
        "id": f"{SERVICE}/backends/support-backend", "name": "support-backend",
        "properties": {"type": "Single", "protocol": "http", "url": "https://support.contoso.com:8000",
                       "credentials": {"header": {"x-api-key": ["sk-abcdefghijklmnopqrstuvwxyz01"]}}},
    },
]

NAMED_VALUES = [
    {"id": f"{SERVICE}/namedValues/aoai-key", "name": "aoai-key",
     "properties": {"displayName": "aoai-key", "secret": True}},
    {"id": f"{SERVICE}/namedValues/kv-key", "name": "kv-key",
     "properties": {"displayName": "kv-key", "secret": True,
                    "keyVault": {"secretIdentifier": "https://v.vault.azure.net/secrets/k"}}},
    {"id": f"{SERVICE}/namedValues/MCP-KILLSWITCH", "name": "MCP-KILLSWITCH",
     "properties": {"displayName": "MCP-KILLSWITCH", "secret": False, "value": "off"}},
    {"id": f"{SERVICE}/namedValues/meta-ai-Authorization-LLM", "name": "meta-ai-Authorization-LLM",
     "properties": {"displayName": "meta-ai-Authorization-LLM", "secret": True}},
]

ROUTES: dict[str, Any] = {
    SERVICE: {
        "id": SERVICE, "name": "apim-demo", "location": "West US 2",
        "sku": {"name": "StandardV2", "capacity": 1},
        "identity": {"type": "SystemAssigned", "principalId": "p-1", "tenantId": "t-1"},
        "properties": {
            "provisioningState": "Succeeded", "gatewayUrl": "https://apim-demo.azure-api.net",
            "virtualNetworkType": "None", "publicNetworkAccess": "Enabled",
            "hostnameConfigurations": [{"type": "Proxy", "hostName": "apim-demo.azure-api.net",
                                        "certificateSource": "BuiltIn"}],
        },
    },
    f"{SERVICE}/workspaces": [
        {"id": f"{SERVICE}/workspaces/finance", "name": "finance",
         "properties": {"displayName": "finance", "description": "", "serveOn": "workspaceAndDefault"}}
    ],
    # A workspace holds its own APIs, backends, and named values. A unified model
    # API declares its models through languageModel backends rather than through
    # any host or path heuristic.
    f"{SERVICE}/workspaces/finance/apis": [
        {"id": f"{WS}/apis/model-api", "name": "model-api",
         "properties": {"displayName": "Model API", "path": "llm/v1", "protocols": ["https"],
                        "isCurrent": True, "apiRevision": "1", "subscriptionRequired": True,
                        "type": "unifiedModelApi", "backendId": "claude-backend",
                        "serviceUrl": None,
                        "subscriptionKeyParameterNames": {"header": "api-key",
                                                          "query": "subscription-key"}}}
    ],
    f"{SERVICE}/workspaces/finance/apis/model-api/operations": [
        {"id": f"{WS}/apis/model-api/operations/chat", "name": "chat",
         "properties": {"displayName": "chat", "method": "POST", "urlTemplate": "/chat/completions"}},
        {"id": f"{WS}/apis/model-api/operations/models", "name": "models",
         "properties": {"displayName": "models", "method": "GET", "urlTemplate": "/models"}},
    ],
    f"{SERVICE}/workspaces/finance/backends": [
        {"id": f"{WS}/backends/claude-backend", "name": "claude-backend",
         "properties": {"type": "languageModel", "protocol": "http",
                        "url": "https://demo.services.ai.azure.com/anthropic",
                        "languageModel": {"apiFormat": "anthropic-messages", "model": "claude-opus-5"},
                        "credentials": {"header": {"api-key": ["{{claude-key}}"]}}}}
    ],
    f"{SERVICE}/workspaces/finance/namedValues": [
        {"id": f"{WS}/namedValues/claude-key", "name": "claude-key",
         "properties": {"displayName": "claude-key", "secret": True}}
    ],
    f"{SERVICE}/workspaces/finance/products": [],
    f"{SERVICE}/workspaces/finance/subscriptions": [],
    f"{SERVICE}/workspaces/finance/policyFragments": [],
    f"{SERVICE}/apis": APIS,
    f"{SERVICE}/backends": BACKENDS,
    f"{SERVICE}/namedValues": NAMED_VALUES,
    f"{SERVICE}/policyFragments": [
        {"id": f"{SERVICE}/policyFragments/killswitch", "name": "killswitch",
         "properties": {"description": "kill switch", "value": FRAGMENT}}
    ],
    f"{SERVICE}/products": [
        {"id": f"{SERVICE}/products/ai", "name": "ai",
         "properties": {"displayName": "AI", "state": "published", "subscriptionRequired": True}}
    ],
    f"{SERVICE}/products/ai/apis": [{"id": f"{SERVICE}/apis/aoai-api", "name": "aoai-api"}],
    f"{SERVICE}/subscriptions": [
        {"id": f"{SERVICE}/subscriptions/team-a", "name": "team-a",
         "properties": {"displayName": "Team A", "state": "active", "scope": f"{SERVICE}/products/ai"}},
        {"id": f"{SERVICE}/subscriptions/master", "name": "master",
         "properties": {"displayName": "All access", "state": "active", "scope": f"{SERVICE}/"}},
    ],
    f"{SERVICE}/certificates": [],
    f"{SERVICE}/authorizationServers": [],
    f"{SERVICE}/openidConnectProviders": [],
    f"{SERVICE}/authorizationProviders": [],
    f"{SERVICE}/loggers": [],
    f"{SERVICE}/diagnostics": [],
    # A real Azure OpenAI import publishes far more than inference: assistants,
    # threads and vector stores come along and have no target at all.
    f"{SERVICE}/apis/aoai-api/operations": [
        {"id": f"{SERVICE}/apis/aoai-api/operations/chat", "name": "chat",
         "properties": {"displayName": "chat", "method": "POST",
                        "urlTemplate": "/deployments/{deployment-id}/chat/completions"}},
        {"id": f"{SERVICE}/apis/aoai-api/operations/embeddings", "name": "embeddings",
         "properties": {"displayName": "embeddings", "method": "POST",
                        "urlTemplate": "/deployments/{deployment-id}/embeddings"}},
        {"id": f"{SERVICE}/apis/aoai-api/operations/threads", "name": "threads",
         "properties": {"displayName": "create thread", "method": "POST",
                        "urlTemplate": "/threads?api-version={api-version}"}},
        {"id": f"{SERVICE}/apis/aoai-api/operations/thread_runs", "name": "thread_runs",
         "properties": {"displayName": "create run", "method": "POST",
                        "urlTemplate": "/threads/{thread_id}/runs?api-version={api-version}"}},
        {"id": f"{SERVICE}/apis/aoai-api/operations/assistants", "name": "assistants",
         "properties": {"displayName": "list assistants", "method": "GET",
                        "urlTemplate": "/assistants?api-version={api-version}"}},
        {"id": f"{SERVICE}/apis/aoai-api/operations/vs", "name": "vs",
         "properties": {"displayName": "vector stores", "method": "GET",
                        "urlTemplate": "/vector_stores?api-version={api-version}"}},
    ],
    f"{SERVICE}/apis/orders-rest/operations": [
        {"id": f"{SERVICE}/apis/orders-rest/operations/list_orders", "name": "list_orders",
         "properties": {"displayName": "list orders", "method": "GET", "urlTemplate": "/orders"}}
    ],
    f"{SERVICE}/apis/meta-ai/operations": [
        {"id": f"{SERVICE}/apis/meta-ai/operations/all", "name": "all",
         "properties": {"displayName": "passthrough", "method": "POST", "urlTemplate": "/*"}}
    ],
    f"{SERVICE}/apis/orders-mcp/tools": [
        {"id": f"{SERVICE}/apis/orders-mcp/tools/t1", "name": "t1",
         "properties": {"displayName": "list_orders", "description": "List orders",
                        "operationId": f"{SERVICE}/apis/orders-rest/operations/list_orders", "policies": None}}
    ],
    f"{SERVICE}/apis/support-mcp/tools": [],
    f"/subscriptions/{SUB}/providers/Microsoft.CognitiveServices/accounts": [
        {"id": ACCOUNT, "name": "aif", "location": "westus3", "kind": "AIServices", "sku": {"name": "S0"},
         "properties": {"endpoint": "https://aif.cognitiveservices.azure.com/",
                        # A real AIServices account advertises many endpoints across
                        # several hostnames; agent and model traffic use different ones.
                        "endpoints": {"OpenAI": "https://aif.openai.azure.com/",
                                      "AI Foundry API": "https://aif.services.ai.azure.com/"},
                        "customSubDomainName": "aif", "disableLocalAuth": False,
                        "publicNetworkAccess": "Enabled"}}
    ],
    f"{ACCOUNT}/deployments": [
        {"id": f"{ACCOUNT}/deployments/gpt-5", "name": "gpt-5",
         "properties": {"model": {"format": "OpenAI", "name": "gpt-5.2", "version": "2025-12-11"},
                        "provisioningState": "Succeeded", "raiPolicyName": "DefaultLight"},
         "sku": {"name": "GlobalStandard", "capacity": 15000}}
    ],
}

POLICIES = {
    f"{SERVICE}/apis/aoai-api": POOL_POLICY,
    f"{SERVICE}/apis/support-mcp": MCP_POLICY,
    f"{SERVICE}/apis/orders-mcp": MCP_POLICY,
}


class FakeArmClient:
    """Implements only the surface the collector uses."""

    def __init__(self) -> None:
        self.call_count = 0
        self.requested: list[str] = []

    def _path(self, url: str) -> str:
        return urlsplit(url).path if url.startswith("http") else url.split("?", 1)[0]

    def request(self, method, url, *, api_version=None, params=None, accept="application/json") -> ArmResponse:
        self.call_count += 1
        path = self._path(url)
        self.requested.append(path)
        if path in ROUTES and isinstance(ROUTES[path], dict):
            return ArmResponse(200, ROUTES[path], "")
        return ArmResponse(404, {"error": {"code": "ResourceNotFound", "message": path}}, "")

    def list(self, url, api_version, **params) -> list[dict]:
        self.call_count += 1
        path = self._path(url)
        self.requested.append(path)
        value = ROUTES.get(path)
        return list(value) if isinstance(value, list) else []

    def get_json(self, url, api_version, **params):
        response = self.request("GET", url, api_version=api_version)
        return response.body if response.ok else None

    def get_policy(self, scope_url, api_version, policy_name="policy"):
        self.call_count += 1
        xml = POLICIES.get(self._path(scope_url))
        return {"format": "rawxml", "value": xml} if xml else None
