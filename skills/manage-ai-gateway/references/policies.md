# Governance policy reference

Choose a control, its traffic boundary and caller partitions, then the
smallest preserving native change. Authorization follows the
[administrator workflow](../SKILL.md); support gaps are in the
[capability inventory](activities-and-cli-coverage.md).

## Choose compatible controls

| Policy | Mechanism and principal configuration | Workspace defaults | Compatible asset hosts |
| --- | --- | --- | --- |
| `tokenLimit` | Bound token consumption: `count`, `period`, `counterKey`, accounting `scope` | Model traffic | Models, aliases |
| `costLimit` | Control estimated USD consumption: stable `id`, `amount`, `period`, `counterKey`, `scope`, ordered `overrides` | Model traffic | Models, aliases |
| `requestRateLimit` | Bound call volume: `callsPerPeriod`, `periodSeconds`, `counterKey`, `scope` | Applicable model/tool traffic | Models, aliases, ToolServers |
| `ipFilter` | Admit/exclude caller networks: `action` (`Allow`/`Deny`), `cidrRanges` | Applicable model/tool traffic | Models, aliases, ToolServers |
| `toolThreatProtection` | Evaluate tool threats through Agent 365: `preInvocation`, `postInvocation` | Not supported | ToolServers |
| `agentHooks` | Ask a decision service for allow/deny: stable `id`, resource `scope`, lifecycle `hooks`, HTTPS endpoint, authorization, failure mode/headers | Not supported | ToolServers |

