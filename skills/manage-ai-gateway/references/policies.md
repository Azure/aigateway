# Governance policy reference

Policies configure runtime controls on a workspace or registered asset.
This reference describes their mechanisms, applicability, accounting, and
native authoring paths for `Microsoft.ApiManagement/aigateways`.
Use it with the [administrator workflow](../SKILL.md) and
[capability inventory](activities-and-cli-coverage.md).

## Policy catalogue

| Policy | Mechanism and principal configuration | Workspace defaults | Compatible asset hosts |
| --- | --- | --- | --- |
| `tokenLimit` | Token-volume allowance: `count`, `period`, `counterKey`, accounting `scope` | Model traffic | Models, aliases |
| `costLimit` | Estimated USD allowance: stable `id`, `amount`, `period`, `counterKey`, `scope`, optional ordered `overrides` | Model traffic | Models, aliases |
| `requestRateLimit` | Request-volume allowance: `callsPerPeriod`, `periodSeconds`, `counterKey`, `scope` | Applicable model/tool traffic | Models, aliases, ToolServers |
| `ipFilter` | Caller IP admission: `action` (`Allow`/`Deny`) and `cidrRanges` | Applicable model/tool traffic | Models, aliases, ToolServers |
| `toolThreatProtection` | Tool evaluation phases: `preInvocation`, `postInvocation` | Not supported | ToolServers |
| `agentHooks` | Governance callbacks: stable `id`, resource `scope`, lifecycle `hooks`, HTTPS endpoint, authorization, optional failure mode/headers | Not supported | ToolServers |

This is the supported native authoring surface, not every type present in an
older portal catalogue or CLI schema. Provider-specific exclusions belong
in the capability inventory. Models and aliases are model-family hosts;
individual tools and backend sources are not independent policy attachments.

The three allowance policies measure different quantities: tokens, requests,
and estimated cost. A request ceiling does not bound token size, and a
token ceiling does not express a dollar budget. Several controls can
constrain the same workload independently.

## Attachment and effective configuration

Each policy instance is stored in its host's `properties.policies` array.
It is not a separate ARM child resource.

| Host | Path under the selected gateway | Configuration boundary |
| --- | --- | --- |
| Default workspace | `workspaces/default` | Shared configuration inherited by applicable assets |
| Alias | `workspaces/default/aliases/<alias>` | Traffic using the callable alias and its selected backend pool |
| Registered model | `workspaces/default/modelProviders/<provider>/models/<model>` | Traffic evaluated for that model registration |
| ToolServer | `workspaces/default/toolServers/<server>` | Applicable traffic through that MCP server |

The current skill supports only the implicit default workspace. Provider
registrations and arbitrary named asset groups are not policy hosts.
An alias references backend models; it is not their ARM parent or their
underlying deployment.

Effective configuration includes both compatible inherited workspace rules
and direct asset rules. A looser direct allowance does not remove a workspace
guardrail. Applicability and runtime evaluation order are separate questions;
display order alone proves neither precedence nor override behavior.

## Accounting model

An allowance policy consists of a policy instance, a traffic boundary, a
caller partition, a quantity, and a period. Resolve all five before selecting
its configuration.

**Traffic boundary.** Counting-policy JSON uses `scope: "workspace"` on a
workspace host and `scope: "resource"` on an alias, model, or ToolServer.
Workspace accounting includes applicable workspace traffic. Alias accounting
includes its backend pool. Separate asset attachments establish separate
policy instances even when their settings or names match. Shared accounting
therefore requires a supported common traffic boundary, not a batch of
identical policies.

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
or defaults a value and is not equivalent to explicitly selecting `[]`.

**Quantity and period.** Token limits use positive counts and periods
`minute`, `hour`, or `day`. Request limits use positive request counts and
positive intervals in seconds. Cost limits use nonnegative estimated USD
amounts and periods `hour`, `day`, `week`, `month`, or `year`. Request units
need runtime context: MCP transport activity, actual tool executions, model
requests, and tokens are different measurements.

**Policy identity.** Preserve existing IDs. A cost policy's stable `id`
identifies its spend counter; changing it starts a new counter. Moving
attachments or changing scope/dimensions changes accounting, even when
the numeric allowance stays the same.

Cost accounting charges observed usage after responses. Admitted concurrent
requests can overshoot an allowance, and missing prices can undercount.
A cost limit is an estimated-cost control rather than an Azure billing cap
or guaranteed hard spending ceiling.

### Cost override semantics

Overrides select an allowance within an Identity-partitioned cost policy.
They require Identity as the only dimension; empty, IP, and composite
partitions are incompatible. Entries are ordered and the first match wins.
Selectors can use `apiKeyResourceId` or exact validated token `claims`;
all claims in a selector must match.

