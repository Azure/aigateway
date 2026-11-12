---
name: manage-ai-gateway
version: 1.0.0
description: Create, configure, administer, troubleshoot, and operate Microsoft.ApiManagement/aigateways resources with the official Azure AI Gateway CLI. Manage providers, models, aliases, MCP sources, policies, client keys, managed identities, networking, private endpoint connections, and telemetry. Use for administrator tasks, not application integration or APIM migration.
---

# Manage Azure AI Gateway

Manage `Microsoft.ApiManagement/aigateways` resources (`default` workspace) with `az aigateway` (or `az aig`). Never use `az rest` or target legacy `Microsoft.ApiManagement/service`; migrating an existing APIM workload is outside this skill, so do not read, convert, or replicate source APIM configuration here. External resources must already exist; only RBAC role assignments required for gateway operation may be created via `az role assignment create` after confirmation.

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
- Runtime URL: `properties.gatewayUrl` (or `properties.frontend.defaultHostname`).
- `--tags` replaces all tags—merge existing tags from `show` first. `delete` leaves a soft-delete record (`az apim deletedservice purge --service-name "$GW" --location "$LOCATION"` only if permanent purge is requested).
- See [references/gateway-lifecycle.md](references/gateway-lifecycle.md) for `--no-wait` polling.

## Configure gateway assets

### 1. Models, providers, and aliases (`model-provider`, `model`, `model-alias`)

Clients call **model aliases** (`properties.aliasName`, set via `--routing-name`), never provider or model registration names.

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

# Custom or low-level provider + model
az aigateway model-provider create --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$PROVIDER" --kind Custom --custom @custom.json
az aigateway model create --subscription "$SUB" -g "$RG" --gateway-name "$GW" --provider-name "$PROVIDER" -n "$MODEL" \
  --deployment-config '{"modelName":"<backend-model>"}' --api-format OpenAIChatCompletions --supported-endpoints /v1/chat/completions

# Create 1:1 default aliases for all models in a provider
az aigateway model list --subscription "$SUB" -g "$RG" --gateway-name "$GW" --provider-name "$PROVIDER" -o json \
  | az aigateway model-alias create

# Create or update an alias (`set` upserts; `create` fails if the alias exists)
az aigateway model-alias set --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$ALIAS" --routing-name "$ROUTING_NAME" \
  --backend-model resource-id="$MODEL_A_ID" priority=0 weight=80 \
  --backend-model resource-id="$MODEL_B_ID" priority=0 weight=20 \
  --backend-model resource-id="$FALLBACK_MODEL_ID" priority=1 weight=100
```

See [references/models-and-routing.md](references/models-and-routing.md) for low-level Foundry/Custom JSON schemas, `--api-format` and update flags, [alias pool routing rules](references/models-and-routing.md#alias-pool), and safe deletion order.

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

See [references/mcp.md](references/mcp.md) for OpenAPI/credential JSON schemas, editing existing sources (`mcp update --endpoints`), OAuth (`mcp authorize`), and tool filtering (`allowList`, `blocked`).

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
- Workspace/model setters merge supplied fields into the first entry of that type (there is no `policy show`; use `policy list`). `--policies @file` on `model`, `model-alias`, or `mcp update` **replaces the entire `properties.policies` array**—read existing policies first and preserve other entries and `id` values.
- See [references/policies.md](references/policies.md) for `counterKey` / `scope` values and JSON schemas (`costLimit` overrides, `toolThreatProtection`, `agentHooks`).

### 4. Identities, RBAC, and caller API keys (`identity`, `api-key`)

```bash
az aigateway identity show --subscription "$SUB" -g "$RG" -n "$GW" -o json
az aigateway identity assign --subscription "$SUB" -g "$RG" -n "$GW" --system-assigned true
az aigateway identity assign --subscription "$SUB" -g "$RG" -n "$GW" --user-assigned "$UAMI_RESOURCE_ID"
az aigateway identity remove --subscription "$SUB" -g "$RG" -n "$GW" --user-assigned "$UAMI_RESOURCE_ID"

az aigateway api-key list --subscription "$SUB" -g "$RG" --gateway-name "$GW" -o json
az aigateway api-key create --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$KEY_NAME"
az aigateway api-key update --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$KEY_NAME" --state suspended
```

`identity show` exits with not-found if no identity is assigned yet. See [references/keys-and-identities.md](references/keys-and-identities.md) for UAMI identifier mapping (`id` vs `clientId` vs `principalId`), inbound/outbound RBAC role IDs and `az role assignment` commands, secret retrieval (`list-secrets`), and staged key rotation (`regenerate`).

### 5. Networking and private endpoint connections (`network`)

```bash
az aigateway network show --subscription "$SUB" -g "$RG" -n "$GW" -o json
az aigateway network update --subscription "$SUB" -g "$RG" -n "$GW" --subnet "$SUBNET_ID"
az aigateway network update --subscription "$SUB" -g "$RG" -n "$GW" --disable-vnet-integration true
az aigateway network private-endpoint-connection list --subscription "$SUB" -g "$RG" --gateway-name "$GW" -o json
```

`--subnet` and `--disable-vnet-integration` are mutually exclusive. See [references/networking.md](references/networking.md) for delegated subnet requirements and private endpoint connection commands (`show`, `approve`, `reject`, `delete`, `wait`).

### 6. Telemetry export (`telemetry-exporter`)

```bash
az aigateway telemetry-exporter list --subscription "$SUB" -g "$RG" --gateway-name "$GW" -o json
az aigateway telemetry-exporter create --subscription "$SUB" -g "$RG" --gateway-name "$GW" \
  -n "$EXPORTER" --kind OpenTelemetry --open-telemetry @otlp.json \
  [--application-insights "{\"resourceId\":\"$APPINSIGHTS_ID\"}"] --payload-capture false
```

See [references/telemetry-and-troubleshooting.md](references/telemetry-and-troubleshooting.md) for Application Insights OTLP/DCR discovery, `otlp.json` schemas, claim attribute mappings, and troubleshooting (there is no `telemetry-exporter wait`; verify with `telemetry-exporter show`).

## Operate

1. **Confirm only high-impact actions**: Execute requested creates, updates, and `--foundry-resource-id` onboarding directly. Ask confirmation before:
   - Deleting resources (`delete`) or applying `model-provider sync` when `--dry-run` plans deletions.
   - Dropping existing items in full-array updates (`--backend-model`, `--endpoints`, `--policies`, `--tags`, telemetry `attributes`) or weakening security policies.
   - Running standalone `az role assignment create` commands.
   - Rotating/suspending/deleting API keys, reading secrets (`api-key list-secrets`, `mcp authorize`), changing network/private-endpoint access, or enabling `--payload-capture true`.
2. **Protect secrets**: Never print raw keys, backend secrets, or OAuth links. Pass secrets via environment variables or temporary `0600` JSON files outside source control (`@file.json` does not expand `$ENV_VAR`). Never send redacted markers in updates.
3. **Verify**: Check command output and run `show`/`list` to confirm target fields and preserved sibling settings. The CLI has no subcommands for model inference, MCP `tools/list` / `tools/call`, or KQL log queries; verify runtime traffic separately with an authorized HTTP/MCP client or `az monitor` query.
