# Native capability inventory

This reference indexes the gateway resource and command surface, its
configuration limits, and ownership boundaries. Use it with the
[administrator workflow](../SKILL.md) and the domain references. Capability
availability is separate from authorization to perform a change.

## Evidence baseline

The reviewed baseline is official CLI `1.0.0b22`, API
`2025-09-01-preview`, and the
[public command reference](https://github.com/Azure/aigateway/blob/main/cli/command-reference.md)
at blob `34d488c50748eb5f1b90b300f27d17bf98027f43`.
Local help, declared argument schemas, and typed-resource dispatch were
inspected. No live Azure operation or runtime behavior is certified by this
review. Current task-specific help and release evidence determine whether
the recorded command surface still applies.

Portal functional areas were reviewed at revision
`64376af870a6203c6b2f5fe7a94bf3d508a43e99`: gateway provisioning,
provider/model registration, alias routing/selection, governance, native
ToolServers, access, identities, networking, and monitoring. Source areas
include `src/App.tsx`, `src/api/real/`, asset editors, `ProvisioningContext`,
telemetry setup, and specs 042, 050, 052, 053, 054, 056, 058, 059, 061,
and 063. Historical or other-resource-family designs are not evidence of
typed-gateway capability.

## Capability classifications

| Classification | Meaning |
| --- | --- |
| Native | An exposed command/typed input supplies an execution path for the recorded capability |
| Native JSON | A native argument accepts the referenced payload shape; service acceptance and runtime effect remain separate evidence |
| Gap | No confirmed native path for the complete capability or field |
| External | Resource or permission changes owned outside this skill's gateway-only boundary |

These classifications describe distinct dimensions of support. A free-form
argument does not establish service applicability, an inherited portal label
does not identify the actual policy host, and saved configuration does not
prove runtime effect.

## Resource and control surface

All command names below are prefixed with `az aigateway`.

| Area | Native surface | Configuration and support boundaries | Reference |
| --- | --- | --- | --- |
| Gateway lifecycle | `list/show/create/update/delete/wait/version` | Typed gateway identity, provisioning, tags and tier; existing RG; tags replace the supplied set | [Lifecycle](gateway-lifecycle.md) |
| Model provider | `model-provider create/show/list/update/delete` | Foundry/Custom registration and nested endpoint/auth settings; underlying accounts remain external | [Models](models-and-routing.md) |
| Foundry registration | Low-level provider and model create operations, then explicit aliases | Existing deployments and backend permissions; convenience `--foundry-resource-id` paths also grant external RBAC and are outside the allowed execution path | [Models](models-and-routing.md) |
| Provider reconciliation | `model-provider sync --dry-run` and confirmed apply | Foundry only; sequential additions/stale removals; alias dependencies and optional default aliases need an explicit plan; Custom discovery/sync is a gap | [Models](models-and-routing.md) |
| Model registration | `model create/show/list/update/delete` | Deployment metadata, supported endpoints and exposed API formats; not deployment provisioning or proof of a callable alias | [Models](models-and-routing.md) |
| Alias routing | `model-alias create/set/show/list/update/delete` | Stable callable name, one to 30 unique same-gateway model targets, priority and weight; `set` explicitly creates or updates | [Models](models-and-routing.md) |
| Advanced alias selection | Gap | Auto-selection objectives, override grants, selection order, session preference, CEL backend conditions; typed backend fields expose only ID/priority/weight | [Models](models-and-routing.md) |
| Workspace policies | `policy list/set/remove` and specialized setters | Token, cost, request-rate and IP controls on `workspaces/default`; workspace accounting scope; no arbitrary raw workspace-array write | [Policies](policies.md) |
| Model policies | `model policy list/set/remove` and token/cost setters | Partial updates for compatible policies; explicit resource scope may require the raw host path; same-type setters can consolidate entries | [Policies](policies.md) |
| Asset inline policies | Native JSON: host `update --policies @file` | Compatible model/alias/ToolServer controls; complete-array preservation; no established provider policy host | [Policies](policies.md) |
| Cost override variants | Verified raw resource-host policy JSON | Ordered API-key/claim selectors with Identity-only accounting; reviewed convenience `--cost-overrides` items declare no fields; no established native arbitrary workspace override path | [Policies](policies.md) |
| Content safety | Unsupported for typed gateways | Legacy `Microsoft.ApiManagement/service` only; visible CLI flags do not enable it on `Microsoft.ApiManagement/aigateways` | [Policies](policies.md) |
| MCP registration | `mcp create/show/list/update/delete` | Multi-source ToolServers, versions, supported inline policies; full endpoint updates define complete membership | [MCP](mcp.md) |
| MCP sources | `mcp source add/list/remove` and typed endpoint JSON | Remote MCP and OpenAPI URL/inline sources; secret-preserving conditional editing; `http` enum lacks a verified kind-specific authoring contract | [MCP](mcp.md) |
| MCP backend authentication | Native JSON credentials | Headers, gateway MI and authorization-code OAuth; reviewed grants exclude client credentials and Entra token-exchange/OBO authoring | [MCP](mcp.md) |
| MCP OAuth initiation | `mcp authorize` | Persisted endpoint identity and sensitive login-link handling; initiation is not proof of completed authorization | [MCP](mcp.md) |
| MCP tool exposure and discovery | Gap | No confirmed native tool-selector/pattern authoring, runtime tool listing, refresh, or tool execution operation | [MCP](mcp.md) |
| Client API keys | `api-key create/show/list/update/delete/list-secrets/regenerate` | Gateway-wide access; metadata differs from secret retrieval; supported state/expiry/value changes and staged primary/secondary rotation; existing-key rename is service-rejected | [Keys](keys-and-identities.md) |
| Gateway identity | `identity assign/show/remove/wait` | System identity and attachment of existing UAMIs; external role grants and identity-resource creation remain external | [Identities](keys-and-identities.md) |
| Gateway networking | `network show/update/wait` | Public ingress and existing outbound subnet integration; no backing VNet/subnet/DNS provisioning | [Networking](networking.md) |
| Private endpoint connections | `network private-endpoint-connection list/show/approve/reject/delete/wait` | Existing gateway-side connection decisions; backing private endpoints remain separate resources | [Networking](networking.md) |
| Telemetry exporters | `telemetry-exporter create/show/list/update/delete` plus native JSON | Existing destinations, OTLP signals/auth, claim attributes and payload capture; no exporter wait in the reviewed CLI | [Telemetry](telemetry-and-troubleshooting.md) |
| Runtime/query evidence | Gap | No established native inference/MCP test or metrics/trace/KQL query subgroup; portal/destination evidence is separate | [Operations](telemetry-and-troubleshooting.md) |
| Invocation roles and app consent | External | Microsoft.Authorization, Entra applications/consent, and connector ACL changes, including grants scoped to a gateway/asset | Owner prerequisite |
| Supporting infrastructure | External | RGs, deployments, identities, networks/DNS/private endpoints, telemetry stores/DCRs, provider/feature registration and external permissions | Owner prerequisite |
| Historical product areas | Outside the confirmed typed-gateway surface | A2A agents, triggers, source connector administration, and old APIM API/backend/XML flows | Separate product capability |

## Compatibility details

- Earlier reference examples advertised `policy show`,
  `telemetry-exporter wait`, and alias `create --overwrite`; these are not
  exposed by the reviewed CLI. The current command reference uses
  `policy list`, bounded exporter read-back, and explicit alias `update`.
  Alias `set` is available for intentional create-or-update behavior.
- MCP `--failure-mode` is create-only and not returned on reads; its
  enforcement and an update cannot be established through that interface.
- Custom provider authentication accepts `ApiKey`, not the portal's newer
  arbitrary-header variants. Model API formats expose
  `OpenAIChatCompletions`, `ResponsesApi`, and `AnthropicMessages`; other
  protocol/decision-model variants need a reviewed upstream capability.
- Several name-only operations lack exact family binding. Typed-parent and
  collision checks reduce risk but do not make a sequence atomic.
- Workspace policies may write without an ETag. General model, provider,
  network, key, and exporter mutations are not uniformly concurrency-safe.
  Alias and MCP operations have their own conditional handling.
- Current portal monitoring uses OTLP signal endpoints, authentication and
  a destination link; a shorter legacy connection-string example does not
  establish current dashboard compatibility.

An unresolved requirement is reported with the missing capability or field,
the affected resource/scope, available supported configuration, and the
necessary owner prerequisite or upstream change. The own-resource/native-only
boundary remains unchanged by a gap; neither legacy retargeting nor a REST
bypass supplies missing product support.
