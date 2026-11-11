# Model aliases, registrations, and routing

**An alias publishes the callable model name.** On
`Microsoft.ApiManagement/aigateways`, clients send `properties.aliasName`
as the request's `model`. A provider and model registration supply backend
configuration, not a published route; even one backend needs an alias.
This requirement concerns model traffic, not MCP ToolServers.

Use the [administrator workflow](../SKILL.md) for scope, authorization, and
credential handling, and the [capability inventory](activities-and-cli-coverage.md)
for reviewed limits. Examples are independent operations using its resolved
variables, not a script to run wholesale.

## Choose the smallest workflow

| Intended outcome | Smallest change and effect |
| --- | --- |
| Publish one existing backend deployment | Reuse a suitable provider; register only the missing model, then create a one-target alias |
| Publish an already registered model | Create only the missing alias; inspect existing aliases first |
| Move one production route to a new deployment | Register the new deployment separately, then update that alias's pool; do not repoint a shared registration |
| Change shared endpoint/authentication | Update the provider after checking all its models and their alias consumers |
| Change exposed operations | Update the selected model's protocol/endpoint metadata only after checking every consuming alias's required operations; metadata does not add backend capabilities |
| Reconcile an entire Foundry provider | Preview `model-provider sync`; it can remove stale registrations, unlike selected low-level creates |

## Resource model

| Object | Configuration responsibility | Relationships and ownership |
| --- | --- | --- |
| Model alias | Callable name, backend target pool, priorities/weights, and alias-local policies | References registered models in the same gateway/default workspace; not their ARM parent |
| Model provider | Backend endpoint, provider kind, and outbound authentication | Parent of model registrations; its connection settings are shared configuration |
| Registered model | Backend deployment metadata, exposed API format/endpoints, and model-local policies | Belongs to one provider; can be referenced by aliases |
| Backend account/deployment | Actual model hosting, deployment lifecycle, and backend permissions | External prerequisite, not created or deleted by gateway registration |

Providers and models live at
`workspaces/default/modelProviders/<provider>` and
`workspaces/default/modelProviders/<provider>/models/<model>`.
Aliases live at `workspaces/default/aliases/<alias>`.

### Identifiers

| Identifier | Meaning |
| --- | --- |
| Provider ARM name / ID | Selects the provider registration and scopes its child models |
| Model ARM name / ID | Selects one registration under one provider; the full ID disambiguates same-name registrations under different providers |
| `deployment.modelName` | Backend request identifier: the Foundry deployment name or Custom backend's model name, not necessarily its catalogue model name or gateway ARM name |
| `deployment.resourceId` | Existing Azure deployment identity where applicable, not a request to provision it |
| Alias ARM name | Management identity selected by `--name`; separate from its callable name |
| `properties.aliasName` | Callable value configured by `--routing-name` for clients using the alias |

A display name is metadata, not a resource move or route rename. The callable
alias name can contain `/`; it is not the alias's ARM path or runtime URL.

## Execute the smallest native change

Inspect provider → model → consuming aliases; reuse matching configuration.
Create examples assume missing names, not permission to overwrite. Discover
providers with `model-provider list` using the same gateway selectors.

```bash
az aigateway model-provider show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" -o json
az aigateway model list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -o json
az aigateway model-alias list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
```

Follow `--max-items` / `--next-token` pagination before claiming absence or
complete dependencies. Retain returned IDs for commands exposing `--ids`;
do not manufacture IDs from foreign responses.

### Provider configuration

#### Foundry provider

Use authorized backend inventory or an operator manifest for the endpoint,
account/deployment IDs, metadata, and supported operations.

1. Select the gateway system identity or an existing attached UAMI.
   Identity attachment is a separately confirmed
   [identity operation](keys-and-identities.md).
