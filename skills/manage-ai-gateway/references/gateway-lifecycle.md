# Gateway lifecycle

Apply [target resolution and safeguards](../SKILL.md) first. These examples
use its scope variables and an existing resource group.

## Discover and inspect

```bash
az aigateway list --subscription "$SUBSCRIPTION" --resource-group "$RG" -o json
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
```

List output can include legacy AI Gateway services; retain only exact
`Microsoft.ApiManagement/aigateways` targets, while detecting same-name
family collisions. A child listing is not proof of permission to read/write
its parent. Inspect `id`, `type`, `location`, `tags`, `sku`, `identity`, and
`properties.provisioningState`. Discover the runtime URL from returned
metadata, not a fabricated hostname.

## Create

Establish the exact subscription, existing RG, available region, unique name,
and intended optional settings. Check the subscription's provider readiness
and supported `aigateways` locations through authorized read-only Azure CLI
discovery if needed. Missing registration is an owner prerequisite; do not
register it. Do not apply a historical BasicV2/publisher/dual-resource design.

Refuse an existing gateway or a same-name legacy-family collision instead
of treating creation as an upsert. Execute only the requested settings:

```bash
az aigateway create --subscription "$SUBSCRIPTION" \
  --resource-group "$RG" --name "$GATEWAY" --location "$LOCATION"
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
```

`LOCATION` is the selected region. Omitting `--sku` lets the service select
its default (documented as Standard); explicit choices are `Standard`,
`Premium`, or `Consumption`. Confirm cost/tier intent; do not infer a tier
from an old APIM source.

Optional native inputs, only when requested:

| Input | Requirements |
| --- | --- |
| `--tags @tags.json` | Complete intended tag object, no secrets |
| `--system-assigned true` | Identity/access change explicitly authorized |
| `--user-assigned <existing-identity-id>` | Existing identity; no provisioning or role grant |
| `--subnet <existing-subnet-id>` | Networking confirmation and existing delegated subnet prerequisites in [networking](networking.md) |
| `--sku <selected-tier>` | Explicit choice; not source sizing conversion |
| `--no-wait` | Only if tracking is needed; acceptance is not completion |

When asynchronous, use the exposed native wait and a bounded read:

```bash
az aigateway wait --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" \
  --created --timeout 1800 --interval 20
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
```

Check final healthy state and selected fields. On timeout or a lost create
response, inspect this exact root before deciding whether creation failed.
Do not retry against a different family/name, automatically delete the
partially provisioned gateway, or provision extra resources.

## Update tags or SKU

Read fresh state. `--tags` replaces the entire tag set: build `tags.json`
by merging requested additions/removals with existing tags. Do not send a
one-tag object unless replacement of all tags is intended.

```bash
az aigateway update --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" \
  --tags @tags.json
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
```

For a tier change use the same command with `--sku "$SKU"` instead of
`--tags`. Do not repeat unrelated fields. If `--no-wait` was selected,
use `wait --updated` with bounds before read-back. Root updates do not
guarantee atomic protection from concurrent edits.

## Delete

Inventory relevant models, providers, aliases, ToolServers, policies, keys,
identities, exporters, and private connections as authorized. Explain client
outage and gateway-owned configuration loss, and list external dependencies
that will remain. Obtain confirmation for this exact gateway, then:

```bash
az aigateway delete --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION"
az aigateway wait --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" \
  --deleted --timeout 1800 --interval 20
```

Native confirmation must be handled explicitly; add `--yes` only after user
confirmation and a help check. Verify authoritative absence with the wait
and a scoped read. A denied read does not prove deletion. API Management
retains a soft-delete record; do not promise purge or immediate name reuse.
Never delete the RG, source deployments, Connector Namespace/connections,
backing private endpoint, identity resources, or telemetry stores as cleanup.

## Reproducible output

For provisioning, retain a secret-free Bash script in an approved output
location, with `set -euo pipefail`, required explicit input variables, the
actual reviewed create/configuration sequence, and matching verification.
Record prerequisite resources and authorization decisions separately. Reference
runtime secret inputs by name only, and never silently replay an overwrite,
deletion, key rotation, or access change. Do not claim the script is an
atomic transaction or that rerunning every create is safe.
