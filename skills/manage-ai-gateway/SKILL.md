---
name: manage-ai-gateway
version: 1.0.0
description: Create, configure, administer, troubleshoot, and operate Microsoft.ApiManagement/aigateways resources with the official Azure AI Gateway CLI. Manage providers, models, aliases, MCP sources, policies, client keys, managed identities, networking, private endpoint connections, and telemetry. Use for administrator tasks, not application integration or APIM migration.
---

# Manage Azure AI Gateway

Manage `Microsoft.ApiManagement/aigateways` resources (`default` workspace) with `az aigateway` (or `az aig`). Never use `az rest` or target legacy `Microsoft.ApiManagement/service` (use [`migrate-ai-gateway`](../migrate-ai-gateway/SKILL.md) for APIM migration). External resources must already exist; only RBAC role assignments required for gateway operation may be created via `az role assignment create` after confirmation.

## Prerequisites and target resolution

Discover missing context with Azure CLI before asking the user. Ask only when multiple candidates match or external values (new gateway region, custom URL, or secret) cannot be discovered.

1. **Extension**: Run `az aigateway version`. If missing, ask approval to install via `curl -fsSL https://aka.ms/aigateway-cli-install | bash` (`cli/install.ps1` on Windows).
2. **Subscription**: Resolve `SUB` from user input or `az account show --query id -o tsv`. Pass `--subscription "$SUB"` on every command so name-based commands do not fall back to the default subscription.
3. **Discovery**: Resolve omitted gateways (`az aigateway list --subscription "$SUB" [-g "$RG"] -o json`, filtering `type == "Microsoft.ApiManagement/aigateways"`), Foundry accounts/deployments (`az cognitiveservices account list` / `deployment list`), identities (`az identity list`), subnets (`az network vnet subnet list`), or Application Insights (`az resource show`).

```bash
SUB="<subscription-id>"
RG="<resource-group>"
GW="<gateway-name>"
GATEWAY_ID="/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GW"
```

| Target resource | Selector flags (always include `--subscription "$SUB"`) |
| --- | --- |
| Gateway (`create`, `show`, `update`, `delete`, `wait`), `identity`, `network` | `-g "$RG" -n "$GW"` (or `--ids "$GATEWAY_ID"`, except on `create` and `identity`) |
| Workspace children (`model-provider`, `model-alias`, `mcp`, `api-key`, `telemetry-exporter`, `network private-endpoint-connection`) | `-g "$RG" --gateway-name "$GW" -n "<child-name>"` (`telemetry-exporter` has no `--ids`) |
| Workspace policies (`policy`) | `-g "$RG" --gateway-name "$GW"` |
| Provider children (`model`, `model policy`) | `-g "$RG" --gateway-name "$GW" --provider-name "$PROVIDER" -n "$MODEL"` |
| MCP sources (`mcp source`) | `-g "$RG" --gateway-name "$GW" --tool-server-name "$MCP_NAME" [--namespace "$NS"]` |

## Create a gateway

Check `az aigateway list --subscription "$SUB" -g "$RG" -o json` first to avoid overwriting an existing gateway.

```bash
az aigateway create --subscription "$SUB" -g "$RG" -n "$GW" --location "$LOCATION" \
  [--system-assigned true] [--subnet "$SUBNET_ID"] [--tags env=prod]

az aigateway update --ids "$GATEWAY_ID" --subscription "$SUB" [--tags @tags.json] [--sku Standard]
az aigateway delete --ids "$GATEWAY_ID" --subscription "$SUB" --yes
```

- `--sku` defaults to `Standard`. `--user-assigned` is rejected on `create`; attach UAMIs afterwards with `az aigateway identity assign`.
- `--subnet` requires a same-region subnet delegated to `Microsoft.App/environments`.
- Runtime URL: `properties.gatewayUrl` (or `properties.frontend.defaultHostname`).
- `--tags` replaces all tags—merge existing tags from `show` first. `delete` leaves a soft-delete record ([references/gateway-lifecycle.md](references/gateway-lifecycle.md)).

## Configure gateway assets

### 1. Models, providers, and aliases (`model-provider`, `model`, `model-alias`)

Clients call **model aliases** (`properties.aliasName`, set via `--routing-name`), never provider or model registration names. Every `--backend-model` target must be a gateway model registration ARM ID (`$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$MODEL`), never a Foundry deployment ID.