2. Verify principal access. Record principal, least-privileged role, and
   narrowest scope for a missing grant; check assignment authority, confirm
   that exact [grant](../SKILL.md#operating-boundary), then create and verify
   it, or give the owner the plan. Identity selection grants nothing.
3. Reuse a provider only if its endpoint, account IDs, and authentication
   suit this deployment; otherwise create a separate registration.

`foundry.json` selects managed-identity authentication:

```json
{
  "endpoint": "https://contoso.openai.azure.com/",
  "resourceIds": ["/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>"],
  "authentication": {
    "kind": "ManagedIdentity",
    "managedIdentity": {"resource": "https://cognitiveservices.azure.com/"}
  }
}
```

`resourceIds` contains account IDs, not deployment IDs.
`managedIdentity.resource` is the backend's token audience; use its observed
value. Add `managedIdentity.clientId` only to select an attached UAMI;
omitting it selects the gateway system identity.

```bash
az aigateway model-provider create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" \
  --kind Foundry --foundry @foundry.json
```

Foundry also accepts `authentication.kind: "ApiKey"` with
`apiKey: {"headerName":"<backend-header>","value":"<runtime-secret>"}`.
Do not retrieve account keys as ordinary discovery.

The convenience `model-provider create --foundry-resource-id` imports every
deployment; `model create --foundry-resource-id ... --deployment ...` onboards
one. Both bundle system-identity enablement and **Foundry User at account
scope**. Prefer low-level registration plus the separately approved grant.

#### Custom provider

`custom.json`:

```json
{
  "endpoint": "https://models.example.com/",
  "authentication": {
    "kind": "ApiKey",
    "apiKey": {"headerName": "Authorization", "value": "<complete-runtime-header-value>"}
  }
}
```

Use the same provider create command with `--kind Custom --custom @custom.json`.
The value is the complete backend header value, including any required
prefix, not the gateway caller key. Use [protected credential
inputs](../SKILL.md#authorization-and-preservation); JSON files do not expand
variables. Reviewed Custom authentication is `ApiKey` only; portal `Header`
configuration, arbitrary header maps, and Custom managed identity are not
established native support.

### Model registration

`deployment.json` for a selected existing Foundry deployment:

```json
{
  "modelName": "<existing-foundry-deployment-name>",
  "modelVersion": "<observed-version>",
  "resourceId": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/deployments/<deployment>"
}
```

Include `modelVersion` only when observed. Custom registrations need the
backend model name, not an invented Azure deployment ID.

```bash
az aigateway model create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --deployment-config @deployment.json --api-format "$API_FORMAT" \
  --supported-endpoints "$SUPPORTED_ENDPOINT"
az aigateway model show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" -o json
```

Set metadata from the backend contract. `API_FORMAT` is
`OpenAIChatCompletions`, `ResponsesApi`, or `AnthropicMessages` in the
reviewed native interface. `SUPPORTED_ENDPOINT` is one exact supported path;
multiple paths are separate arguments after `--supported-endpoints`.
Preserve observed provider prefixes such as `/openai/v1/`; do not normalize
them to a bare `/v1` default. These fields neither prove protocol conversion
nor establish an unreviewed decision-model variant.

### Update without rebuilding settings

Refresh registrations and retain returned `PROVIDER_ID` / `MODEL_ID`.
Metadata-only edits need no connection or deployment object:

```bash
az aigateway model-provider update --subscription "$SUBSCRIPTION" \
  --ids "$PROVIDER_ID" --display-name "Production models"
az aigateway model update --subscription "$SUBSCRIPTION" \
  --ids "$MODEL_ID" --display-name "Production chat"
```

For a selected endpoint-only change:

```bash
az aigateway model-provider update --subscription "$SUBSCRIPTION" \
  --ids "$PROVIDER_ID" --foundry '{"endpoint":"https://<approved-account>.openai.azure.com/"}'
```

Provider update merges supplied `--foundry` / `--custom` fields into current
configuration, preserving omitted authentication/settings. Do not round-trip
redacted provider JSON. An account change also requires matching `resourceIds`,
deployment IDs, and access; an endpoint-only edit is not a migration.
Changing authentication kind requires a complete new authentication object
and access-change approval.

Model update patches supplied properties. **Create uses `--deployment-config`;
update uses `--deployment @deployment.json`**, not a deployment-name string.
Retain unrequested fields in the complete deployment object; do not assume
nested merging. `--supported-endpoints` and `--policies` replace collections.
Prefer [policy-specific paths](policies.md) for governance changes.
General provider/model updates lack the alias update's conditional-write
path; fresh reads do not eliminate concurrent-write risk.

### Alias pool

#### Publish a callable name

Get the selected model registration's returned ID, not its backend deployment
ID. The scope check below deliberately stops on empty or misrouted output:

```bash
MODEL_ID="$(az aigateway model show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --query id -o tsv)" || exit 1
if [ "$MODEL_ID" != "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$MODEL" ]; then
  printf '%s\n' 'Unexpected model registration ID; stop and resolve scope.' >&2
  exit 1
fi
az aigateway model-alias create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" --routing-name "$ROUTING_NAME" \
  --backend-model resource-id="$MODEL_ID" priority=0 weight=100
az aigateway model-alias show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" \
  -o json
```

`--name` selects the immutable ARM resource; `--routing-name` sets
`properties.aliasName`. Check both ARM-name and callable-name collisions,
including onboarding/sync aliases. Keep the callable name stable when
retargeting. Alias create's GET-before-PUT check is not atomic; exclude
concurrent creation. There is no `create --overwrite`; use explicit update.

#### Promote a model and retain rollback

Read `model-alias show`; retain `ALIAS_ID`, callable name, full pool, policies,
and other routing settings. Read current/proposed models by registration ID;
use those IDs for `NEW_MODEL_ID` / `OLD_MODEL_ID`.

A pool has **one to 30 unique model IDs** in this gateway's default workspace,
possibly across providers. Require common support for the client's operations,
not merely matching `apiFormat` labels; inspect alias `supportedEndpoints` /
`gatewayEndpoints` when returned, without writing these derived fields.
Check [workspace, alias, and model policies](policies.md): retargeting changes
backend-local controls; an alias allowance is not duplicated per target.

| Intent | Targets | Effect |
| --- | --- | --- |
| Canary / active-active | Old: priority 0, weight 75; new: priority 0, weight 25 | Relative 3:1 request share among eligible models in the same tier |
| Promote new, retain old fallback | New: priority 0, weight 100; old: priority 1, weight 100 | New tier preferred; old does not receive a normal weighted share |

These examples assume priority/weight routing without other selection stages.
Priority is integer `0-100` (lower preferred); weight is integer `1-100`
and relative within a tier, not a percentage total or token/cost allocation.
Weight zero is not a supported way to park a target.

After confirming **whole-pool replacement**, this two-target example promotes
the new model while retaining the old as fallback:

```bash
az aigateway model-alias update --subscription "$SUBSCRIPTION" \
  --ids "$ALIAS_ID" \
  --backend-model resource-id="$NEW_MODEL_ID" priority=0 weight=100 \
  --backend-model resource-id="$OLD_MODEL_ID" priority=1 weight=100
az aigateway model-alias show --subscription "$SUBSCRIPTION" \
  --ids "$ALIAS_ID" -o json
```

Supplying backends replaces the **entire pool**. Carry forward every intended
target and setting; if the native target schema cannot preserve an existing
field, stop before replacement. Omit `--routing-name`, `--description`, and
`--policies` to retain them. Update sends supplied properties with the current
ETag/If-Match; a conflict requires fresh state and a new decision.

For manual rollback, reverse the priorities after a fresh read and approved
pool change. If the old model must receive **no traffic**, keep its registration
and saved former pool for rollback but exclude it from the active pool:
a lower-priority target is still eligible fallback, not disabled.

The portal also authors backend conditions, automatic model-selection
objectives/override grants, selection order, session preference, and failure
rules/retry caps. These can change eligibility, preference, and failover;
priority alone does not explain an existing alias's behavior. Native authoring
is reviewed for ID/priority/weight, not these controls or per-target timeouts.
Preserve them on unrelated edits; report an unsupported change rather than
inventing JSON or silently reducing the alias to weighted routing.

### Provider reconciliation

Sync reconciles Foundry deployments with one provider's registrations; it
neither changes the connection nor provisions deployments.

```bash
az aigateway model-provider sync --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" --dry-run
```

Review proposed creates/deletes by exact deployment/registration ID. A stale
registration may be a rollback target. Check all alias references; retarget
or unbind deliberately before deletion. Discovery errors are not an empty
backend account.

There is **no add-only sync switch**. Stop after a preview-only request.
Without removal approval, use selected low-level creates instead.
`--create-default-aliases true` adds missing 1:1 aliases only when requested;
include it in both preview and apply.

Apply without `--dry-run` only after confirming the exact reconciliation,
including removals; `--yes` merely answers that confirmation. Sync rechecks
discovery but is not a pinned-plan transaction. Changed inputs require a new
preview/decision. Writes are sequential, so inspect current models/aliases
after partial failure before retrying.

Sync preserves matching registrations/policies rather than refreshing metadata;
it changes no backend deployments, provider settings, identity, or roles.
Portal Custom discovery is not native sync support: use explicit registrations
from an authorized finite catalogue.

### Removal and verification

Remove in dependency order, only for the approved resources:

1. Retarget affected aliases to approved survivors, or delete aliases whose
   callable names are being retired. Preserve unrelated aliases and policies.
2. Verify no remaining alias references each retiring model's full ID, then
   delete those model registrations.
3. Re-list models under a retiring provider; delete it only once empty.
   Do not rely on provider deletion to perform safe cleanup.

Use `model-alias delete`, `model delete`, or `model-provider delete` with the
returned child `--ids` and explicit subscription. Alias deletion uses
If-Match and never deletes target models. Matching reads must establish
authoritative absence, not permission denial. Backend accounts/deployments
and external grants survive registration deletion; review grant retirement
separately rather than silently removing shared access.

## Verify configuration

Read back each changed object by its returned ID and compare the intended
difference and preserved siblings:

- Provider: kind, endpoint, account IDs, nonsecret auth metadata.
- Model: deployment, protocol, operations, retained policies.
- Alias: callable name, complete pool/priorities/weights, other routing settings
  and policies, and derived endpoint metadata when returned.

## Identify remaining runtime uncertainty

Redacted output cannot prove a credential. Report separately what remains
unverified: propagation, backend access, protocol behavior, traffic share, and
failover/retry sequence need authorized runtime evidence. A saved alias is
configured, not a successful inference.
