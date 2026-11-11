# Native capability inventory

Choose a task below, then use its reference for effects, the smallest native
change, configuration verification, and remaining runtime uncertainty.
This index records support boundaries for
`Microsoft.ApiManagement/aigateways` and the implicit `default` workspace.
For selectors, authorization, and execution, use the
[administrator workflow](../SKILL.md); for complete syntax, use the
[CLI command reference](../../../cli/command-reference.md) and task-specific help.

## Resource and control surface

All command families below are prefixed with `az aigateway`.

| Administrator task | Native entry point | Decision or boundary | Task reference |
| --- | --- | --- | --- |
| Provision, retag, set SKU, or delete a gateway | Top-level `list/show/create/update/delete/wait` | Existing RG; only `Standard` exposed; attach UAMIs after creation; tags replace the set | [Lifecycle](gateway-lifecycle.md) |
| Register a backend deployment | `model-provider`, then `model`, then `model-alias` | Foundry/Custom connection and deployment metadata, not backend provisioning; alias publishes the callable name | [Models and routing](models-and-routing.md) |
| Reconcile Foundry registrations | `model-provider sync --dry-run` | Preview additions, stale removals, alias dependencies, and optional default aliases; apply is sequential, not transactional | [Models and routing](models-and-routing.md) |
| Split traffic or add fallback targets | `model-alias create/update/set` | One to 30 unique same-gateway targets with priority/weight; `set` intentionally creates or updates | [Models and routing](models-and-routing.md) |
| Set quotas, accounting, or access controls | `policy`, `model policy`; compatible asset `update --policies @file` | Default-workspace versus asset attachment matters; inline arrays replace the collection and same-type setters may consolidate entries | [Policies](policies.md) |
| Publish or edit a multi-source ToolServer | `mcp`, `mcp source add/list/remove`, `mcp authorize` | Remote MCP/OpenAPI sources; native JSON for headers, gateway MI, or authorization-code OAuth; endpoint arrays replace membership; OAuth initiation is not completion | [MCP](mcp.md) |
| Manage caller access or rotate keys | `api-key`; confirmed role grants via core CLI | Keys are gateway-wide; metadata reads differ from authorized `list-secrets`; rotate primary/secondary separately; existing-key rename is service-rejected | [Keys and identities](keys-and-identities.md) |
| Enable outbound managed identity | `identity assign/show/remove/wait` | System identity or existing user-assigned identities; attachment does not grant backend access | [Keys and identities](keys-and-identities.md) |
| Inspect networking or configure outbound subnet integration | `network show/update/wait` | Existing subnet prerequisites; public-access flags do not establish ingress enforcement (see gap below) | [Networking](networking.md) |
| Inspect the private-connection command surface | `network private-endpoint-connection` | Gateway-side syntax, not proof of available private ingress or backing endpoint/DNS provisioning (see gap below) | [Networking](networking.md) |
| Configure export or investigate missing telemetry | `telemetry-exporter` | Signal endpoints/auth, attributes and capture; destination ingestion and query access are separate | [Telemetry and troubleshooting](telemetry-and-troubleshooting.md) |

## Operation gaps and applicability

These limits apply to the reviewed native CLI and target resource type.
Requalify support before lifting a limit.

| Requirement | Limitation and next reference |
| --- | --- |
| Content safety | Reviewed native setters remain legacy `Microsoft.ApiManagement/service` only; do not retarget the resource. See [policies](policies.md). |
| Private ingress or disabling public access | [Lab 18](../../../labs/18-private-networking/README.md) records unavailable inbound private endpoints and ineffective `publicNetworkAccess: Disabled` on typed gateways (2026-10-19, `d5209ad9`). No live retest here. See [networking](networking.md) before promising isolation. |
| Routing beyond priority/weight, or Custom provider sync | Reviewed alias target authoring covers model ID/priority/weight only; additional routing-field writes and Custom provider sync are not established. See [models](models-and-routing.md). |
| Other model protocols/authentication | Reviewed API formats: `OpenAIChatCompletions`, `ResponsesApi`, `AnthropicMessages`; Custom authentication: `ApiKey`, not arbitrary-header variants. See [models](models-and-routing.md). |
| Arbitrary policy payloads or cost variants | No provider policy host or arbitrary workspace-array write is established. Resource-host cost JSON supports ordered API-key/claim overrides with Identity-only accounting; the convenience `--cost-overrides` item schema remains empty in b26. See [policies](policies.md). |
| Other MCP source/auth/tool controls | An `http` enum is not a verified authoring contract. No confirmed client-credentials/OBO/token-exchange authoring, tool-selector/pattern authoring, runtime tool listing, refresh, or execution command. See [MCP](mcp.md). |
| MCP failure behavior | Use per-source `required` for discovery behavior. Top-level `--failure-mode` is create-only, absent on read-back, and unavailable for update; its enforcement remains unverified. See [MCP](mcp.md). |
| Waits and diagnostics | No `telemetry-exporter wait` or `policy show`; use bounded exporter read-back and `policy list`. No established inference/MCP test or metrics/trace/KQL query subgroup. See [troubleshooting](telemetry-and-troubleshooting.md). |
| Legacy/historical product areas | A2A agents, triggers, source connector administration, and APIM API/backend/XML flows are outside the confirmed typed-gateway surface. |

