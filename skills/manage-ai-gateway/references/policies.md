# Governance policy reference

Counter dimensions and JSON payload schemas for `properties.policies` on workspaces, models, aliases, and MCP ToolServers.

## Counter dimensions (`counterKey`) and `scope`

| Counter mode | Wire JSON `counterKey` | CLI setter flag value | Behavior |
| --- | --- | --- | --- |
| Per caller identity | `["identity"]` | `Identity` (default) | Separate counter per Entra caller or API key |
| Per client IP | `["ipAddress"]` | `IPAddress` | Separate counter per client IP |
| Per identity + IP | `["identity", "ipAddress"]` | `Identity IPAddress` | Separate counter per `(identity, IP)` combination |
| Pooled across callers | `[]` | `@empty-array.json` (`[]`) | Single shared budget across all callers hitting the policy |

- Workspace setters write `"scope": "workspace"`. Asset-level policies in `--policies @file` use `"scope": "resource"`.
- Workspace/model counting setters merge supplied fields into the first entry of that type (removing duplicate entries of that type). `--policies @file` on `model`, `model-alias`, or `mcp update` **replaces the entire policy array**—merge into the current array from `show`/`policy list`.

## Policy JSON schemas (for `--policies @file`)

### `tokenLimit` (models, aliases)

```json
{"type": "tokenLimit", "scope": "resource", "count": 30000, "period": "minute", "counterKey": ["identity"]}
```
- `period`: `"minute"`, `"hour"`, or `"day"`.

### `costLimit` (models, aliases)

```json
{
  "type": "costLimit",
  "id": "team-daily-budget",
  "scope": "resource",
  "amount": 100.0,
  "period": "day",
  "counterKey": ["identity"],
  "overrides": [
    {"claims": {"tid": "<tenant-id>", "oid": "<object-id>"}, "amount": 250.0},
    {"apiKeyResourceId": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/aigateways/<gw>/workspaces/default/apiKeys/<key>", "amount": 25.0}
  ]
}
```
- `period`: `"hour"`, `"day"`, `"week"`, `"month"`, or `"year"` (fixed UTC calendar windows).
- Preserve `id` on updates; changing `id` resets the spend counter.
- `overrides` requires `"counterKey": ["identity"]`; first match wins and sets per-identity allowances (does not pool multiple callers).

### `requestRateLimit` (models, aliases, ToolServers)

```json
{"type": "requestRateLimit", "scope": "resource", "callsPerPeriod": 60, "periodSeconds": 60, "counterKey": ["identity"]}
```

### `ipFilter` (models, aliases, ToolServers)

```json
{"type": "ipFilter", "action": "Allow", "cidrRanges": ["203.0.113.0/24"]}
```
- `action`: `"Allow"` or `"Deny"`.

### `toolThreatProtection` (MCP ToolServer only)

```json
{"type": "toolThreatProtection", "preInvocation": true, "postInvocation": false}
```
- Enable at least one phase (`preInvocation` or `postInvocation`). Requires Agent 365 / Defender / Purview licensing and delegated Entra user tokens.

### `agentHooks` (MCP ToolServer only)

```json
{
  "type": "agentHooks",
  "id": "review-hook",
  "scope": "resource",
  "hooks": {
    "preToolCall": {
      "endpoint": "https://<function-app>/api/pre-tool-call",
      "mode": "failClosed",
      "authorization": {
        "type": "apiKey",
        "apiKey": {"headerName": "x-functions-key", "value": "<secret>"}
      }
    }
  }
}
```
- Phases: `preToolCall` and/or `postToolCall`. `mode`: `"failClosed"` (default) or `"failOpen"` (confirm before weakening).
- `authorization.type`: `"apiKey"` (omit unchanged `value` on updates), `"managedIdentity"` (`{"type": "managedIdentity", "managedIdentity": {"resource": "<audience>", "clientId": "<optional-uami-client-id>"}}`), or `"anonymous"`.


