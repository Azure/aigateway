# Find and connect to the gateway

Use a supplied runtime URL immediately when it is sufficient for the task.
Management discovery is optional; an ARM ID alone does not establish permission.

## Try scoped discovery, then ask

When details are missing, inspect the existing Azure context without changing it:
`az account show --query '{subscription:id,tenant:tenantId}' -o json`.
With an existing sign-in and a supplied or unambiguous current subscription,
try a relevant read under that identity. Permission need not be known before
the first read; a denial is the boundary, not a reason to try another identity.
If there is no sign-in, do not initiate one just for optional inventory.

For example, list typed gateways in the selected subscription:

```bash
az resource list --subscription "$SUBSCRIPTION_ID" \
  --resource-type Microsoft.ApiManagement/aigateways \
  --query '[].{id:id,name:name,resourceGroup:resourceGroup}' -o json
```

Set `SUBSCRIPTION_ID` from the supplied or selected existing context, not a
guess. Add `--resource-group` when known to narrow the read. Resolve an exact
name/ID match; ask the user to choose if several candidates remain. Do not scan
other subscriptions or tenants automatically. A denied list does not prove a
supplied exact resource GET is denied, but do not probe arbitrary IDs.

The supported gateway resource type is `Microsoft.ApiManagement/aigateways`.
If supplied metadata or existing inventory identifies
`Microsoft.ApiManagement/service` with `sku.name` equal to `AIGateway`, explain
that these resources are deprecated and need migration to
`Microsoft.ApiManagement/aigateways` by an authorized administrator. Stop that
connection path; do not generate legacy requests, rewrite its resource ID or
perform the migration through this consumer skill. Other APIM services are not
AI Gateway resources. A runtime hostname alone does not establish a resource's
type; do not require new management access merely to classify a known endpoint.

Once resolved, use the root and child reads below. Stop denied collections,
preserve successful partial discovery, and ask only for the missing published
connection details. An empty successful list, denied read and ambiguous resource
are different outcomes. Keep helping with the runtime path in each case.

## Runtime-only connection

Use the published connection details supplied by the user,
application configuration, or an authorized asset owner. No ARM ID, subscription
enumeration or management sign-in is required to provide runtime help.

- For a model, obtain the full operation URL (or runtime origin plus published
  operation path), exact callable name and API format. The alias usually
  belongs in the request body, not the URL.
- For tools, obtain each known gateway MCP endpoint and its available connection
  instructions. A known server can expose its tools through authorized runtime
  `tools/list`; this does not enumerate other servers on the gateway.
- Establish the chosen authentication method and existing secure binding or
  approved sign-in flow. Do not ask the user to paste a key or token into chat.

A host alone cannot identify published aliases or MCP servers. Do not invent a
runtime model/server catalog API, guess asset names, or demand management
permission. After available authorized discovery, ask only for the missing
published connection detail. Still explain authentication, inspect URL/request
structure locally, and interpret returned
errors. A plausible route is not proof that an asset exists or is callable.

For this path, skip ARM inventory, provider/policy enrichment and key listing.
Use [models](models.md) or [MCP](mcp.md) for URL/protocol and integration rules,
and [authentication](authentication.md) for runtime credentials. Use
[diagnostics](diagnostics.md) for errors. Mark backend/routing/filter/policy
configuration unknown unless supplied by an authorized source. Missing metadata is not missing
runtime permission, absent governance, or a reason to block useful guidance.

## Management-enriched connection

When reads are permitted, use the resolved ARM ID and read only relevant
permitted collections. A failed or denied
collection remains unavailable; continue runtime-only work where possible
instead of retrying discovery under another identity. If only a name/host is
known, resolve the resource with authorized reads or request its identity only
for this management path. Never guess a subscription or choose an ambiguous
resource. Use the supported resource identity:

```text
/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/aigateways/<gateway>
```

Preserve the leading slash and exact resource identity. The workspace is `default`.

Use `az rest` for authenticated ARM reads; it handles the management token
without printing or copying it. Resolve the current cloud's ARM endpoint with
`az cloud show --query endpoints.resourceManager -o tsv`. Child-resource reads
use `2025-09-01-preview`. For the gateway root GET, use `2026-05-01`.
Keep root and child API versions distinct. These are the
documented contracts for this skill; if an API version is rejected, verify the
current Azure AI Gateway documentation rather than cycling arbitrary versions.

For example, after resolving the supported gateway's `RID`:

```bash
ARM="$(az cloud show --query endpoints.resourceManager -o tsv)"
ARM="${ARM%/}"
az rest --method get --url "$ARM$RID?api-version=2026-05-01" \
  --query '{id:id,type:type,state:properties.provisioningState,gatewayUrl:properties.gatewayUrl,hostname:properties.frontend.defaultHostname}'
```

Read only the metadata needed for discovery:

| Purpose | GET path below the gateway ARM ID |
| --- | --- |
| Published model aliases | `/workspaces/default/aliases` |
| Registered backend models, when authorized | `/workspaces/default/models` |
| Relevant provider metadata, when needed and authorized | `/workspaces/default/modelProviders` |
| MCP tool servers | `/workspaces/default/toolServers` |
| Existing key metadata, only when needed | `/apiKeys` |
| Last-resort runtime hostname metadata | `/workspaces/default/subscriptions` |

Follow ARM `nextLink` pagination, retaining the selected cloud/gateway scope.
Reject unexpected origins or resource scopes before forwarding credentials.
Do not treat `403`, a failed page, or malformed responses as an empty inventory.
Report which collections were read and which remain unavailable.

Resolve the runtime origin in this order:

1. `properties.gatewayUrl` on the gateway.
2. `https://` plus `properties.frontend.defaultHostname`.
3. If both are absent, `properties.aiGateway.hostname` from authorized API-key
   metadata, then workspace-subscription metadata. Prefer the `default`
   subscription when it has a hostname.

Metadata reads do not authorize secret retrieval. For example,
`https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com` illustrates a
default runtime origin; its generated identifier cannot be derived from the
gateway name. Use the actual published hostname. If none is available, report
runtime discovery as pending/unavailable rather than guessing a host.

Validate an HTTPS origin without embedded credentials, query, or fragment and
remove its trailing slash. Respect private network reachability; do not change
networking to make a probe work.
