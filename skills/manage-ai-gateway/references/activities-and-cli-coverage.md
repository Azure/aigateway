# Native capability inventory

Command surface and known limitations for `Microsoft.ApiManagement/aigateways` (CLI `1.0.0b26`, API `2025-09-01-preview`).

## Administrator task to CLI command group

| Administrator task | `az aigateway` command group | Reference |
| --- | --- | --- |
| Create, show, list, retag, set SKU, wait, or delete a gateway | Top-level `create`, `show`, `list`, `update`, `delete`, `wait`, `version` | [gateway-lifecycle.md](gateway-lifecycle.md) |
| Onboard Foundry/Custom providers and reconcile deployments | `model-provider create/show/list/update/delete/sync` | [models-and-routing.md](models-and-routing.md) |
| Register or update backend models | `model create/show/list/update/delete` | [models-and-routing.md](models-and-routing.md) |
| Publish callable model aliases and weighted/priority routing | `model-alias create/set/show/list/update/delete` | [models-and-routing.md#alias-pool](models-and-routing.md#alias-pool) |
| Configure workspace or asset governance policies | `policy`, `model policy`, or `model`/`model-alias`/`mcp update --policies` | [policies.md](policies.md) |
| Register MCP ToolServers, manage sources, or start OAuth | `mcp create/show/list/update/delete/authorize`, `mcp source add/list/remove` | [mcp.md](mcp.md) |
| Manage inbound API keys or outbound managed identities | `api-key`, `identity assign/show/remove/wait` | [keys-and-identities.md](keys-and-identities.md) |
| Configure outbound VNet integration or private endpoint connections | `network show/update/wait`, `network private-endpoint-connection` | [networking.md](networking.md) |
| Configure OpenTelemetry / Application Insights export | `telemetry-exporter create/show/list/update/delete` | [telemetry-and-troubleshooting.md](telemetry-and-troubleshooting.md) |

## Operation gaps and applicability

| Area | Limitation on `Microsoft.ApiManagement/aigateways` | What to do instead |
| --- | --- | --- |
| Content safety (`set-content-safety`) | Supported only on legacy `Microsoft.ApiManagement/service`; rejected on `aigateways` | Do not run `set-content-safety` on typed `aigateways`; report as unsupported |
| Create-time `--user-assigned` | Rejected by `aigateway create` despite appearing in `--help` | Create the gateway first, then run `az aigateway identity assign --user-assigned <id>` |
| Inbound private endpoints & `publicNetworkAccess: Disabled` | Inbound private link and disabling public ingress are not effective on `aigateways` in current preview | Use Entra RBAC, API keys, and `ipFilter` policies for ingress control; use `--subnet` for outbound VNet integration |
| Custom provider sync & Managed Identity | `model-provider sync` is Foundry-only; Custom providers support `ApiKey` auth only | Register Custom models explicitly with `model create` and `ApiKey` credentials |
| MCP tool filtering (`allowList`, `blocked`, `accessState`) & OBO | No dedicated CLI authoring flags | Preserve existing fields on updates; configure those portal-only settings outside the CLI |
| Missing `wait` / `show` commands | No `policy show` or `telemetry-exporter wait` | Use `policy list` and `telemetry-exporter show` |
| Data-plane tests & log queries | No CLI subcommand for model inference, MCP `tools/list` / `tools/call`, or KQL queries | Verify runtime behavior separately with an authorized HTTP/MCP client or `az monitor` query |