```bash
# Onboard one Foundry deployment (enables system MI, grants Foundry User on account, creates/reuses provider + model)
az aigateway model create --subscription "$SUB" -g "$RG" --gateway-name "$GW" \
  --foundry-resource-id "$FOUNDRY_ACCOUNT_ID" --deployment "$DEPLOYMENT_NAME"

# Bulk-onboard all deployments in a Foundry account
az aigateway model-provider create --subscription "$SUB" -g "$RG" --gateway-name "$GW" \
  --foundry-resource-id "$FOUNDRY_ACCOUNT_ID"

# Reconcile Foundry provider with current deployments (preview first; apply deletes stale unaliased models)
az aigateway model-provider sync --subscription "$SUB" -g "$RG" --gateway-name "$GW" \
  -n "$PROVIDER" --create-default-aliases --dry-run

# Custom or low-level provider + model (see JSON schemas in references/models-and-routing.md)
az aigateway model-provider create --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$PROVIDER" --kind Custom --custom @custom.json
az aigateway model create --subscription "$SUB" -g "$RG" --gateway-name "$GW" --provider-name "$PROVIDER" -n "$MODEL" \
  --deployment-config '{"modelName":"<backend-model>"}' --api-format OpenAIChatCompletions --supported-endpoints /v1/chat/completions

# Create 1:1 default aliases for all models in a provider
az aigateway model list --subscription "$SUB" -g "$RG" --gateway-name "$GW" --provider-name "$PROVIDER" -o json \
  | az aigateway model-alias create

# Create or update an alias with weighted split (same priority) and fallback (higher priority number)
az aigateway model-alias set --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$ALIAS" --routing-name "$ROUTING_NAME" \
  --backend-model resource-id="$MODEL_A_ID" priority=0 weight=80 \
  --backend-model resource-id="$MODEL_B_ID" priority=0 weight=20 \
  --backend-model resource-id="$FALLBACK_MODEL_ID" priority=1 weight=100
```