An override changes each matching identity's allowance, not the counter
partition. Matching several identities to one department claim does not
pool their spend into a department budget. The policy neither issues claims
nor creates a new caller dimension.

## Native configuration paths

| Host | Read path | Authoring path |
| --- | --- | --- |
| Workspace | `policy list` | `policy set`, specialized token/cost/rate/IP setters, and type-based `remove` |
| Model | `model policy list` or `model show` | First-class token/cost setters for compatible policies; `model update --policies @file` for an explicit complete array |
| Alias | `model-alias show` | `model-alias update --policies @file` |
| ToolServer | `mcp show` | `mcp update --policies @file` |

All commands are prefixed with `az aigateway` and use the exact resolved
subscription/gateway/asset selectors. The installed baseline exposes
`policy list`, not `policy show`. There is no native arbitrary workspace
policy-array write or provider-policy command.

Workspace counting setters write `scope: "workspace"`. Reviewed model
setters do not always add explicit resource scope when creating a policy;
inspect the resulting scope and use the complete native host-array path
with explicit `scope: "resource"` when needed. There is no generic `--scope`
option to supply that field.

First-class setters preserve unrelated types but may consolidate duplicate
same-type entries. Raw `--policies @file` replaces the complete host array.
These paths are not interchangeable when several policy instances must
remain distinct.

## Deriving a policy change

1. Establish the workload constraints: protected assets, covered traffic,
   measurements, allowed quantities/periods, and caller partitions.
2. Read workspace and affected resource policies. Identify the existing
   effective controls and whether the requested behavior is already present.
3. Compose compatible instances from the catalogue. For each, determine its
   host, explicit accounting fields where applicable, required settings, and
   external prerequisites. One requirement can need several controls; some
   changes belong to routing or access configuration rather than a policy.
4. Compare the proposed effective rules with current state. Resolve choices
   that affect sharing, behavior, disruption, or cost; explain the resulting
   constraints in administrator terms before applying the smallest change.
5. Follow the common authorization/preservation rules and the native paths
   above. Verify persisted configuration separately from runtime effects.

Inspection examples use the [resolved variables](../SKILL.md):

```bash
az aigateway policy list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
az aigateway model policy list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" -o json
```

These return arrays. Alias and ToolServer reads expose `properties.policies`.
Record exact host IDs, policy IDs/types, scope, dimensions, quantities,
periods, and siblings; a policy's UI index is not a stable identity.

## Configuration examples

Values below illustrate valid shapes, not universal operating defaults.
Raw objects are entries to merge into the **complete intended host array**.
The selected native host update receives that array as `--policies @file`.

### Token limit

Workspace token configuration:

```bash
az aigateway policy set --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" \
  --token-limit 30000 --token-period minute --token-counter-key Identity
```

This defines a per-identity workspace allowance. A directly attached alias
or model policy uses resource scope:

```json
{
  "type": "tokenLimit",
  "scope": "resource",
  "count": 10000,
  "period": "minute",
  "counterKey": ["identity"]
}
```

For an alias, apply the reviewed full array with:

```bash
az aigateway model-alias update --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" --policies @policies.json
```

For a model, use `model update` with provider/model selectors.
`model policy set` and `set-token-limit` also support compatible partial
updates, subject to the scope and duplicate-entry semantics above.

### Cost limit

An explicit empty dimension array defines pooled accounting.
`no-dimensions.json` contains:

```json
[]
```

```bash
az aigateway policy set --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --cost-id workspace-monthly-budget \
  --cost-limit 1000 --cost-period month --cost-counter-key @no-dimensions.json
```

Use the selected amount/period and preserve an existing policy's ID on
update. `model policy set` and `set-cost-limit` provide model-level paths
for compatible policies. A resource-hosted cost policy with an override:

```json
{
  "type": "costLimit",
  "id": "department-budget",
  "scope": "resource",
  "amount": 100,
  "period": "day",
  "counterKey": ["identity"],
  "overrides": [{"claims": {"department": "support"}, "amount": 25}]
}
```

Each matching identity receives its own $25 allowance at this policy scope;
unmatched identities use the default. Preserve override order and unknown
existing variants. The reviewed `--cost-overrides` item schema declares no
properties, so verified raw resource-host shapes are the available path;
native arbitrary workspace override authoring is not established.

### Request rate limit

Workspace request configuration:

```bash
az aigateway policy set --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" \
  --calls-per-period 60 --period-seconds 60 --rate-counter-key Identity
```

A resource-local pooled request policy:

