# Azure AI Gateway CLI command reference

This is the human-readable reference for the published **1.0.0b22** extension.
Start with [installation and quickstart](README.md). Use this page to find a
command, understand its purpose, and copy a configuration example. Use the
installed command's `--help` for all arguments and allowed values; help
supplements this reference rather than replacing it.

[Command groups](#command-groups) | [Resource selectors](#resource-selectors) |
[Models and aliases](#models-and-aliases) | [Policies](#policies) |
[MCP servers](#mcp-servers) | [Authentication](#authentication-and-keys) |
[Output and verification](#output-and-verification)

## Command groups

Prefix every entry below with `az aigateway`. This table lists the public
commands in the reviewed wheel, not hidden compatibility aliases.

| Group | Commands | Purpose |
| --- | --- | --- |
| Top level | `create`, `show`, `list`, `update`, `delete`, `wait`, `version` | Gateway lifecycle, tags/tier, and installed version |
| `model-provider` | `create`, `show`, `list`, `update`, `delete`, `sync` | Backend connection and model registration reconciliation |
| `model` | `create`, `show` (`get`), `list`, `update`, `delete` | Register existing backend models and their protocol metadata |
| `model-alias` | `create`, `set`, `show`, `list`, `update`, `delete` | Publish callable names and priority/weight target pools |
| `model policy` | `list`, `set`, `set-token-limit`, `set-cost-limit`, `set-content-safety`, `remove` | Model-local policy configuration; content safety is legacy-only |
| `policy` | `list`, `set`, `set-token-limit`, `set-cost-limit`, `set-rate-limit`, `set-ip-filter`, `set-content-safety`, `remove` | Default-workspace controls; content safety is legacy-only |
| `mcp` | `create`, `show`, `list`, `update`, `delete`, `authorize` | ToolServer registration and configured backend OAuth initiation |
| `mcp source` | `add`, `list`, `remove` | Individual backend source membership |
| `api-key` | `create`, `show`, `list`, `update`, `delete`, `list-secrets`, `regenerate` | Inbound gateway-wide client keys |
| `identity` | `assign`, `show`, `remove`, `wait` | Outbound gateway managed identities |
| `network` | `show`, `update`, `wait` | Public ingress and outbound subnet integration |
| `network private-endpoint-connection` | `list`, `show`, `approve`, `reject`, `delete`, `wait` | Gateway-side private endpoint connection decisions |
| `telemetry-exporter` | `create`, `show`, `list`, `update`, `delete` | Telemetry destinations and export configuration |

```bash
az aigateway version
az aigateway model-alias create --help
az aigateway mcp source add --help
```

There is no `policy show`, `telemetry-exporter wait`, or
`model-alias create --overwrite` in this release. Use `policy list`,
bounded exporter read-back, and explicit alias `update` respectively.
`model-alias set` is an intentional create-or-update operation, not a
create-only safeguard.

The CLI does not currently expose `az aigateway migration collect-source`,
`validate`, `apply`, or `report`. The
[migration skill](../skills/migrate-ai-gateway/SKILL.md) provides local
assessment/planning helpers and delegates destination writes to native
resource commands. Do not treat proposed migration commands as available.

## Resource selectors

Examples use Bash and explicit subscriptions. Replace placeholders before
running them; these are independent examples, not one deployment script.

```bash
SUBSCRIPTION="<subscription-id>"
RG="<existing-resource-group>"
GATEWAY="<gateway-name>"
PROVIDER="<provider-registration-name>"
MODEL="<model-registration-name>"
ALIAS="<alias-resource-name>"
ROUTING_NAME="<callable-model-name>"
```

| Target | Selectors |
| --- | --- |
| Gateway | `--subscription "$SUBSCRIPTION" -g "$RG" -n "$GATEWAY"` |
| Provider, alias, MCP server, or API key | `--subscription "$SUBSCRIPTION" -g "$RG" --gateway-name "$GATEWAY" -n "<child-name>"` |
| Model or model policy | The child selectors above, plus `--provider-name "$PROVIDER"` |

`-g` means `--resource-group`; `-n` means `--name`. A child name does not
identify the parent gateway. Use exact `--ids` only where that command's
help exposes it. Verify returned resource IDs/types, especially where a
name can also match a legacy API Management `service`.
This guide targets `Microsoft.ApiManagement/aigateways` and its implicit
`default` workspace.

Use JSON files for structured arguments that support `@file`. The file must
contain the advertised object/array, not a string holding JSON. Files do
not interpolate environment variables. Protect secret-bearing files and
keep them out of source control.

## Models and aliases

**An alias is required to publish a model route.** The client request's
`model` is the alias's `properties.aliasName`, not the registered model's
deployment name or ARM ID. Providers and models supply the backend
configuration; an alias connects the callable name to one or more models.

### Register a provider and model

For a Foundry provider, prepare existing backend access for the gateway
identity first. `foundry.json`:

```json
{
  "endpoint": "https://<account>.openai.azure.com/",
  "resourceIds": ["/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>"],
  "authentication": {
    "kind": "ManagedIdentity",
    "managedIdentity": {"resource": "https://cognitiveservices.azure.com/"}
  }
}
```

`deployment.json` describes an existing backend deployment:

```json
{
  "modelName": "<backend-model-name>",
  "resourceId": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/deployments/<deployment>"
}
```

```bash
az aigateway model-provider create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" \
  --kind Foundry --foundry @foundry.json
az aigateway model create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --deployment-config @deployment.json --api-format OpenAIChatCompletions \
  --supported-endpoints /v1/chat/completions
```

Use the selected backend's actual protocol/operation path, not this example
for every model. Low-level create uses `--deployment-config`; general
`model update` uses `--deployment` with a JSON object.

The convenience `model-provider create --foundry-resource-id "<account-id>"`
imports every deployment, enables gateway identity, and grants **Foundry User**
on that account. `model create --foundry-resource-id "<account-id>"
--deployment "<deployment-name>"` onboards one deployment with external
access setup. These require additional permission and explicit intent.
Neither creates the underlying deployments.

### Publish a one-target alias

```bash
MODEL_ID="$(az aigateway model show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --query id -o tsv)" || exit 1
if [ -z "$MODEL_ID" ] || [ "$MODEL_ID" = "null" ]; then
  printf '%s\n' 'No model registration ID returned; stop before alias creation.' >&2
  exit 1
fi
az aigateway model-alias create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" --routing-name "$ROUTING_NAME" \
  --backend-model resource-id="$MODEL_ID" priority=0 weight=100
az aigateway model-alias show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" -o json
```

### Share traffic or prefer a fallback

An alias holds one to 30 unique model registration IDs under the same gateway.
For multiple targets, explicitly supply integer priority `0-100` and
weight `1-100` on each target.

| Intent | Example configuration | Meaning |
| --- | --- | --- |
| Active-active or canary | A: priority 0, weight 75; B: priority 0, weight 25 | Same tier, relative 3:1 request share among eligible models |
| Preferred/fallback | A: priority 0, weight 100; B: priority 1, weight 100 | Prefer A's tier; B is not an ordinary weighted share while A can serve |

Weights need not sum to 100. Priority chooses the preferred tier; weights
split traffic within that tier. Replacing an alias's backend list replaces
the **whole pool**. Preserve unrelated policies and settings.
See [routing examples and failover verification](../skills/manage-ai-gateway/references/models-and-routing.md#alias-pool).

### Reconcile provider registrations

```bash
az aigateway model-provider sync --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" --dry-run
```

Review additions, stale removals, and alias dependencies before applying
without `--dry-run`. Request `--create-default-aliases true` only when
1:1 aliases are intended, and include it in both preview and apply.
Sync is sequential, not transactional. It does not provision backend
deployments; a failed discovery is not evidence that deployments are absent.

## Policies

Workspace policies are shared defaults; model/alias policies attach to those
assets. For a workspace token allowance of 30,000 tokens per minute per caller:

```bash
az aigateway policy set --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" \
  --token-limit 30000 --token-period minute --token-counter-key Identity
az aigateway policy list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
```

`Identity` separates counters by authenticated identity or shared API key;
it does not pool a department's users together. Token, request, and cost
limits measure different quantities. Cost limits are estimated controls,
not a hard Azure billing cap.

Use the [policy reference](../skills/manage-ai-gateway/references/policies.md)
for model-local setters, rate/IP controls, accounting dimensions, tool
threat protection, and agent hooks. `--policies @file` on a compatible asset
replaces its complete policy array; retain existing IDs and unrelated entries.
Content-safety flags are visible but are **not supported on typed
`aigateways`** in this baseline; do not copy legacy `service` examples.

## MCP servers

`mcp create --endpoints @endpoints.json` registers an endpoint array; see the
[quickstart](README.md#2-register-a-public-mcp-server) for a complete example.
Use `mcp source add/list/remove` to edit individual sources. A full endpoint
array update changes complete membership and may involve credentials.

`mcp authorize` initiates OAuth for a selected persisted backend endpoint.
It is not the caller's gateway login and does not prove authorization
completed. See [MCP configuration and OAuth lifecycle](../skills/manage-ai-gateway/references/mcp.md).
Tool discovery and execution need a separately authorized runtime client,
not just `mcp show`.

## Authentication and keys

Prefer caller Entra OAuth tokens with the appropriate gateway data-plane role.
Configure gateway-to-backend managed identity separately, with grants on
the selected model or tool target. An ARM management token, gateway runtime
token, and backend token are not interchangeable.

`api-key list/show` return metadata. `list-secrets` returns sensitive values
and requires explicit authorization and protected handling. Keys grant
gateway-wide access, not per-asset roles. Rotate one primary/secondary value
at a time using `api-key regenerate --key-type primary|secondary`, move
clients, and confirm cutover before rotating the other.
See [authentication, key storage, rotation, and identity commands](../skills/manage-ai-gateway/references/keys-and-identities.md).

## Output and verification

Use `-o table` for an overview, `-o json` for complete metadata, and
`--query ... -o tsv` for a selected nonsecret field:

```bash
az aigateway show --subscription "$SUBSCRIPTION" -g "$RG" -n "$GATEWAY" \
  --query '{id:id,state:properties.provisioningState,url:properties.gatewayUrl}' -o json
```

For list commands exposing `--max-items` and `--next-token`, retain and
follow continuation tokens before claiming an inventory is complete.
For asynchronous operations, use the matching `wait` and a bounded timeout
where exposed; otherwise use bounded read-back. Acceptance is not completion.

Management reads establish saved configuration, not successful inference,
MCP tool exposure, policy enforcement, or telemetry ingestion.
Runtime clients use the gateway URL and published alias/MCP endpoint.
Do not bypass the gateway or switch caller identities to hide a failure.

Gateway deletion affects consumers and can retain a soft-delete record.
Deleting a model registration does not delete its external deployment.
Private endpoint connection commands manage the gateway-side connection,
not the backing private endpoint or DNS.
