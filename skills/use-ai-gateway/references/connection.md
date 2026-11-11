# Find gateway endpoints and assets

Use supplied runtime details first. A gateway host alone does not identify its
model aliases or MCP servers. Azure management reads are optional and use the
current Azure CLI identity; runtime invocation requires separate data-plane
authorization.

## Discover with Azure CLI

If the user has not supplied a subscription, inspect the existing context:

```bash
az account show --query '{subscription:id,tenant:tenantId}' -o json
```

List typed gateways only in the selected subscription:

```bash
az resource list --subscription "$SUBSCRIPTION_ID" \
  --resource-type Microsoft.ApiManagement/aigateways \
  --query '[].{id:id,name:name,resourceGroup:resourceGroup}' -o json
```

If several gateways match, ask the user to select one. Do not guess its
resource ID, subscription, tenant or runtime hostname. A resource of type
`Microsoft.ApiManagement/service` with `sku.name: AIGateway` is the deprecated
resource type; direct its owner to migration rather than constructing its
runtime contract here.

Read only the root and collections needed for the task. Use the root API
version for the gateway and the child API version for collections:

```bash
ARM="$(az cloud show --query endpoints.resourceManager -o tsv)"
RID="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.ApiManagement/aigateways/$GATEWAY"
az rest --method get --url "${ARM%/}${RID}?api-version=2026-05-01" \
  --query '{id:id,type:type,hostname:properties.frontend.defaultHostname}'
```

Child collections use `2025-09-01-preview`:

| Needed information | GET path below `$RID` |
| --- | --- |
| Published model aliases | `/workspaces/default/aliases` |
| Published MCP servers | `/workspaces/default/toolServers` |
| Key names and metadata only | `/apiKeys` |

For example, list aliases with:

```bash
az rest --method get --url \
  "${ARM%/}${RID}/workspaces/default/aliases?api-version=2025-09-01-preview"
```

Replace `aliases` with `toolServers` or `apiKeys` for the other collections.
Follow `nextLink` pages. Never call `listSecrets` for endpoint discovery. A
denied, failed or partial read is not an empty catalog; stop that read and
report its scope. If the user wants to continue Azure inventory after a denied
ARM read, ask the gateway owner for management read access to the selected
gateway and required child assets; runtime invocation roles do not grant this
access.

Use `https://` plus `properties.frontend.defaultHostname` as the runtime
origin. If the frontend hostname is absent, ask the gateway owner for
the published runtime hostname.

## Without management access

Continue with supplied runtime details. Ask an authorized asset owner for only
what is missing:

- **Model:** full operation URL, exact alias, supported API format.
- **MCP:** published gateway MCP endpoint, supported protocol/version and
  client instructions.
- **Authentication:** an existing secure key binding or approved Entra sign-in,
  plus the required runtime role/scope.

Do not require an ARM ID or elevated management permission to use a known
runtime endpoint. Management roles do not imply permission to invoke models or
tools, and runtime roles do not imply permission to list gateway resources.