- `--api-format`: `OpenAIChatCompletions`, `ResponsesApi`, `AnthropicMessages`. `model create` uses `--deployment-config`; `model update` uses `--deployment`.
- `model-alias set` creates or updates; `create` fails if the alias exists.
- Routing: `priority` (`0–100`, **lower serves first**: `0` primary, `1` fallback); `weight` (`1–100`, relative share within the same priority). `--backend-model` **replaces the entire pool** (1–30 models)—read `model-alias show` first to keep existing targets ([references/models-and-routing.md#alias-pool](references/models-and-routing.md#alias-pool)).

### 2. MCP ToolServers (`mcp`, `mcp source`)

Clients call `<gatewayUrl>/default/toolservers/<mcp-name>/mcp`. Each source's `namespace` prefixes its tools as `<namespace>_<tool>`.

```bash
az aigateway mcp create --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$MCP_NAME" \
  --endpoints '[{"kind":"mcp","namespace":"learn","required":true,"mcp":{"transport":"streamableHttp","url":"https://learn.microsoft.com/api/mcp"},"credentials":{"type":"none"}}]'

az aigateway mcp source add --subscription "$SUB" -g "$RG" --gateway-name "$GW" --tool-server-name "$MCP_NAME" \
  --namespace "$NS" --kind mcp --mcp '{"transport":"streamableHttp","url":"https://tools.example.com/mcp"}' \
  --credentials '{"type":"none"}' --required true

az aigateway mcp source remove --subscription "$SUB" -g "$RG" --gateway-name "$GW" --tool-server-name "$MCP_NAME" --namespace "$NS"
```

- No `mcp source update`: read `mcp show` and pass the full array to `mcp update --endpoints @endpoints.json` (keep `namespace` values and omit unchanged `credentials` to preserve stored secrets).
- `header` credential values are **string arrays** (`{"type":"header","headers":{"X-Api-Key":["<secret>"]}}`). See [references/mcp.md](references/mcp.md) for OpenAPI (`url` / `inline` base64), `managedIdentity`, `oauth2`, and `mcp authorize`.

### 3. Governance policies (`policy`, `model policy`, `--policies`)

| Host | Read | Write | Supported `type` values |
| --- | --- | --- | --- |
| Workspace (`default`) | `policy list` | `policy set`, `set-token-limit`, `set-cost-limit`, `set-rate-limit`, `set-ip-filter`, `remove` | `tokenLimit`, `costLimit`, `requestRateLimit`, `ipFilter` |
| Model | `model policy list` | `model policy set`, `set-token-limit`, `set-cost-limit`, `remove`, or `model update --policies @file` | `tokenLimit`, `costLimit`, `requestRateLimit`, `ipFilter` |
| Alias | `model-alias show` | `model-alias update --policies @file` | `tokenLimit`, `costLimit`, `requestRateLimit`, `ipFilter` |
| MCP ToolServer | `mcp show` | `mcp update --policies @file` | `requestRateLimit`, `ipFilter`, `toolThreatProtection`, `agentHooks` |

```bash
az aigateway policy set-token-limit --subscription "$SUB" -g "$RG" --gateway-name "$GW" --token-limit 30000 --token-period minute --token-counter-key Identity
az aigateway policy set-cost-limit --subscription "$SUB" -g "$RG" --gateway-name "$GW" --amount 100 --period month --cost-counter-key Identity
az aigateway policy set-rate-limit --subscription "$SUB" -g "$RG" --gateway-name "$GW" --rate-limit 60 --rate-period minute --rate-counter-key Identity
az aigateway policy set-ip-filter --subscription "$SUB" -g "$RG" --gateway-name "$GW" --ip-filter-mode Allow --ip-addresses 203.0.113.0/24
az aigateway policy remove --subscription "$SUB" -g "$RG" --gateway-name "$GW" --remove-token-limit true
```

- **Content safety (`set-content-safety`) is unsupported on `Microsoft.ApiManagement/aigateways`** (legacy `service` only).
- `--policies @file` on `model`, `model-alias`, or `mcp update` **replaces the entire `properties.policies` array**—read existing policies first and preserve other entries and `id` values ([references/policies.md](references/policies.md)).

### 4. Identities, RBAC, and caller API keys (`identity`, `api-key`)

```bash
az aigateway identity show --subscription "$SUB" -g "$RG" -n "$GW" -o json
az aigateway identity assign --subscription "$SUB" -g "$RG" -n "$GW" --system-assigned true
az aigateway identity assign --subscription "$SUB" -g "$RG" -n "$GW" --user-assigned "$UAMI_RESOURCE_ID"
az aigateway identity remove --subscription "$SUB" -g "$RG" -n "$GW" --user-assigned "$UAMI_RESOURCE_ID"

az aigateway api-key list --subscription "$SUB" -g "$RG" --gateway-name "$GW" -o json
az aigateway api-key create --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$KEY_NAME"
az aigateway api-key update --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$KEY_NAME" --state suspended
az aigateway api-key regenerate --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$KEY_NAME" --key-type secondary
```

- `identity show` exits with not-found if no identity is assigned yet. In asset JSON configs, `managedIdentity.clientId` takes the UAMI's **clientId** (omit for system-assigned); RBAC uses `principalId`.
- **RBAC**: Inbound Entra roles are `AI Gateway Models User` (alias/workspace), `AI Gateway Tools User` (ToolServer/workspace), and `AI Gateway User` (both). Outbound gateway MI uses `Foundry User` (`53ca6127-db72-4b80-b1b0-d745d6d5456d`) on Foundry accounts or `Monitoring Metrics Publisher` on App Insights DCRs ([references/keys-and-identities.md](references/keys-and-identities.md)).

### 5. Networking and private endpoint connections (`network`)

```bash
az aigateway network show --subscription "$SUB" -g "$RG" -n "$GW" -o json
az aigateway network update --subscription "$SUB" -g "$RG" -n "$GW" --subnet "$SUBNET_ID"
az aigateway network update --subscription "$SUB" -g "$RG" -n "$GW" --disable-vnet-integration true

az aigateway network private-endpoint-connection list --subscription "$SUB" -g "$RG" --gateway-name "$GW" -o json
az aigateway network private-endpoint-connection approve --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$PEC_NAME" --description "Approved"
```
`--subnet` and `--disable-vnet-integration` are mutually exclusive. Inbound private endpoints and `--public-network-access Disabled` are not effective on typed `aigateways` in the current preview ([references/networking.md](references/networking.md)).

### 6. Telemetry export (`telemetry-exporter`)

```bash
az aigateway telemetry-exporter list --subscription "$SUB" -g "$RG" --gateway-name "$GW" -o json
az aigateway telemetry-exporter create --subscription "$SUB" -g "$RG" --gateway-name "$GW" \
  -n "$EXPORTER" --kind OpenTelemetry --open-telemetry @otlp.json \
  [--application-insights "{\"resourceId\":\"$APPINSIGHTS_ID\"}"] --payload-capture false
```
For Application Insights, discover OTLP endpoints and `DataCollectionRuleResourceId` from the App Insights resource and grant the gateway identity `Monitoring Metrics Publisher` on that DCR. In `otlp.json`, `credentials.headers` is a **string-to-string** map ([references/telemetry-and-troubleshooting.md](references/telemetry-and-troubleshooting.md)).

## Operate

1. **Confirm only high-impact actions**: Execute requested creates, updates, and `--foundry-resource-id` onboarding directly. Ask confirmation before:
   - Deleting resources (`delete`) or applying `model-provider sync` when `--dry-run` plans deletions.
   - Dropping existing items in full-array updates (`--backend-model`, `--endpoints`, `--policies`, `--tags`, telemetry `attributes`) or weakening security policies.
   - Running standalone `az role assignment create` commands.
   - Rotating/suspending/deleting API keys, reading secrets (`api-key list-secrets`, `mcp authorize`), changing network/private-endpoint access, or enabling `--payload-capture true`.
2. **Protect secrets**: Never print raw keys, backend secrets, or OAuth links. Pass secrets via environment variables or temporary `0600` JSON files outside source control (`@file.json` does not expand `$ENV_VAR`). Never send redacted markers in updates.
3. **Verify**: Check command output and run `show`/`list` (or `wait --created/--updated/--deleted` after `--no-wait`) to confirm target fields and preserved sibling settings ([references/activities-and-cli-coverage.md](references/activities-and-cli-coverage.md)).

