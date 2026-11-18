[AI Gateway labs](README.md) › Release notes <!-- gh -->

# Labs release notes

What changed in the Azure AI Gateway labs for each [product release](https://ai.gateway.azure.com/docs/), and
where to practice every new feature. Newest first. 🆕 marks a new lab, ✏️ an updated lab, ✅ a lab that already
covered the feature, and ➖ a feature that no lab covers yet.

**Releases:** [November 18](#november-18-2026) · [November 12](#november-12-2026) · [November 9](#november-9-2026) · [November 6](#november-6-2026) · [October 28](#october-28-2026) · [October 16](#october-16-2026) · [October 8](#october-8-2026) · [October 1](#october-1-2026) · [September 24](#september-24-2026) · [September 10](#september-10-2026) · [August 28](#august-28-2026) · [How these notes work](#how-these-notes-work) <!-- gh -->

## November 18, 2026

### Azure AI Gateway is generally available

Azure AI Gateway is generally available. Every lab now uses the generally available portal and management API
version `2026-11-01`, and every track was retested on it.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases#release-2026-11-18).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Create a gateway, import a model, and make your first call in the generally available portal | [Quick start · Your first model call in 5 minutes](quickstart/README.md) and [01 · Provision your AI Gateway](01-provision-gateway/README.md) | ✏️ Updated |
| Manage gateways and their assets with the management API `2026-11-01` in REST and Bicep | Every lab's REST and Bicep + azd tracks, starting with [02 · Review the templates](02-first-model-call/README.md#review-the-templates) | ✏️ Updated |
| Manage gateways and their assets with the `az aigateway` extension 1.0.0b34, which calls `2026-11-01` and prints the generally available field names | Every lab's Azure CLI track, starting with [Install the `aigateway` extension](SETUP.md#install-the-aigateway-extension), and [08 · Set the policy](08-content-safety/README.md#set-the-policy), which writes content safety with `az aigateway model update --policies` | ✏️ Updated |
| Manage gateways and their assets with Terraform and the AzAPI provider at `2026-11-01` | A new **Terraform** track in the quick start and 28 labs, starting with [Deploy a lab with Terraform](SETUP.md#deploy-a-lab-with-terraform) and [01 · Provision your AI Gateway](01-provision-gateway/README.md) | ✏️ Updated |
| Providers set `modelProviderType` and a `displayName`, and a model's `supportedEndpoints` decide its API format | [02 · Publish a Foundry model and make your first call](02-first-model-call/README.md) and [03 · Publish models from any provider behind stable aliases](03-multi-provider-aliases/README.md) | ✏️ Updated |
| Tool server backends set `mode` (`failClosed` or `failOpen`), and tool lists use `blockList` | [04 · Federate MCP tools behind one endpoint](04-federate-mcp-tools/README.md) and [05 · Control which tools agents can call](05-mcp-tool-controls/README.md) | ✏️ Updated |
| Request rate limits set a `count` and a `period` | [05 · Control which tools agents can call](05-mcp-tool-controls/README.md) and [09 · Review the policy file](09-gateway-baselines/README.md#review-the-policy-file) | ✏️ Updated |
| Cost limit overrides for Microsoft Entra identities list claim `name` and `value` pairs | [07 · Give a Microsoft Entra identity its own budget](07-cost-budgets/README.md#give-a-microsoft-entra-identity-its-own-budget) | ✏️ Updated |
| Token limits and content safety policies on the generally available API | [06 · Throttle tokens per caller with token limits](06-token-limits/README.md) and [08 · Screen prompts and responses with content safety](08-content-safety/README.md) | ✏️ Updated |
| Deploy the enterprise reference architecture with the generally available templates | [21 · Review the templates](21-enterprise-reference/README.md#review-the-templates) and [21 · Apply the gateway baseline](21-enterprise-reference/README.md#apply-the-gateway-baseline) | ✏️ Updated |
| Current agent SDKs and the coding-agent plugin | [15 · Connect agent frameworks to models and tools](15-agent-frameworks/README.md), [16 · Deploy a Foundry hosted agent behind AI Gateway](16-foundry-hosted-agent/README.md), and [17 · Build on your gateway with coding agents](17-coding-agent-plugin/README.md) | ✏️ Updated |
| Import Foundry deployments filtered by resource group | [24 · Import the deployment](24-github-copilot-byok/README.md#import-the-deployment) and [25 · Import the Claude deployments](25-claude-code/README.md#import-the-claude-deployments) | ✏️ Updated |
| Back a model provider with a system- or user-assigned identity (`authentication.managedIdentity`), or an API-key header | [12 · Point the model provider at the identity](12-backend-identity/README.md#point-the-model-provider-at-the-identity) and [12 · Use stored credentials when a backend can't take a managed identity](12-backend-identity/README.md#use-stored-credentials-when-a-backend-cant-take-a-managed-identity) | ✏️ Updated |
| Telemetry exporters set `telemetryExporterType`, `{url}` endpoints, and a top-level `authentication` block | [13 · Create the telemetry exporter](13-monitoring/README.md#create-the-telemetry-exporter) and [14 · Choose the claims to export](14-otel-chargeback/README.md#choose-the-claims-to-export) | ✏️ Updated |
| Configure telemetry in the portal on a managed Log Analytics workspace | [13 · Start the setup](13-monitoring/README.md#start-the-setup) | ✏️ Updated |
| Turn off a gateway's public network access: its public endpoint returns `403` | [18 · Turn off the gateway's public network access](18-private-networking/README.md#turn-off-the-gateways-public-network-access) | ✏️ Updated |
| Request inbound private endpoints, find the gateway's private DNS zone, and reach the gateway on a private IP | [18 · Inbound private endpoints](18-private-networking/README.md#inbound-private-endpoints) and [18 · Reach the gateway through an inbound private endpoint](18-private-networking/README.md#reach-the-gateway-through-an-inbound-private-endpoint) | ✏️ Updated |
| Protect tool calls with tool threat protection on the generally available tool server shape | [19 · Add tool threat protection](19-tool-threat-protection/README.md#add-tool-threat-protection) | ✏️ Updated |
| Allow exact tool names by pattern, block tools, and suspend MCP server access | [20 · Allow the exact tool names](20-agent-365-governance/README.md#allow-the-exact-tool-names) and [20 · Block the whole server](20-agent-365-governance/README.md#block-the-whole-server) | ✏️ Updated |

## November 12, 2026

### Model failover and retry rules

Keep an alias available when a backend deployment is throttled or fails: retry the same backend, switch the request
to the next eligible model, and temporarily exclude the failing backend from later requests.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases#release-2026-11-12).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Ordered failure rules on an alias, with a CEL condition over the backend response | [29 · Turn on failover](29-model-failover/README.md#turn-on-failover) | 🆕 New lab |
| Switch a failed request to the next backend model by priority, and prove it with `x-ms-served-model` | [29 · Watch the failover](29-model-failover/README.md#watch-the-failover) | 🆕 New lab |
| Temporarily exclude a failing backend (`excludeFor`) | [29 · Check that the primary comes back](29-model-failover/README.md#check-that-the-primary-comes-back) | 🆕 New lab |
| Same-backend retries and the per-request retry limit (`retryAttempts`, `maxRetryAttempts`) | [29 · How it works](29-model-failover/README.md#how-it-works) | 🆕 New lab |
| **Failure handling** in the **Create alias** wizard and the alias editor | [29 · Add a failure rule](29-model-failover/README.md#add-a-failure-rule) | 🆕 New lab |
| Priority alone passes backend errors to the client; add failure rules to fail over | [22 · How it works](22-model-routing/README.md#how-it-works) | ✏️ Updated |
| Routing attributes and metrics in telemetry (`azure.ai_gateway.routing.*`) | [13 · Read the routing attributes](13-monitoring/README.md#read-the-routing-attributes) | ✏️ Updated |

## November 9, 2026

### Jev decisions and per-request model selection

Publish TypeSafe Jev decision models behind an alias, and let callers override auto model selection on individual
requests.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases#release-2026-11-09).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Publish TypeSafe Jev models behind a gateway alias with a Custom provider | [31 · Publish Jev behind an alias](31-jev-decisions/README.md#publish-jev-behind-an-alias) | 🆕 New lab |
| Evaluate yes/no questions, categorical choices, and scoring rubrics with native System One requests over uncompressed JSON | [31 · Send a decision request](31-jev-decisions/README.md#send-a-decision-request) | 🆕 New lab |
| Limit decision requests per caller | [31 · Limit decision requests per caller](31-jev-decisions/README.md#limit-decision-requests-per-caller) | 🆕 New lab |
| Allow callers to override the objective or narrow the model pool for one request (preview) | [28 · Let callers choose per request](28-auto-model-selection/README.md#let-callers-choose-per-request) | 🆕 New lab |
| Filter auto model selection for function-tool or request-parameter compatibility | Explained in [28 · Go further](28-auto-model-selection/README.md#go-further) | ➖ Not covered |
| Priority and weighted routing, and decision telemetry, for Jev models | Explained in [31 · Go further](31-jev-decisions/README.md#go-further) and [13 · Read the routing attributes](13-monitoring/README.md#read-the-routing-attributes) | ➖ Not covered |

## November 6, 2026

### Auto model selection, session affinity, Agent Hooks, and on-behalf-of authentication

Combine prompt-aware model selection with gateway routing, and add delegated authentication and custom governance
to MCP backends.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases#release-2026-11-06).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Choose a model for each prompt with auto model selection and a Balanced, Cost, or Quality objective (preview) | [28 · Let the gateway choose the model for each request](28-auto-model-selection/README.md) | 🆕 New lab |
| See which model served a request with `x-ms-served-model` | [28 · Send a simple and a hard prompt](28-auto-model-selection/README.md#send-a-simple-and-a-hard-prompt) | 🆕 New lab |
| Route an alias's requests by request headers or the caller with CEL backend conditions | [27 · Route research requests to the larger model](27-conditional-routing/README.md#route-research-requests-to-the-larger-model) | 🆕 New lab |
| Keep a conversation on one backend model with session affinity | [27 · Keep each session on one backend](27-conditional-routing/README.md#keep-each-session-on-one-backend) | 🆕 New lab |
| Write and check CEL expressions in the portal | [27 · Create the chat alias with a condition](27-conditional-routing/README.md#create-the-chat-alias-with-a-condition) | 🆕 New lab |
| Understand the routing order: conditions, priority, auto selection, session affinity, and weights | [22 · How it works](22-model-routing/README.md#how-it-works) and [27 · Go further](27-conditional-routing/README.md#go-further) | ✏️ Updated |
| Stateful API continuations stay pinned to their owning backend | [23 · How it works](23-streaming-responses/README.md#how-it-works) | ✏️ Updated |
| Ask your decision service before an MCP tool runs, and enforce its `allow` or `deny` verdict (Agent Hooks, preview) | [30 · Call a blocked tool](30-agent-hooks/README.md#call-a-blocked-tool) | 🆕 New lab |
| Screen tool results before they reach the agent with an after-tool-call hook | [30 · Get a result that contains a secret](30-agent-hooks/README.md#get-a-result-that-contains-a-secret) | 🆕 New lab |
| Choose fail closed or fail open when the decision service is unavailable | [30 · See the policy fail closed](30-agent-hooks/README.md#see-the-policy-fail-closed) | 🆕 New lab |
| Grant management, read, and runtime access separately with the control-plane roles | [11 · Grant control-plane access](11-entra-rbac/README.md#grant-control-plane-access) | ✏️ Updated |
| Assign runtime roles on all assets, a model alias, or an MCP server | [11 · Grant a runtime role](11-entra-rbac/README.md#grant-a-runtime-role) | ✏️ Updated |
| Mark failed model streams and MCP tool calls as `Error` in telemetry, even when the response is `200` | [13 · Find failed operations](13-monitoring/README.md#find-failed-operations) | ✏️ Updated |
| Count failed operations per caller in a chargeback report | [14 · Build a chargeback report](14-otel-chargeback/README.md#build-a-chargeback-report) | ✏️ Updated |
| Call MCP backends as the signed-in user with on-behalf-of token exchange | [33 · Connect Microsoft 365 Copilot to MCP tools as the signed-in user](33-copilot-obo-mcp/README.md), explained in [12 · Call MCP backends as the signed-in user](12-backend-identity/README.md#call-mcp-backends-as-the-signed-in-user) | 🆕 New lab |
| Edit virtual network settings after gateway creation: add, change, or remove the integration subnet | [18 · Remove and add back private routing](18-private-networking/README.md#remove-and-add-back-private-routing) and [01 · Review the template](01-provision-gateway/README.md#review-the-template) | ✏️ Updated |
| Send runtime keys as `Authorization: Bearer <key>` | [10 · Send the key in either header](10-api-keys/README.md#send-the-key-in-either-header) and [02 · How it works](02-first-model-call/README.md#how-it-works) | ✏️ Updated |
| Fixed: stream Anthropic Messages without `stream_options` failures | [25 · Ask a quick question](25-claude-code/README.md#ask-a-quick-question) | ✅ Covered |
| The new routing options, Agent Hooks, control-plane roles, and failure telemetry in the big picture | [00 · How Azure AI Gateway works](00-how-ai-gateway-works/README.md) | ✏️ Updated |

## October 28, 2026

### Embedding models

Import embedding models, publish stable aliases, and generate vectors in the portal.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases#release-2026-10-28).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Import embedding deployments from Foundry and publish them behind stable aliases | [26 · Publish embedding models for search and RAG](26-embeddings/README.md) | 🆕 New lab |
| Generate vectors with text batches and backend-supported dimensions | [26 · Generate embeddings](26-embeddings/README.md#generate-embeddings) | 🆕 New lab |
| Test embeddings in the **Catalog** playground and **Continue in code** | [26 · Test in the playground](26-embeddings/README.md#test-in-the-playground) | 🆕 New lab |
| Apply token limits and usage telemetry to embedding models | [26 · Cap ingestion with a token limit](26-embeddings/README.md#cap-ingestion-with-a-token-limit) | 🆕 New lab |
| Route an embeddings alias across deployments by priority and weight | Explained in [26 · Go further](26-embeddings/README.md#go-further), practiced with chat models in [22 · Route an alias across models by priority and weight](22-model-routing/README.md) | ➖ Not covered |

## October 16, 2026

### Priority and weighted model routing, MCP 2026-07-28

Keep a stable alias while you prefer purchased capacity, balance traffic across deployments, or test a new
model version, and manage MCP servers that use the 2026-07-28 MCP specification.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases#release-2026-10-16).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Route an alias's traffic across backend models by priority and weight | [22 · Route an alias across models by priority and weight](22-model-routing/README.md) | 🆕 New lab |
| Canary a new model version or run an A/B test with a controlled split | [22 · Split traffic 80/20 between two models](22-model-routing/README.md#split-traffic-8020-between-two-models) | 🆕 New lab |
| Prefer purchased capacity with priorities | [22 · Prefer one model by priority](22-model-routing/README.md#prefer-one-model-by-priority) | 🆕 New lab |
| Create and edit aliases with the **Create alias** wizard | [03 · Publish models from any provider behind stable aliases](03-multi-provider-aliases/README.md#give-one-backend-model-two-aliases) | ✏️ Updated |
| Choose the MCP protocol versions a server supports, including 2026-07-28 | [04 · Choose supported MCP versions](04-federate-mcp-tools/README.md#choose-supported-mcp-versions) | ✏️ Updated |
| See supported MCP versions on the server page and in **Catalog** | [04 · Check the negotiated version](04-federate-mcp-tools/README.md#check-the-negotiated-version) | ✏️ Updated |

## October 8, 2026

### Agent 365 integration and tool threat protection

Discover and govern AI Gateway MCP servers and tools from Microsoft Agent 365, and protect tool calls with
Microsoft Defender and Microsoft Purview.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases#release-2026-10-08).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Discover AI Gateway MCP servers in the Agent 365 inventory | [20 · Connect Agent 365 to your gateways](20-agent-365-governance/README.md#connect-agent-365-to-your-gateways) | ✅ Covered |
| Block or unblock MCP servers and individual tools from Agent 365 | [20 · Block a tool](20-agent-365-governance/README.md#block-a-tool) and [20 · Block the whole server](20-agent-365-governance/README.md#block-the-whole-server) | ✅ Covered |
| Evaluate tool calls before and after invocation with Defender and Purview | [19 · Add tool threat protection](19-tool-threat-protection/README.md#add-tool-threat-protection) and [19 · Understand verdicts and failures](19-tool-threat-protection/README.md#understand-verdicts-and-failures) | ✅ Covered |

## October 1, 2026

### Cost limit overrides for Microsoft Entra identities

Set different cost limit amounts for Microsoft Entra callers by identity or by an exact combination of
validated token claims.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases#release-2026-10-01).

| In the product | Practice it in the labs | Status |
|---|---|---|
| A higher or lower budget for a selected identity or matching token claims | [07 · Give a Microsoft Entra identity its own budget](07-cost-budgets/README.md#give-a-microsoft-entra-identity-its-own-budget) | ✅ Covered |
| Separate budgets per caller by tenant ID and object ID | [07 · Enforce cost budgets with per-caller overrides](07-cost-budgets/README.md) | ✅ Covered |
| The first matching override wins | [07 · How it works](07-cost-budgets/README.md#how-it-works) | ✅ Covered |

## September 24, 2026

### Model aliases, Entra access, and Chat Completions streaming usage

Aliases become the stable model contract, with Microsoft Entra authentication, gateway-scoped policies, and
complete usage for streamed Chat Completions responses.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases#release-2026-09-24).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Callable aliases, several aliases for one backend model, and retargeting | [03 · Publish models from any provider behind stable aliases](03-multi-provider-aliases/README.md) | ✅ Covered |
| Grant model and MCP access to Microsoft Entra users, groups, apps, and managed identities | [11 · Go keyless with Microsoft Entra ID and RBAC](11-entra-rbac/README.md) | ✅ Covered |
| Export selected JWT claims to OTLP logs, traces, and metrics | [14 · Choose the claims to export](14-otel-chargeback/README.md#choose-the-claims-to-export) | ✅ Covered |
| Apply one policy to every current and future asset, including a gateway-wide cost limit | [09 · Set gateway-wide policy baselines](09-gateway-baselines/README.md) | ✅ Covered |
| Usage for streamed Chat Completions responses without `include_usage` | [23 · Stream a burst without asking for usage](23-streaming-responses/README.md#stream-a-burst-without-asking-for-usage) | 🆕 New lab |

## September 10, 2026

### Per-key budget overrides and MCP tool filtering and blocking

Assign higher or lower model budgets to selected API keys, and control which MCP tools agents can discover and
invoke.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases#release-2026-09-10).

| In the product | Practice it in the labs | Status |
|---|---|---|
| A different budget for selected API keys | [07 · Give an API key a bigger budget](07-cost-budgets/README.md#give-an-api-key-a-bigger-budget) | ✅ Covered |
| Expose all, selected, or pattern-matched tools | [05 · Publish only approved tools](05-mcp-tool-controls/README.md#publish-only-approved-tools) | ✅ Covered |
| Block individual tools or a whole MCP server | [05 · Take the whole server offline](05-mcp-tool-controls/README.md#take-the-whole-server-offline) | ✅ Covered |
| Redesigned Home and first-run gateway setup | [01 · Provision your AI Gateway](01-provision-gateway/README.md) | ✅ Covered |

## August 28, 2026

### OpenTelemetry observability and model budgets

Export logs, traces, token metrics, and estimated cost metrics through OTLP, and enforce model spend with cost
limits.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases#release-2026-08-28).

| In the product | Practice it in the labs | Status |
|---|---|---|
| The built-in Application Insights dashboard and request traces | [13 · Monitor usage, cost, and traces](13-monitoring/README.md) | ✅ Covered |
| OTLP export of logs, traces, and token and cost metrics | [14 · Attribute tokens and cost with OpenTelemetry](14-otel-chargeback/README.md) | ✅ Covered |
| Cost limits with hourly to yearly budget windows | [07 · Enforce cost budgets with per-caller overrides](07-cost-budgets/README.md) | ✅ Covered |
| Import Microsoft Foundry models and onboard custom providers | [02 · Publish a Foundry model](02-first-model-call/README.md) and [03 · Add Anthropic as a custom provider](03-multi-provider-aliases/README.md#add-anthropic-as-a-custom-provider) | ✅ Covered |

## How these notes work

Each section matches one entry in the [product release notes](https://ai.gateway.azure.com/docs/), with the same
date and title, and maps every product change to the lab where you can practice it.

This file, [`labs/RELEASE-NOTES.md`](RELEASE-NOTES.md), is the source of truth: the labs site renders it at
[/release-notes/](https://azure.github.io/aigateway/release-notes/). To check for product releases that the
notes don't cover yet, run `npm run releases` in `labs/`. See [Authoring](AUTHORING.md#release-notes).
