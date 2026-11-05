[AI Gateway labs](README.md) › Release notes <!-- gh -->

# Labs release notes

What changed in the Azure AI Gateway labs for each [product release](https://ai.gateway.azure.com/docs/), and
where to practice every new feature. Newest first. 🆕 marks a new lab, ✏️ an updated lab, ✅ a lab that already
covered the feature, and ➖ a feature that no lab covers yet.

**Releases:** [October 16](#october-16-2026) · [October 8](#october-8-2026) · [October 1](#october-1-2026) · [September 24](#september-24-2026) · [September 10](#september-10-2026) · [August 28](#august-28-2026) · [How these notes work](#how-these-notes-work) <!-- gh -->

## October 16, 2026

### Priority and weighted model routing, MCP 2026-07-28

Keep a stable alias while you prefer purchased capacity, balance traffic across deployments, or test a new
model version, and manage MCP servers that use the 2026-07-28 MCP specification.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-10-16).

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
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-10-08).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Discover AI Gateway MCP servers in the Agent 365 inventory | [20 · Connect Agent 365 to your gateways](20-agent-365-governance/README.md#connect-agent-365-to-your-gateways) | ✅ Covered |
| Block or unblock MCP servers and individual tools from Agent 365 | [20 · Block a tool](20-agent-365-governance/README.md#block-a-tool) | ✅ Covered |
| Evaluate tool calls before and after invocation with Defender and Purview | [19 · Protect tool calls with Agent 365 threat protection](19-tool-threat-protection/README.md) | ✅ Covered |

## October 1, 2026

### Cost limit overrides for Microsoft Entra identities

Set different cost limit amounts for Microsoft Entra callers by identity or by an exact combination of
validated token claims.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-10-01).

| In the product | Practice it in the labs | Status |
|---|---|---|
| A higher or lower budget for a selected identity or matching token claims | [07 · Give a Microsoft Entra identity its own budget](07-cost-budgets/README.md#give-a-microsoft-entra-identity-its-own-budget) | ✅ Covered |
| Separate budgets per caller by tenant ID and object ID | [07 · Enforce cost budgets with per-caller overrides](07-cost-budgets/README.md) | ✅ Covered |
| The first matching override wins | [07 · How it works](07-cost-budgets/README.md#how-it-works) | ✅ Covered |

## September 24, 2026

### Model aliases, Entra access, and Chat Completions streaming usage

Aliases become the stable model contract, with Microsoft Entra authentication, gateway-scoped policies, and
complete usage for streamed Chat Completions responses.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-09-24).

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
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-09-10).

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
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-08-28).

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
