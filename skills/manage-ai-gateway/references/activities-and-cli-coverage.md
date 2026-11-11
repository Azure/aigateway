# Native capability inventory

Choose a task below, then use its reference for applicability, semantics,
the smallest native change and verification. This index records the surface
and reviewed evidence for
`Microsoft.ApiManagement/aigateways` and the implicit `default` workspace.
For selectors, authorization, and execution, use the
[administrator workflow](../SKILL.md); for complete syntax, use the
[CLI command reference](../../../cli/command-reference.md) and task-specific help.

## Resource and control surface

All command families below are prefixed with `az aigateway`.

| Administrator task | Native entry point | Task reference |
| --- | --- | --- |
| Provision, retag, set SKU, or delete a gateway | Top-level `list/show/create/update/delete/wait` | [Lifecycle](gateway-lifecycle.md) |
| Publish a backend deployment or change routing | `model-provider`, `model`, `model-alias` | [Models and routing](models-and-routing.md) |
| Reconcile Foundry registrations | `model-provider sync --dry-run` | [Provider reconciliation](models-and-routing.md#provider-reconciliation) |
| Set quotas, accounting, or policy access controls | `policy`, `model policy`; asset `update --policies @file` | [Policies](policies.md) |
| Publish or edit a ToolServer | `mcp`, `mcp source add/list/remove`, `mcp authorize` | [MCP](mcp.md) |
| Manage caller access or keys | `api-key`; confirmed role grants via core CLI | [Keys and identities](keys-and-identities.md) |
| Manage outbound identity | `identity assign/show/remove/wait` | [Identity operations](keys-and-identities.md#enable-attach-or-remove-outbound-identity) |
| Configure outbound networking or review private connections | `network show/update/wait`, `network private-endpoint-connection` | [Networking](networking.md) |
| Configure export or diagnose missing telemetry | `telemetry-exporter` | [Telemetry and troubleshooting](telemetry-and-troubleshooting.md) |

## Operation gaps and applicability

Requalify support before lifting a limit. Domain-specific authoring contracts
and gaps stay with their recipes rather than being copied into this index:
[model protocols, authentication and routing](models-and-routing.md),
[policy hosts and payloads](policies.md),
[MCP sources and tool controls](mcp.md#product-controls-and-native-limits), and
[telemetry operations](telemetry-and-troubleshooting.md).
The following service-level exclusions have separate applicability evidence:

| Requirement | Limitation and next reference |
| --- | --- |
| Content safety | Reviewed native setters remain legacy `Microsoft.ApiManagement/service` only; do not retarget the resource. |
| Private ingress or disabling public access | [Lab 18](../../../labs/18-private-networking/README.md) records unavailable inbound private endpoints and ineffective `publicNetworkAccess: Disabled` on typed gateways (2026-10-19, `d5209ad9`). No live retest here. |
| Runtime diagnostics | No established inference/MCP test or metrics/trace/KQL query subgroup; use [authorized diagnostic evidence](telemetry-and-troubleshooting.md#diagnose-without-speculative-remediation). |
| Legacy/historical product areas | A2A agents, triggers, source connector administration, and APIM API/backend/XML flows are outside the confirmed typed-gateway surface. |

## Compatibility details

- **Resource dispatch and subscription.** Several name-only operations can
  fall back to legacy `service`; typed-parent/collision checks are not atomic
  family binding. A carried-forward b26 observation (2026-11-10) recorded
  name-based commands ignoring `--subscription` in favor of the CLI default;
  `--ids` reads were unaffected. Not re-tested here. Keep explicit
  subscriptions and follow [target resolution](../SKILL.md#prerequisites-and-target-resolution)
  when the mismatch occurs.
- **Concurrency.** Follow the affected task reference's operation-specific
  conditions. MCP create sends
  `If-None-Match: *`, but native help disclaims atomic enforcement;
  a request header alone does not establish create-if-absent protection.
- **Gateway creation and waits.** The b26 adapter rejects create-time
  `--user-assigned` despite help visibility; wait states were checked at the
  source locations below. Apply these findings through [lifecycle](gateway-lifecycle.md)
  and the affected task's verification procedure.
- **MCP endpoint writes.** b26 `azext_aigateway/_rp.py`, `write_mcp()` lines
  981–988: supplying endpoints
  invokes `AIGatewayToolServer_ListSecrets`. The operational contract is in
  [credential preservation](mcp.md#credential-preservation-and-implicit-secret-reads).
- **Telemetry.** Exporter writes and masking were checked at the source
  locations below; use the [export contract](telemetry-and-troubleshooting.md)
  rather than legacy help examples.

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

These checks inform the linked authoring recipes; they did not lift the
recorded content-safety applicability or cost-override schema limits.