## Compatibility details

- **Resource dispatch and subscription.** Several name-only operations can
  fall back to legacy `service`; typed-parent/collision checks are not atomic
  family binding. A carried-forward b26 observation (2026-11-10) recorded
  name-based commands ignoring `--subscription` in favor of the CLI default;
  `--ids` reads were unaffected. Not re-tested here. Keep explicit
  subscriptions and use the workflow's consented temporary default-switch
  procedure when needed; help exposing a selector does not prove dispatch.
- **Concurrency.** Workspace writes may lack ETags; general model, provider,
  network, key, and exporter mutations are not uniformly conditional.
  Alias/MCP handling is operation-specific. MCP create sends
  `If-None-Match: *`, but native help disclaims atomic enforcement;
  a request header alone does not establish create-if-absent protection.
- **Gateway creation and waits.** The b26 adapter rejects create-time
  `--user-assigned` despite help visibility; attach an existing UAMI after
  creation. Typed waits accept `Active` or `Succeeded`; a parent wait does not
  verify the changed identity, subnet or child approval. See [lifecycle](gateway-lifecycle.md)
  and the affected task reference.
- **MCP endpoint writes.** b26 `azext_aigateway/_rp.py`, `write_mcp()` lines
  981–988: supplying endpoints
  invokes `AIGatewayToolServer_ListSecrets`. Thus `mcp update --endpoints`
  and `mcp source add/remove` can implicitly retrieve secrets;
  `--display-name`, `--description`, `--versions`, `--type`, or `--policies`
  alone do not trigger that path. See [MCP](mcp.md).
- **External dependencies.** Supporting infrastructure, Entra app/consent,
  connector ACLs, and provider/feature registration remain owner prerequisites.
  Explicit, confirmed least-privileged role grants are permitted when the user
  can assign at that scope. Foundry `--foundry-resource-id` convenience paths
  bundle identity enablement and RBAC; prefer low-level registration plus the
  explicit grant. See the [operating boundary](../SKILL.md#operating-boundary).
- **Telemetry.** Native exporter updates forward supplied objects without
  a conditional header; reads mask the whole headers map. Legacy
  connection-string/singular-endpoint examples are not current per-signal
  OTLP recipes. See [telemetry](telemetry-and-troubleshooting.md).

## Evidence baseline

- **Published reference baseline:** official CLI `1.0.0b26`, API
  `2025-09-01-preview`; command-reference blob
  `b53b4cb38719506c14e197f37bb36bc8fbbba6d0`.
- **Historical applicability review:** CLI `1.0.0b22`; typed dispatch and
  argument schemas were inspected against command-reference blob
  `34d488c50748eb5f1b90b300f27d17bf98027f43`.
- **Refresh on 2026-11-11:** installed CLI `1.0.0b26`, API
  `2025-09-01-preview`. Reviewed relevant native help, argument schemas and
  adapter code, not every native operation. This is not b26 applicability
  certification.
- **Specific source checks:** native `azext_aigateway/_rp.py` lines 936
  (MCP create), 1652–1655 (UAMI create rejection), 1885–1888 (wait states),
  1178–1202 (exporter writes); `_helpers.py` lines 7–18,44–59 (masking).
- **Boundary:** no Azure resource reads, writes or runtime tests in this
  refresh. Source/help establishes inputs and client behavior, not service
  acceptance, enforcement or delivery. Retain reviewed limits unless stronger
  evidence supersedes them.

### Local help checked on 2026-11-11

`az aigateway --help`, `telemetry-exporter --help`, `policy --help`,
`model-alias create --help`, `policy set-content-safety --help`,
`mcp create --help`, `mcp update --help`, `policy set --help`,
`policy set-cost-limit --help`, `model policy set-cost-limit --help`,
`create --help`, `update --help`, `network update --help`, and
`network private-endpoint-connection --help`
(all entries after the first also use the `az aigateway` prefix).

These reconfirmed the missing exporter wait, policy show, and alias
`create --overwrite`; use alias `update` or intentional `set` instead.
Content-safety visibility and generic cost-override JSON did not lift the
recorded applicability/schema limits. A gap requires an explicit unsupported
outcome or owner prerequisite, not legacy retargeting or a REST bypass.
