# Gateway lifecycle

Use the [shared workflow](../SKILL.md) and its Bash scope variables.
The resource group and external dependencies must already exist.

## Choose the task and inspect effects

Choose provisioning, tags/SKU, or gateway deletion. For identity/network changes, use
[identity and access](keys-and-identities.md) or [networking](networking.md).
Provisioning publishes no callable assets; separately configure requested
[model aliases](models-and-routing.md) or [MCP ToolServers](mcp.md).
List scoped inventory; use `show` only for an existing target:

```bash
az aigateway list --subscription "$SUBSCRIPTION" --resource-group "$RG" -o json
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
```

Select `Microsoft.ApiManagement/aigateways`; retain legacy list matches for
the shared collision check. Inspect `id`, `type`, `location`, `tags`, `sku`,
`identity`, and `properties.provisioningState`. Discover the runtime URL
from returned metadata (`properties.frontend.defaultHostname` or
`properties.gatewayUrl`), not a fabricated hostname.

## Create

Choose a globally unique name and supported `aigateways` region. Check
registration and preview access; region availability alone does not establish
access. Hand registration, RG creation, and other missing prerequisites to the
owner. Omit legacy publisher/capacity inputs and companion resources.

Omit `--sku` for the documented default, Standard, or pass `--sku Standard`.
Other tiers are not exposed; verify service support before planning a transition.

Add only requested optional inputs to the create command:

| Input | Requirements |
| --- | --- |
| `--tags @tags.json` | Complete intended tag object, no secrets |
| `--system-assigned true` | Confirm identity enablement; backend grants remain separate |
| `--subnet <existing-subnet-id>` | Resolve [outbound subnet prerequisites and confirmation](networking.md#read-and-confirm) before creation |

Attach existing user-assigned identities after creation; the native adapter
rejects create-time `--user-assigned` despite help visibility.
After the scoped inventory/collision check, create and wait:

```bash
LOCATION="<supported-region>"
az aigateway create --subscription "$SUBSCRIPTION" \
  --resource-group "$RG" --name "$GATEWAY" --location "$LOCATION" --no-wait
az aigateway wait --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" \
  --created --timeout 1800 --interval 20
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
```

Verify the returned ID/type, location, SKU, tags, identity, and subnet.
The typed wait accepts `properties.provisioningState` of `Active` or
`Succeeded`. Reconcile timeout or a lost response through the
[shared execution procedure](../SKILL.md#operate).

## Update tags or SKU

`--tags` replaces the entire set. Read fresh state, merge requested changes
with existing tags into approved `tags.json`, and pass its actual path below.
A one-tag object drops other tags.

```bash
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
az aigateway update --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" \
  --tags @tags.json
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
```

For a supported SKU-only change, substitute `--sku Standard` for
`--tags @tags.json`; omit unchanged fields. Compare tags/SKU and preserved
identity/network settings with the pre-read. With `--no-wait`, use the bounded
wait above with `--updated` before read-back. Root updates lack atomic
concurrent-edit protection; name/location changes are not exposed.

## Delete

Plan client outage, gateway-owned configuration loss, and system-identity loss.
Inspect relevant models/providers, aliases, ToolServers, policies, keys,
identities, exporters, and private connections; record external dependencies
and role grants that remain. Refresh the exact gateway, obtain deletion
confirmation, then:

```bash
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
az aigateway delete --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" --yes
az aigateway wait --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" \
  --deleted --timeout 1800 --interval 20
```

The wait verifies active-root absence, not purge; denied reads prove neither.
The CLI documents a recoverable soft-delete record but exposes no native
purge/recover operation; do not promise immediate name reuse. Leave external
RGs, deployments, Connector Namespace/connections, private endpoints/DNS,
user-assigned identities, telemetry stores, and role assignments untouched.

Retain provisioning commands using the [shared replay and reporting requirements](../SKILL.md#operate).