**Content safety remains legacy `Microsoft.ApiManagement/service` only**
in reviewed native applicability. Native setters and free-form JSON do not
lift that limit; stop typed-gateway requests rather than retargeting.
See the [capability inventory](activities-and-cli-coverage.md#operation-gaps-and-applicability).

Combine allowances for independent token, call, and cost constraints.
MCP request limits do not provide model token/cost budgets.

## Attachment and effective configuration

Each policy instance is stored in its host's `properties.policies` array.
It is not a separate ARM child resource.

| Host | Path under the selected gateway | Configuration boundary |
| --- | --- | --- |
| Default workspace | `workspaces/default` | Shared configuration inherited by applicable assets |
| Alias | `workspaces/default/aliases/<alias>` | Traffic using the callable alias and its selected backend pool |
| Registered model | `workspaces/default/modelProviders/<provider>/models/<model>` | Traffic for that registration across aliases targeting it |
| ToolServer | `workspaces/default/toolServers/<server>` | Applicable traffic through that MCP server |

Providers, individual tools, backend sources, and named asset groups are not
policy hosts. Tool policies belong on the ToolServer; see [MCP](mcp.md).

For alias-routed traffic, compatible workspace, alias, and selected model
rules can all govern one call. A looser asset-local allowance does not replace
an inherited guardrail. Policy-array order is not evidence of runtime
execution order.

## Accounting model

Separate the host, accounting scope, caller partitions, quantity, and period.

**Host versus accounting scope.** The host determines where a policy applies.
The documented accounting contract lets an inherited counting policy share
an instance across compatible resources (`scope: "workspace"`) or distribute
independent instances per resource (`scope: "resource"`).
Direct asset policies use resource scope.
Native workspace setters always write workspace scope; they cannot author
the inherited per-resource variant. Do not silently change that variant
while editing an existing policy.

An alias instance covers traffic through its backend pool. A model instance
covers that registration across aliases targeting it. Identical policies
on several assets remain separate instances, not one shared budget.

**Caller partition.** `counterKey` divides traffic within that boundary:

| Dimension selection | Wire representation | Counter partition |
| --- | --- | --- |
| Identity | `["identity"]` | One counter per API key or authenticated Entra identity |
| IP address | `["ipAddress"]` | One counter per observed caller IP |
| Identity and IP | `["identity", "ipAddress"]` | One counter per identity/IP combination |
| No dimensions | `[]` | One pooled counter for all applicable traffic to the policy instance |

Callers reusing an API key share its Identity partition; clients behind the
same observed IP share an IP partition. Composite dimensions form a
combination, not two independent allowances. An omitted CLI option preserves
or defaults a value; native new-policy defaults select Identity, not `[]`.

**Quantity and period.** Token limits use positive integer counts and periods
`minute`, `hour`, or `day`. Request limits use positive request counts and
positive intervals in seconds. Cost limits use nonnegative estimated USD
amounts and UTC calendar periods `hour`, `day`, `week`, `month`, or `year`,
not rolling windows (weeks start Monday). MCP transport activity, tool
executions, model calls, and tokens are different measurements; establish
the request unit from runtime evidence.

**Policy identity.** Preserve host-local IDs. A cost policy's stable `id`
identifies its spend counter; changing it starts a new counter. Moving
attachments or changing scope/dimensions also changes accounting.

Cost admission checks recorded spend without reserving the request's maximum
cost, then charges observed usage after responses. Concurrent/admitted calls
can overshoot. Missing usage/prices can yield zero or partial estimates;
catalog pricing can differ from account billing. A cost limit is not a hard
spending cap. Token/request limits add consumption controls, not price accuracy.

### Cost override semantics

Overrides select an allowance within an Identity-partitioned cost policy.
They require Identity as the only dimension; empty, IP, and composite
partitions are incompatible. Entries are ordered and the first match wins.
Each entry uses either a full gateway key `apiKeyResourceId` or validated
token `claims`; all claim pairs must match. Use `tid` plus `oid` for a specific
Entra identity, and place specific selectors before broader matching claims.

An override changes each identity's allowance, not its partition. Matching
several identities to a department claim does not pool their spend. The
policy neither issues claims nor creates a caller dimension.

### Choose a team budget boundary

- **Per caller across models:** workspace token/cost policies with
  `["identity"]`. Multiple users or keys still receive separate budgets.
- **One team's pooled model traffic:** a team-specific alias with resource
  token/cost policies and `counterKey: []` pools callers across its backend
  pool. A model attachment instead covers every alias targeting that model;
  workspace `[]` pools all applicable workspace traffic.

An alias budget is a traffic boundary, not caller authorization: anyone
allowed to use it consumes its pool, and traffic using another alias is
outside it. A shared team key can share an Identity counter, but keys grant
gateway-wide access; do not propose key sharing as team access isolation.

## Native configuration paths

| Host | Read path | Authoring path |
| --- | --- | --- |
| Workspace | `policy list` | `policy set`, specialized token/cost/rate/IP setters, and type-based `remove` |
| Model | `model policy list` or `model show` | First-class token/cost setters for compatible policies; `model update --policies @file` for an explicit complete array |
| Alias | `model-alias show` | `model-alias update --policies @file` |
| ToolServer | `mcp show` | `mcp update --policies @file` |

All commands use `az aigateway` and the [resolved selectors](../SKILL.md).
`policy list`, not `policy show`, reads workspace policies. There is no
native arbitrary workspace policy-array write or provider-policy command.

Model setters can create counting entries without explicit resource scope.
Use the complete native host-array path when explicit `scope: "resource"`
is needed; there is no generic setter `--scope` option.

### Inspect before choosing a setter

```bash
az aigateway policy list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
az aigateway model policy list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" -o json
```

These return arrays. Alias and ToolServer reads expose `properties.policies`.
Read both workspace and affected asset rules; identify the target instance
by its ID where present, otherwise its full configuration, not an array position.

- Counting setters merge supplied fields into the first same-type entry,
  preserving omitted fields, but delete later duplicates. IP setters rebuild
  their entry, dropping omitted IDs/unknown fields. Use a setter only when
  its resulting collection is intended.
- For one asset entry among duplicates, edit the fresh complete array and use
  the host's `update --policies @file`. Preserve every other instance, stable
  ID, order, and unknown field. An isolated example object is not that array.
- Type-based removal can delete multiple same-kind entries. Model
  `policy remove` supports `--remove-token-limit true` and
  `--remove-cost-limit true`; workspace removal also supports
  `--remove-rate-limit true` and `--remove-ip-filter true`.
- If workspace scope, duplicates, or fields cannot survive the setter, stop:
  no native per-instance or complete-array workspace editing path is established.
  Do not substitute REST or delete an imagined policy child.

## Configuration examples

Merge example entries into the **complete intended host array**, never as
standalone replacement payloads.

### Token limit

Workspace token configuration:

```bash
az aigateway policy set --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" \
  --token-limit 30000 --token-period minute --token-counter-key Identity
```

For a pooled alias/model allowance:

```json
{
  "type": "tokenLimit",
  "scope": "resource",
  "count": 10000,
  "period": "minute",
  "counterKey": []
}
```

For an alias, apply the reviewed full array with:

```bash
az aigateway model-alias update --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" --policies @policies.json
```

For models use provider/model selectors with `model update`, or compatible
partial `model policy set` / `set-token-limit` updates.

### Cost limit

For pooled workspace accounting, `no-dimensions.json` contains:

```json
[]
```

```bash
az aigateway policy set --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --cost-id workspace-monthly-budget \
  --cost-limit 1000 --cost-period month --cost-counter-key @no-dimensions.json
```

A resource-hosted cost policy with an override:

```json
{
  "type": "costLimit",
  "id": "support-callers",
  "scope": "resource",
  "amount": 100,
  "period": "day",
  "counterKey": ["identity"],
  "overrides": [{"claims": {"department": "support"}, "amount": 25}]
}
```

Each matching identity receives $25; unmatched identities receive $100.
Preserve override order and unknown variants. The native `--cost-overrides`
item schema declares no properties: use reviewed resource-host JSON shapes,
not an assumed arbitrary workspace override path.

### Request rate limit

Workspace request configuration:

```bash
az aigateway policy set --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" \
  --calls-per-period 60 --period-seconds 60 --rate-counter-key Identity
```

A resource-local pooled request policy:

```json
{"type": "requestRateLimit", "scope": "resource", "callsPerPeriod": 60, "periodSeconds": 60, "counterKey": []}
```

Merge into a compatible host array. A ToolServer limit covers applicable
server traffic, not a separately scoped source or tool.

### IP filter

After confirming access impact:

```bash
az aigateway policy set --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" \
  --ip-filter-mode Allow --ip-addresses "$AUTHORIZED_CIDR"
```

A resource-hosted `ipFilter` uses `action: "Allow"` or `"Deny"` and
`cidrRanges`, without a counter. An allow list can exclude existing clients.

### Tool threat protection

```json
{"type": "toolThreatProtection", "preInvocation": true, "postInvocation": false}
```

Enable at least one phase. Establish evaluation-service access and tenant
licensing with the owner: current product prerequisites specify Agent 365;
the [lab prerequisites](../../../labs/19-tool-threat-protection/README.md#before-you-begin)
list Defender/Purview licensing. Calls require a delegated Entra user token
for the gateway's evaluation-service OBO exchange; app-only/key-only calls
are not substitutes.

Pre-invocation denial prevents execution; post-invocation denial withholds
the result, not the completed action. Evaluation/token-exchange failures
fail closed even in Defender Audit mode. Discovery/session operations are
not evaluated. HTTP 200 can contain an MCP `isError` denial; inspect the
evaluation code, not just status.

### Agent hooks

Agent hooks delegate MCP tool decisions to an existing trusted HTTPS callback.
`preToolCall` can prevent execution; `postToolCall` can withhold results but
cannot undo execution. The hook contract describes both phases; verify native
support for the intended combination before writing. Free-form JSON alone
does not establish dual-phase authoring support.

For an existing Azure Function callback:

```json
{
  "type": "agentHooks",
  "id": "review-hook",
  "scope": "resource",
  "hooks": {
    "preToolCall": {
      "endpoint": "https://<function-app-hostname>/api/pre-tool-call",
      "mode": "failClosed",
      "authorization": {
        "type": "apiKey",
        "apiKey": {"headerName": "x-functions-key", "value": "<runtime-function-key>"}
      }
    }
  }
}
```

Resolve callback connectivity and authorization before attachment; confirm
sending tool arguments/results. The callback must accept payloads without
agent/session identity and return `allow`/`deny`, not approvals or transforms.
URLs must be HTTPS without credentials, query, or fragment. Authentication:

- `apiKey`: verified header and protected key input. Omit an unchanged
  write-only value to preserve it; never send a redaction marker.
- `managedIdentity`: `managedIdentity.resource` is the callback audience;
  optional `clientId` selects a gateway-enabled user-assigned identity,
  otherwise use its enabled system identity. Callback access remains a
  separate prerequisite; follow [identity/grant handling](keys-and-identities.md).
- `anonymous`: only for a deliberately public callback.

`failClosed` (default) blocks callback failure/invalid responses; `failOpen`
allows that failure path and is a weakening requiring confirmation. Neither
mode changes a valid `allow`/`deny` verdict. Hook settings override shared
endpoint/mode/auth (authorization replaces the object); literal non-secret
headers merge case-insensitively. Preserve unedited shared settings.
An empty hook header map does not clear inherited headers.
Merge into the ToolServer array and apply only `mcp update --policies`;
supplying `--endpoints` triggers an implicit secret read (see [MCP](mcp.md)).

Use the [Agent Hooks contract](https://ai.gateway.azure.com/docs/policies/agent-hooks)
and [callback verification procedure](https://ai.gateway.azure.com/docs/policies/guides/create-pre-tool-call-hook).

## Mutation and verification

If secrets or unsupported fields cannot safely round-trip, stop rather than
reconstructing policies from redacted output.

Model setters and alias/MCP updates use ETags; raw model updates do not,
and workspace protection depends on a returned ETag. An internal ETag read
does not bind your prepared array to its original read. Compare fresh policies
before submission and use supported caller conditions; otherwise disclose
the remaining concurrent-edit gap.

Re-read workspace and affected hosts. Verify attachment, explicit accounting
scope, dimensions, quantities, periods, stable IDs, override order, and
retained siblings. Explain which effective controls now apply.

Read-back is not enforcement evidence. For an authorized bounded runtime
check, compare pooled versus separate caller usage within one period;
correlate a rejection with policy/backend traces rather than status alone.
For cost, inspect pricing completeness as well as observed usage. Check IP
admission from the intended client networks. For tool controls distinguish
an explicit deny from evaluator/callback failure and confirm execution at
the selected phase. Leave unavailable runtime evidence explicit; never
replay a side-effecting tool call merely because its result was withheld.