```json
{
  "type": "requestRateLimit",
  "scope": "resource",
  "callsPerPeriod": 60,
  "periodSeconds": 60,
  "counterKey": []
}
```

Attach to a compatible alias, model, or ToolServer through its native
complete-array update. A ToolServer policy accounts for applicable server
traffic, not an independently scoped source or individual tool.

### IP filter

After confirming access impact:

```bash
az aigateway policy set --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" \
  --ip-filter-mode Allow --ip-addresses "$AUTHORIZED_CIDR"
```

A resource-hosted `ipFilter` entry uses `action: "Allow"` or `"Deny"` and
`cidrRanges`. It has no caller allowance counter. Use the actual authorized
range; adding an allow list can exclude existing clients.


### Tool threat protection

```json
{"type": "toolThreatProtection", "preInvocation": true, "postInvocation": false}
```

Tool threat protection is part of Microsoft Agent 365 and requires an
Agent 365 license. At least one phase must be enabled. This ToolServer-only
policy also requires supported evaluation-service access and a delegated Entra user token;
app-only calls are not equivalent. A denied post-invocation evaluation can
withhold a result but cannot undo the tool execution.

### Agent hooks

Agent hooks let a trusted decision service allow or deny an MCP tool action
at the gateway boundary. Use a **before-tool** check to prevent an action
such as an excessive refund; use an **after-tool** check to screen returned
data before the caller receives it. An after-tool denial cannot undo an
action that has already run.

Read [Agent hooks policy: concepts, decisions, and limitations](https://ai.gateway.azure.com/docs/policies/agent-hooks)
for the gateway's supported Agent Hooks contract, and
[Create a pre-tool call hook](https://ai.gateway.azure.com/docs/policies/create-pre-tool-call-hook)
for a working callback and allow/deny verification procedure.
Hooks do not themselves implement a guardrail: the callback must evaluate
the tool context and return the intended `allow` or `deny` verdict.

For an existing, trusted Azure Function callback, a pre-tool policy entry is:

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

To configure it:

1. Select the ToolServer and choose `preToolCall` to block execution or
   `postToolCall` to withhold results. The current portal supports one agent
   hooks policy and one intervention point per server; do not infer support
   for both from the free-form CLI policy argument.
2. Obtain the existing HTTPS callback URL, its authentication details, and
   approval to send it tool arguments/results. Callback deployment and access
   grants are external prerequisites. Keep credentials out of the endpoint
   URL; replace the example key only in approved protected input, not source
   control, logs, or replay scripts.
3. Keep `mode: "failClosed"` when a failed or invalid callback response must
   block the action/result. Choose `failOpen` only with explicit approval to
   let it proceed when evaluation is unavailable. This is failure handling,
   not a replacement for the callback's normal allow/deny decision.
4. Merge the entry into the ToolServer's complete policy array, preserving
   its other entries and stable IDs. After confirming replacement impact,
   apply with `az aigateway mcp update` and `--policies @policies.json`,
   using the resolved subscription/gateway/server selectors.
5. Read back the policy, then separately authorize safe allow and deny test
   calls. Match callback verdicts with backend execution evidence: a blocked
   request alone could be a callback failure under fail-closed behavior,
   not proof that the intended guardrail matched.

Use the selected callback's verified authentication schema. Anonymous
authentication is only for deliberately public callbacks, not a way to skip
credential setup. Do not retry side-effecting tool calls merely because a
post-tool hook withheld their results.

## Mutation and verification

Preserve unrelated entries, IDs, order, and credentials from fresh
authoritative state. Confirm complete-array replacement or policy weakening.
If secret or unsupported fields cannot safely round-trip, stop rather than
reconstructing them from redacted output.

Type-based `model policy remove` exposes `--remove-token-limit true` and
`--remove-cost-limit true`. Workspace `policy remove` also exposes
`--remove-rate-limit true` and `--remove-ip-filter true`. Removal can affect
multiple same-kind entries; selecting one resource-hosted entry instead
requires an explicitly reviewed full-array edit. No unexposed `--all` or
standalone policy ARM deletion is implied.

Model first-class policy writes and alias/MCP updates have their own
conditional handling. Raw model and workspace writes do not provide blanket
atomic concurrency protection. Conflicts require fresh reads and a new
decision, not wildcard overwrites. Multi-host changes are sequential and
may partially succeed.

Re-read workspace and affected hosts. Verify attachment, explicit accounting
scope, dimensions, quantities, periods, stable IDs, override order, and
retained siblings. Explain which effective controls now apply. Management
read-back establishes configuration, not counter enforcement, runtime request
units, failure behavior, or external evaluation success; those require
separately authorized bounded verification.
