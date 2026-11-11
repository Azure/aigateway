# Governance policy reference

Choose a policy, its traffic boundary and counter dimensions, then the
smallest preserving native change. Authorization follows the
[administrator workflow](../SKILL.md); support gaps are in the
[capability inventory](activities-and-cli-coverage.md).

## Choose compatible controls

The gateway policy catalogue maps product names to policy types:

| Policy | Mechanism | Workspace defaults | Compatible asset hosts |
| --- | --- | --- | --- |
| [**Token rate limit**](#token-rate-limit) (`tokenLimit`) | Token-volume allowance | Model traffic | Models, aliases |
| [**Cost limit**](#cost-limit) (`costLimit`) | Estimated USD allowance | Model traffic | Models, aliases |
| [**Request rate limit**](#request-rate-limit) (`requestRateLimit`) | Request-volume allowance | Applicable model/tool traffic | Models, aliases, ToolServers |
| [**IP filter**](#ip-filter) (`ipFilter`) | Caller IP admission | Applicable model/tool traffic | Models, aliases, ToolServers |
| [**Agent 365 tool threat protection**](#agent-365-tool-threat-protection) (`toolThreatProtection`) | Microsoft Defender and Microsoft Purview evaluation of tool calls and results | Not supported | ToolServers |
| [**Agent hooks**](#agent-hooks) (`agentHooks`) | Governance callbacks for MCP tool actions | Not supported | ToolServers |

Check the [Content safety applicability limit](activities-and-cli-coverage.md#operation-gaps-and-applicability)
before proposing that policy; native setter visibility does not lift it.

The three allowance policies measure different quantities: token consumption,
request volume, and estimated cost. A request ceiling does not bound tokens;
a token ceiling is not a cost budget. MCP request limits do not provide model
token/cost budgets, and multiple policies can apply independently.

## Attachment and effective configuration

Each policy instance is stored in its host's `properties.policies` array.
It is not a separate ARM child resource.

| Host | Configuration boundary |
| --- | --- |
| Default workspace (`workspaces/default`) | Shared configuration inherited by applicable assets |
| [Alias](models-and-routing.md#resource-model) | Traffic using the callable alias and its selected backend pool |
| [Registered model](models-and-routing.md#resource-model) | Traffic for that registration across aliases targeting it |
| [ToolServer](mcp.md#understand-the-effects) | Applicable traffic through that MCP server |

Providers, individual tools, backend sources, and named asset groups are not
policy hosts. For non-policy server changes, use [MCP](mcp.md).

For alias-routed traffic, compatible workspace, alias, and selected model
rules can all govern one call. A looser asset-local allowance does not replace
an inherited guardrail. Policy-array order is not evidence of runtime
execution order.

## Accounting model

Separate the host, accounting scope, counter dimensions, quantity, and period.

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

**Counter dimensions (`counterKey`).** The selected dimensions partition
traffic within the accounting boundary:

| Counter dimensions | `counterKey` | Counter partition |
| --- | --- | --- |
| **Caller identity** | `["identity"]` | One counter per API key or authenticated Entra identity |
| **Caller IP address** | `["ipAddress"]` | One counter per observed caller IP |
| Both | `["identity", "ipAddress"]` | One counter per identity/IP combination |
| Neither | `[]` | One pooled counter for all applicable traffic to the policy instance |

Callers reusing an API key share its identity counter; clients behind the
same observed IP share an IP counter. Composite dimensions form a
combination, not two independent allowances. Workspace CLI flags are
`--token-counter-key`, `--rate-counter-key`, and `--cost-counter-key`; for
example, `--token-counter-key Identity IPAddress` selects both dimensions.
An omitted CLI option preserves or defaults a value; native new-policy
defaults select `Identity`, not `[]`.

**Quantity and period.** Use the [policy-specific settings](#configuration-examples)
to select the measured quantity and window. MCP transport activity, tool
executions, model calls, and tokens are different measurements; establish the
request unit from runtime evidence.

**Policy identity.** Preserve host-local IDs. A cost policy's stable `id`
identifies its spend counter; changing it starts a new counter. Moving
attachments or changing scope/dimensions also changes accounting.

Cost admission checks recorded spend without reserving the request's maximum
cost, then charges observed usage after responses. Concurrent/admitted calls
can overshoot. Missing usage/prices can yield zero or partial estimates;
catalog pricing can differ from account billing. A cost limit is not a hard
spending cap. Token/request limits add consumption controls, not price accuracy.

### Cost override semantics

**Overrides** (`overrides`) select an allowance within a cost policy. They
require **Caller identity** as the only counter dimension; empty, IP, and
composite partitions are incompatible. Entries are ordered and the first
match wins. Each entry uses either a full gateway key `apiKeyResourceId` or
validated token `claims`; all claim pairs must match. Use `tid` plus `oid` for
a specific Entra identity, and place specific selectors before broader
matching claims.

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
outside it. Evaluate [key access and caller identity](keys-and-identities.md#understand-the-effects)
before choosing shared credentials; counter pooling is not team access isolation.

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

### Update a ToolServer's policies

Set `MCP_ID` from the [selected registration](mcp.md#inspect-a-server),
merge changes into the complete intended array, preserving other instances
and IDs. Obtain specific confirmation for replacing the whole array before
applying:

```bash
az aigateway mcp update --ids "$MCP_ID" --subscription "$SUBSCRIPTION" \
  --policies @tool-server-policies.json
```

Leave endpoints unrequested in policy-only writes; their
[secret-preservation path](mcp.md#credential-preservation-and-implicit-secret-reads)
is unrelated to governance.

## Configuration examples

Setting flags below refer to workspace `policy set`; check host-specific help
for model setters. Merge example entries into the **complete intended host array**,
never as standalone replacement payloads.

### Token rate limit

**Allowed tokens** is `count` (`--token-limit`), a positive integer;
**Time period** is `period` (`--token-period`): `minute`, `hour`, or `day`.

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

**Budget amount** is `amount` (`--cost-limit`), a nonnegative estimated USD
amount; **Renewal period** is `period` (`--cost-period`): `hour`, `day`,
`week`, `month`, or `year`. Cost periods are fixed UTC calendar windows, not
rolling windows (weeks start Monday).

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

**Calls** is `callsPerPeriod` (`--calls-per-period`) and **Renewal period** is
`periodSeconds` (`--period-seconds`); both are positive.

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

Merge into a compatible host array using the [attachment boundary](#attachment-and-effective-configuration).

### IP filter

After confirming access impact:

```bash
az aigateway policy set --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" \
  --ip-filter-mode Allow --ip-addresses "$AUTHORIZED_CIDR"
```

A resource-hosted `ipFilter` uses `action: "Allow"` or `"Deny"` and
`cidrRanges`, without a counter. An allow list can exclude existing clients.

### Agent 365 tool threat protection

**Before tool invocation** (`preInvocation`) evaluates the request;
**After tool invocation** (`postInvocation`) evaluates the tool output.

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
A before-tool hook (`preToolCall`) can prevent execution; an after-tool hook
(`postToolCall`) can withhold results but cannot undo execution. The hook
contract describes both phases; verify native support for the intended
combination before writing. Free-form JSON alone does not establish dual-phase
authoring support.

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
  optional `clientId` follows the [identity-selection rules](keys-and-identities.md#understand-the-effects).
  Resolve callback access through the [grant procedure](keys-and-identities.md#grant-caller-or-destination-access).
- `anonymous`: only for a deliberately public callback.

`failClosed` (default) blocks callback failure/invalid responses; `failOpen`
allows that failure path and is a weakening requiring confirmation. Neither
mode changes a valid `allow`/`deny` verdict. Hook settings override shared
endpoint/mode/auth (authorization replaces the object); literal non-secret
headers merge case-insensitively. Preserve unedited shared settings.
An empty hook header map does not clear inherited headers.
Apply through the [ToolServer policy path](#native-configuration-paths).

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
