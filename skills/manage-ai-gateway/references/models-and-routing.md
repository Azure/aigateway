# Model aliases, registrations, and routing

**Publish an alias before sending model traffic.** On
`Microsoft.ApiManagement/aigateways`, clients send the alias's callable name
(`properties.aliasName`) as the request's `model`. Registering a provider
and model builds the backend configuration but does not publish that route.
Even a single backend needs an alias; use a one-target alias when no traffic
split is needed. This requirement concerns model traffic, not MCP ToolServers.

Work backward from the name clients will call: choose the alias, identify its
registered backend models, and configure their providers and access. Create
missing resources in the opposite order: provider, model, then alias.
Some onboarding/sync paths can create default aliases; inspect
`model-alias list/show` rather than assuming registration created one.
See the [multi-provider alias lab](https://github.com/Azure/aigateway/tree/main/labs/03-multi-provider-aliases)
for a client-facing example. Use this reference with the
[administrator workflow](../SKILL.md) and
[native capability inventory](activities-and-cli-coverage.md).

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

The provider/model hierarchy groups backend configuration. The alias forms
the caller-facing contract. These are different boundaries: changing shared
provider settings can affect several registrations, while retargeting one
alias changes its selected backend pool without moving or deleting models.

### Identifiers

| Identifier | Meaning |
| --- | --- |
| Provider ARM name / ID | Selects the provider registration and scopes its child models |
| Model ARM name / ID | Selects one registration under one provider; the full ID disambiguates same-name registrations under different providers |
| `deployment.modelName` | Backend model identifier recorded in the registration, distinct from its ARM name |
| `deployment.resourceId` | Existing Azure deployment identity where applicable, not a request to provision it |
| Alias ARM name | Management identity selected by `--name`; separate from its callable name |
| `properties.aliasName` | Callable value configured by `--routing-name` for clients using the alias |

A display name is descriptive metadata, not a resource move or route rename.
Registration success alone does not establish a callable alias. Resolve the
client contract from the selected alias and observed runtime metadata,
rather than deriving it from a backend or registration display name.

## Provider configuration

| Kind | Configuration block | Backend authentication exposed by the reviewed CLI |
| --- | --- | --- |
| `Foundry` | `foundry.endpoint`, account `resourceIds`, and `authentication` | `ApiKey` or `ManagedIdentity` |
| `Custom` | `custom.endpoint` and `authentication` | `ApiKey` with a configured header name/value |

Foundry account IDs belong to the provider configuration; selected deployment
IDs belong to model registrations. A Custom registration can identify a
backend model without inventing an Azure deployment ID.

Authentication selects how the gateway calls the provider. It does not
grant backend access:

- Managed identity uses a token audience in `managedIdentity.resource`.
  An optional `clientId` selects an existing attached UAMI; otherwise the
  gateway system identity is used.
- API-key configuration carries `apiKey.headerName` and the complete header
  `value` expected by that backend. It is not necessarily the gateway's own
  caller key or a bare token without its required header prefix.

Gateway identity attachment is a separately confirmed
[identity operation](keys-and-identities.md). External permissions must
already be prepared. Foundry account keys are not retrieved as ordinary
discovery.

Provider updates can change display/description and partially merge
`--foundry` or `--custom` settings with the existing nested configuration.
Changing authentication kind requires a complete new authentication object
and access-change confirmation. Preserve unrequested settings and credentials;
redacted read output is not a usable replacement secret.

The reviewed Custom authentication enum is `ApiKey` only. Arbitrary header
maps and Custom MI variants are not established native authoring support.

## Model registration configuration

| Setting | Meaning and constraints |
| --- | --- |
| `deployment.modelName` | Actual selected backend model identifier |
| `deployment.modelVersion` | Observed version when available; optional rather than guessed |
| `deployment.resourceId` | Existing Foundry deployment ID where applicable |
| `apiFormat` | Exposed format: `OpenAIChatCompletions`, `ResponsesApi`, or `AnthropicMessages` in the reviewed CLI |
| `supportedEndpoints` | Explicit operation paths supported by this registration |
| `policies` | Compatible inline model-hosted controls, separate from provider authentication and alias routing |
| Display name / description | Management metadata, not the callable alias identity |

Choose protocol and operation paths from the selected backend's actual
contract. Similar model names do not prove compatible operations, and a
format label alone does not establish support for an unexposed protocol or
decision-model variant.

Creation uses **`--deployment-config`**. General update uses
**`--deployment`**, whose value is a JSON object, not the deployment-name
argument of the convenience onboarding command. Metadata PATCH changes
supplied registration properties without changing the underlying deployment.
It is not the policy-specific ETag-safe update path.

## Alias routing semantics

An alias binds one stable callable name to a complete pool of registered
backend models.

| Setting | Meaning |
| --- | --- |
| `--name` | Alias ARM identity; immutable and distinct from the callable value |
| `--routing-name` | Callable `properties.aliasName` |
| `backendModels[].resourceId` | Full selected model registration ID |
| `priority` | Integer 0-100; lower values form the preferred tiers |
| `weight` | Integer 1-100; relative share among models in the same priority tier |
| `policies` | Alias-local controls retained independently of the target pool |

A pool contains one to 30 unique model IDs under this gateway's default
workspace. Targets may belong to different providers but must support the
intended client protocol and operations. Specify priority and weight
explicitly even for a single target.

Weights are relative, not percentages that must sum to 100. Priorities
express preferred and less-preferred tiers; they are not another weight
scale. Use **equal priorities and different weights** for active-active load
sharing or a canary rollout: 75 and 25 express a 3:1 request share among
eligible models in that tier. They do not allocate tokens, cost, or capacity.
Use **different priorities** for preferred capacity and fallback: priority 0
is preferred over priority 1, regardless of their relative weights. A weight
on a fallback model does not give it a share of normal preferred-tier traffic.

Configuration establishes intended routing, not proof of an observed
traffic distribution or a particular runtime retry sequence. Verify failover
under separately authorized failure conditions before relying on it; priority
alone does not configure retries, timeouts, or circuit breakers.

Supplying backends on update defines the **entire target pool**. Retargeting
can preserve the alias name while changing the backend capabilities and
model-local controls encountered by its traffic. Inspect applicable
[workspace, alias, and model policies](policies.md) as part of impact analysis.
An alias-local allowance remains attached to the alias, not duplicated
per backend target.

The reviewed native interface exposes priority/weight routing, not backend
conditions, auto-selection objectives, override grants, selection order,
or CEL session preference. Existing noneditable routing settings must be
preserved by a partial change; if the intended operation cannot retain their
semantics, it remains a capability gap rather than a guessed JSON extension.

## Native operation paths

All commands below are prefixed with `az aigateway` and use the exact
resolved gateway/subscription selectors.

| Resource | Inspection | Configuration and lifecycle |
| --- | --- | --- |
| Provider | `model-provider list/show` | `create`, partial `update`, `delete`; Foundry `sync` has separate reconciliation semantics |
| Model | `model list/show` | Low-level `create`, supplied-field `update`, `delete`; explicit provider/model selectors |
| Alias | `model-alias list/show` | `create`, partial `update`, `delete`; complete backend membership when supplied |

Use exact child `--ids` where exposed. Complete pagination before absence
or dependency claims; match returned IDs to the selected typed gateway and
default workspace. Short names alone do not establish resource identity.

Create is not a blanket idempotent upsert. Inspect existing registrations and
use an explicit update for intended changes. Provider creation is not
guaranteed atomic/create-only. Alias create refuses an existing ARM alias,
but its GET-before-PUT check cannot prevent concurrent same-name creation.
The installed alias command does not expose the reference's `--overwrite`.

Alias update uses its current ETag; conflicts require fresh state and a new
decision. General provider/model writes do not carry a blanket atomic
concurrency guarantee. Compare intended and preserved fields through
matching reads rather than inferring safety from the command name.

## Deriving a configuration change

1. Establish the client-facing contract: model capabilities/operations,
   callable identity, and routing or governance requirements.
2. Inspect relevant providers, models, aliases, and policies. Relate the
   existing registrations to authorized backend evidence: endpoints,
   deployment IDs, versions, protocols, and prepared authentication.
3. Compose the required object relationships. Reuse suitable registrations;
   create missing provider/model foundations before aliases that reference
   them. Additional identity or external setup is not implicit authorization.
4. Compare shared and resource-local effects. Provider connection changes can
   fan out to several models; alias retargeting can change backend-local
   behavior while retaining the caller name. Select the smallest change
   that preserves unaffected workloads and the intended policy boundaries.
5. Apply the native paths with the common authorization, credential and
   preservation safeguards. Separate persisted configuration from runtime
   verification.

Inspection examples use the [resolved variables](../SKILL.md):

```bash
az aigateway model-provider list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
az aigateway model-provider show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" -o json
az aigateway model list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -o json
az aigateway model-alias list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
```

## Configuration examples

Examples illustrate selected values and independent operations, not a script
to run wholesale. Low-level registrations keep external permission changes
outside the gateway's configuration lifecycle.

### Foundry provider

An authorized read-only deployment inventory or operator manifest supplies
the existing account/deployment metadata. `foundry.json`:

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

Use the observed endpoint/audience and prepared identity access.

```bash
az aigateway model-provider create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" \
  --kind Foundry --foundry @foundry.json
```

Foundry can instead use `authentication.kind: "ApiKey"` with
`apiKey: {"headerName":"<backend-header>","value":"<runtime-secret>"}`.
The convenience `--foundry-resource-id` create paths also enable identity
and grant Foundry User externally; they are outside this skill's allowed
execution path.

### Custom provider

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

Use the provider create command with `--kind Custom --custom @custom.json`.
Secret-bearing input belongs in an approved protected file outside source
control, with actual runtime values rather than literal placeholders.
JSON does not interpolate environment variables.

### Model registration

`deployment.json` for a selected existing Foundry deployment:

```json
{
  "modelName": "<observed-runtime-model-name>",
  "modelVersion": "<observed-version>",
  "resourceId": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/deployments/<deployment>"
}
```

Omit genuinely absent optional fields. Custom registrations can use the
actual backend `modelName` without an invented Azure resource ID.

```bash
az aigateway model create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --deployment-config @deployment.json --api-format "$API_FORMAT" \
  --supported-endpoints "$SUPPORTED_ENDPOINT"
az aigateway model show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" -o json
```

Supply exact supported operation paths; multiple paths are separate arguments
after `--supported-endpoints`. Model update accepts `--deployment @deployment.json`,
`--api-format`, `--supported-endpoints`, and supported descriptive fields.
Use [policy authoring paths](policies.md) for governance-specific changes.

### Alias pool

```bash
az aigateway model-alias create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" --routing-name "$ROUTING_NAME" \
  --backend-model resource-id="$MODEL_A_ID" priority=0 weight=75 \
  --backend-model resource-id="$MODEL_B_ID" priority=0 weight=25
az aigateway model-alias show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" -o json
```

Both models use priority 0 deliberately: they are active at the same tier,
so their weights request a 75/25 split. Different priorities would instead
prefer one model, not perform this canary split.

For **priority-based failover**, replace the pool with model A preferred
and model B as fallback:

```bash
az aigateway model-alias update --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" \
  --backend-model resource-id="$MODEL_A_ID" priority=0 weight=100 \
  --backend-model resource-id="$MODEL_B_ID" priority=1 weight=100
```

Each tier has one model, so the weights do not split traffic between A and B.
Model B is a less-preferred option when the preferred tier cannot serve;
confirm the actual runtime failure and retry behavior for the workload.
The [routing lab](https://github.com/Azure/aigateway/tree/main/labs/22-model-routing)
explores the two configurations.

These are alternatives, not steps to run in sequence. For updates, confirm
complete-pool replacement or retargeting impact before sending
`model-alias update`, which takes the same routing/description/backend inputs.
Unrequested alias policies and routing settings remain unchanged.

## Provider reconciliation

Native sync reconciles Foundry deployments with registrations under one
provider. It is distinct from changing provider connection settings or
provisioning deployments.

```bash
az aigateway model-provider sync --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" --dry-run
```

Inspect additions, stale removals, and any requested default aliases.
Discovery failures are not an empty account. Compare stale models with
all alias references before planning deletion. Add-only intent can use
selected low-level creates rather than authorizing stale removals.

After confirming the exact destructive plan, apply without `--dry-run`.
`--create-default-aliases true` belongs in the preview and apply only when
requested; `--yes` requires actual confirmation. The CLI rechecks discovery,
but writes are sequential. Changed inputs require a new preview/decision;
partial failure requires current-state reconciliation rather than blind
whole-sequence replay.

Sync preserves existing matching models and their policies; it does not
change external deployments, provider settings, identity, or roles.
Custom discovery/sync is not established by this native contract. Explicit
Custom registrations use a selected finite model catalogue and known
operations instead.

## Removal and verification

| Removed resource | Dependencies to inspect | Ownership consequence |
| --- | --- | --- |
| Alias | Clients using its callable name and its configured policies | Removes the callable registration, not its target models |
| Model | Every alias referencing its full ID and the model's controls | Removes the gateway registration, not the deployment |
| Provider | All contained models and their alias references | Provider/model configuration is affected; external accounts/deployments remain |

Resolve dependencies only through requested, approved changes. Deletion is
not permission for automatic client retargeting or a destructive cascade.
Use the selected resource's native `delete` with exact exposed selectors/ID,
then require authoritative absence through matching reads.

Verify provider kind, endpoint, account IDs and nonsecret authentication
metadata; model deployment/protocol/operation fields; and alias callable name,
complete target IDs/priorities/weights and retained policies. Redacted output
cannot prove a secret value, and resource existence alone is insufficient.

Runtime propagation, backend access, protocol behavior and observed routing
require separate evidence. A native management read is not an inference test.
Report partial/unknown outcomes and reconcile before retrying instead of
claiming a working callable model from registration success alone.
