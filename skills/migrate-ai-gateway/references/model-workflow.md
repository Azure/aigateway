# Explicit model discovery, import, and synchronization

These are source-only facts followed by a destination selection, not an APIM API
import. Use the selected isolated Python environment and the skill's
`scripts/migration.py` helper. Examples describe shapes, not evidence that an
example model or account exists. Obtain actual identifiers from authorized
discovery or explicit operator input.

## Resolve a model-discovery route during assessment

Before treating model names as missing operator facts, determine whether an
evidenced catalog route and an approved runtime credential are usable. An
unauthenticated failure does not establish model absence or unsupported
discovery. This is source-only work: no destination, inference request, or
migration execution approval is required, but data-plane reads and credential
use retain their separate approvals.

1. **Establish the exact URL from source evidence.** For an APIM-fronted catalog,
   use the observed service `properties.gatewayUrl` or explicitly selected
   hostname binding, API `properties.path`, and catalog GET operation's
   `urlTemplate`. Verify the effective forwarding policy for that operation.
   Do not guess a hostname suffix from the service name, omit an API/base path,
   or assume every model-facing API exposes `/models`. For direct discovery,
   establish the effective provider base from the selected backend and inherited
   routing/rewrite policies or explicit operator evidence, not a provider brand
   or an unrelated backend. The Custom helper appends `/models` to this base:
   preserve version/path prefixes and do not pass an already-complete catalog
   URL. Opaque route expressions remain unresolved; do not probe guessed hosts
   or adjacent paths to compensate.
2. **Resolve credentials only inside the approved runtime.** Source inventory
   deliberately redacts credentials; that does not mean an existing protected
   runtime variable, named value, or subscription key is unavailable. Prefer an
   existing protected binding; when the credential is only available through the
   control plane, offer the scoped APIM helper path below instead of rejecting
   secret retrieval categorically. Obtain separate approval of the exact source
   resource/field and its use at the selected endpoint/header. ARM login or
   metadata-read access alone is not that approval. Never dump the environment,
   print headers, persist secret values, or request a pasted key. If permission
   or the selected credential is unavailable, report that exact prerequisite
   rather than claiming the provider lacks models.
3. **Choose a route with the correct authentication boundary.** Prefer the
   evidenced APIM catalog route when a client credential is approved and usable,
   including through a scoped subscription-key read. APIM can apply its stored
   backend credential without retrieving it into the assessment.
   Use the observed APIM admission header (including any
   configured subscription-key header name), not the backend Authorization
   header. Otherwise use the evidenced direct route with its separately approved
   upstream credential and complete required header scheme. Never send an APIM
   client key or ARM bearer token upstream. Confirmed anonymous catalogs need no
   invented credential. An alternate origin or credential requires its own
   approval; no implicit fallback or redirect following is authorized.
4. **Perform the scoped GET and classify its actual result.** Use the Custom
   helper below for its supported `/models` route. Preserve redirect, pagination,
   response-size, timeout, and finite-entry limits. If an exposed APIM catalog
   has a different route/envelope, keep an approved read as redacted supplemental
   assessment evidence rather than pretending the helper supports that shape.
   Distinguish URL/connectivity failures, authentication/authorization failures,
   malformed responses, unsupported catalog operations, and reads not attempted.
   Do not equate a 401/403 with no models or a 404 with platform incompatibility.
   Correct an evidenced URL/header/binding mistake only within the approved
   scope; do not retry the unchanged failure. If discovery is unavailable, retain
   sanitized diagnostics and explain the exact blocker before using operator
   input. Continue assessing unaffected components.

Preserve exact, case-sensitive IDs from the returned catalog. A list of names
does not prove protocol/operation support or runtime parity. A catalog read
through APIM describes that exposed surface, potentially filtered; retain its
APIM endpoint and provenance, and do not relabel it as a direct authenticated
upstream read or proof of exhaustive upstream membership. Destination provider
selection must still respect the actual account/credential boundary.

## Discover or import source facts

**Foundry:** select the exact account ARM ID and one of its advertised endpoints.
The helper verifies the existing account kind, reads its deployment metadata,
and preserves deployment IDs/names separately from underlying model family and
version. It does not create providers, enable identities, or grant roles.

```bash
"$PYTHON" "$HELPER" collect-models --provider-id account-a \
  --kind Foundry --account-id <selected-account-arm-id> \
  --endpoint <advertised-account-endpoint> --approved-read \
  --output-file foundry.catalog.json
```

`--approved-read` records previously obtained approval of these scoped reads. It
is not permission to contact unselected accounts or a substitute for user
approval. Foundry discovery uses the selected account's subscription and Azure
login, not an upstream API-key variable.

**Custom:** approve the exact provider base URL and use of its existing runtime
credential. The helper GETs `<base-url>/models` using that provider credential,
not an ARM bearer token. Supply the complete header value, including any
required scheme prefix. Never echo it or place it in arguments.

```bash
"$PYTHON" "$HELPER" collect-models --provider-id custom-a \
  --kind Custom --endpoint <approved-https-base-url> \
  --credential-env UPSTREAM_AUTHORIZATION --credential-header Authorization \
  --approved-read --output-file custom.catalog.json
```

**Scoped APIM control-plane credentials:** when no protected runtime binding is
available, do not require the user to extract or paste a secret. Approve the
exact selected source service, credential resource and field, catalog endpoint,
header, and scheme. Then use `--credential-resource-id` instead of
`--credential-env`, with both `--approved-read` and `--approved-credential-read`.
The latter records actual separate approval; it is not permission to grant RBAC,
enumerate secrets, or contact other providers.

The supported APIM `2024-05-01` read actions are
[named value `listValue`](https://learn.microsoft.com/en-us/rest/api/apimanagement/named-value/list-value?view=rest-apimanagement-2024-05-01)
and [subscription `listSecrets`](https://learn.microsoft.com/en-us/rest/api/apimanagement/subscription/list-secrets?view=rest-apimanagement-2024-05-01).
Both use POST but only read existing secrets; no source configuration or keys
are changed. A selected subscription response includes both keys; only the
explicitly selected field is sent to APIM, and neither key is persisted.

```bash
"$PYTHON" "$HELPER" collect-models --provider-id custom-a --kind Custom \
  --endpoint <approved-upstream-base-url> --source-id <source-service-id> \
  --credential-resource-id <source-service-id>/namedValues/<named-value-id> \
  --credential-field value --credential-header Authorization \
  --credential-scheme Bearer --approved-read --approved-credential-read \
  --output-file custom.catalog.json

"$PYTHON" "$HELPER" collect-models --provider-id apim-a --kind Custom \
  --endpoint <observed-apim-gateway-url>/<api-suffix> --source-id <source-service-id> \
  --credential-resource-id <source-service-id>/subscriptions/<subscription-id> \
  --credential-field primaryKey --credential-header Ocp-Apim-Subscription-Key \
  --approved-read --approved-credential-read --output-file apim.catalog.json
```

Use complete ARM IDs and observed header names, not these placeholders. Omit
`--credential-scheme` when a named value already contains the complete header
value; otherwise it prefixes `Bearer` or `Basic` without evaluating expressions.
The helper accepts only one service-level named value or subscription inside the
exact source. Subscription keys additionally require the selected endpoint to
match that source's advertised gateway origin or Proxy hostname binding.
Upstream named-value use requires explicit approval of the evidenced provider
URL and credential boundary. An inaccessible or unresolved Key Vault-backed
value remains a specific blocker, not permission to fetch unrelated vault secrets.

Azure CLI output is captured inside the helper process; credential values never
enter its command arguments, environment, console output, catalog, or plan.
Do not enable CLI debug/verbose logging, shell tracing, or HTTP payload capture.
Values are retained only in process memory for the read, not guaranteed securely
zeroized by Python. Catalogs retain only the non-secret `credentialSource`
(source/resource IDs, selected field, and scheme), plus the credential header.
Redirects and credential-bearing model IDs/continuations remain rejected.

Execution and completion-report refreshes require renewed approval of the
displayed catalog credential sources and `--approved-credential-read` on
`execute`/`report`; a stored reference is not a stored approval. This does not
authorize copying source credentials into destination registrations or replacing
their separate runtime-secret/admission decisions.

Unauthenticated catalogs may omit both credential options. Redirects are rejected.
Pagination must remain on the selected HTTPS origin and exact collection path.
Custom HTTP responses are bounded to 2 MiB and use a 30-second connection/read
timeout. Catalogs are bounded to 1,000 pages and 10,000 entries; ARM calls retain
the helper's CLI timeout. Hitting a limit
produces an explicit incomplete/error result, never silent truncation.
Malformed, unsupported, or unavailable catalogs produce an explicit failed
artifact and a nonzero exit; they do not prove an empty model universe. Explain
the failure and use operator input instead of blindly retrying or widening
access. Do not send inference requests to discover capabilities.

**Operator input:** use `schemas/model-catalog.schema.json`. Each provider has
`provenance: "operator-manifest"`, `complete: false`, `error: null`, an actual
capture/attestation time, and explicit model entries. Model entries preserve
`id`, `deploymentId` (Foundry only), `family`, `version`, observed `apiFormat`,
and observed `endpoints`; unknown optional facts are null/empty, not invented.
An observed upstream format is not a destination protocol choice.

```bash
"$PYTHON" "$HELPER" model-catalog-digest --path operator.models.json
# Show the path/digest and obtain approval before importing:
"$PYTHON" "$HELPER" import-models --manifest-file operator.models.json \
  --approved-digest <approved-canonical-digest> --output-file manual.catalog.json
"$PYTHON" "$HELPER" merge-model-catalogs \
  --catalog-file foundry.catalog.json --catalog-file manual.catalog.json \
  --output-file models.catalog.json
```

Separate accounts or credential boundaries require separate provider catalog
identities, even when endpoint hosts or model names match. Model IDs are
case-preserving. A manual list establishes the selected intent, not exhaustive
upstream completeness or successful runtime behavior.

## Select a finite destination surface

Use `schemas/selection.schema.json`:

- `catalogDigest` is obtained with
  `model-catalog-digest --path models.catalog.json --selection`. This semantic
  digest excludes capture timestamps; the manifest-approval digest above does
  not. Neither permits changing model facts without reselecting.
- `providers` references catalog `id`s. Optional `name` selects a distinct
  destination ARM provider name. `settings` contains the exact low-level native
  `kind` and `custom`/`foundry` configuration, with credential values only as
  `{"$runtimeSecret":"ENVIRONMENT_VARIABLE_NAME"}`. `sourceIds` and `evidence`
  bind the source backend/credential behavior. `reuseExisting: true` is an
  explicit decision to reuse confirmed existing authentication, not rotate it.
  Import/sync will not silently change a conflicting existing provider; review
  that provider change separately or choose an appropriate registration.
- `models` identifies each catalog `provider` and exact runtime `id`, destination
  registration `name`, ARM `alias`, callable `routingName`, target `apiFormat`,
  finite `endpoints`, source bindings, and evidence. A Foundry deployment name,
  model family, ARM model name, and callable name are not interchangeable.
  Conflicting existing alias targets are preserved unless `updateAlias: true`
  explicitly requests a reviewed replacement.
- `mcp` identifies exact sources/contracts, source bindings, evidence and an
  explicit `accessDecision`. The compiled OpenAPI path requires a scoped inline
  contract matching selected operation methods, paths, parameter shapes, backend
  URL and source MCP tool names. Do not use wildcard paths or publish redacted
  inventory directly as a specification. Existing sources need `reuseExisting`
  or an explicit `replaceEndpoints` decision; supplying endpoints replaces the
  collection, not an append. Secret-only rotations are not inferred from
  matching redacted metadata.
  Inline contracts must be payload-free: no embedded defaults/examples,
  credential values, opaque vendor extensions, external schema fetches, or
  operation-level server overrides. Local output-schema references are compared
  with selected source schema structure. Opaque constraints or unsupported
  schema shapes need reviewed evidence or an existing-MCP bridge, not a generic
  response that silently drops them.
- `keys` selects new/reused gateway-wide key metadata and an explicit
  `accessDecision`. This is not per-API/product access or automatic preservation
  of anonymous clients. Destination key values are not retrieved; source keys
  may only be consumed by approved catalog reads, not copied into the destination.
  Selected models/MCP require an explicit key/admission node; an anonymous
  source is not silently treated as an anonymous destination.
- `retained` explicitly identifies observed source records and the reason they
  stay on APIM. Unknown coverage is not a retained source record. Remaining
  unselected items stay unresolved scaffolding until assessed.
- `gateway` provides creation location/subnet when needed, or matching/empty
  creation settings when reusing an existing destination.

The installed reviewed destination capability catalog limits supported model
protocol/operation choices. A user-supplied `supported-endpoints` string is not
proof that the service implements an arbitrary APIM operation. Unknown upstream
capabilities require an explicit operator decision and later behavior proof.
Never derive runtime model IDs from API names, schema examples or generated
sample requests. No wildcard selects future models or every API operation.

## Plan, reconcile, and verify

```bash
"$PYTHON" "$HELPER" init --state-dir <fresh-version-4-state> \
  --source-file source.candidate.json --model-catalog-file models.catalog.json \
  --destination-file destination.candidate.json \
  --capabilities-file capabilities.candidate.json
"$PYTHON" "$HELPER" compile-plan --state-dir <state> --selection-file selection.json
```

Compilation is local and performs no Azure mutation. It creates a graph of
gateway/provider/model/alias/MCP/key resources, not one capability per source
behavior. Every behavior has one owner; a mapping can require several resource
nodes, and prerequisites can be shared. Review unresolved items and residuals;
a structurally valid plan is not execution approval or migration completion.

**Foundry import/sync requires native preview evidence.** Source-only catalogs
still work without a destination. For a new gateway/provider, first compile a
foundation selection with `models: []`, `mcp: []`, and `keys: []`, approve and
create/verify those resources, then recollect destination/capability evidence.
Do not treat this foundation as a completed traffic migration.

Approve reads of the selected gateway workspace (models and aliases) and the
provider's exact Foundry account. With the latest official, reviewed CLI:

```bash
"$PYTHON" "$HELPER" collect-sync-preview \
  --model-catalog-file models.catalog.json --destination-file destination.fresh.json \
  --provider-id <catalog-provider-id> --provider-name <destination-provider-name> \
  --approved-read --output-file provider.preview.json
"$PYTHON" "$HELPER" compile-plan --state-dir <state> --selection-file selection.json \
  --destination-file destination.fresh.json --capabilities-file capabilities.fresh.json \
  --sync-preview-file provider.preview.json
```

Repeat `--sync-preview-file` for each selected Foundry provider. The collector
checks the existing provider's kind, exact account and endpoint before invoking
only public `model-provider sync --dry-run -o json`; it requests no default
aliases. Evidence binds the provider/target, catalog, CLI fingerprint, destination
baseline and native actions. Capture timestamps do not alter plan intent.

Native preview owns missing/stale membership; the helper does not recompute a
Foundry deployment diff. Select exact native create/unchanged registrations by
deployment ID and destination name. A proposed create must keep its native
deployment-based name; an existing matching registration may have another name.
Unselected creates remain untouched. Native `unchanged` describes membership,
not metadata equivalence: explicit selected metadata can still require an
ordinary model update. Existing policies and unrelated models are preserved.
Native deletes appear only as unapproved, separate removal proposals, never
DELETE TODOs. Manual/partial catalogs alone cannot establish staleness.

The reviewed b22 CLI can fail even dry-run if a stale registration is referenced
by an alias. The collector writes a `blocked` artifact and exits nonzero; failed
preview evidence cannot compile a plan. Do not detach aliases/delete models to
obtain a preview or replace the failure with a local diff. Explain the blocker
and retain the existing configuration. Custom providers do not use native sync;
their `/models` or manual catalogs feed explicit registration instead.

Execution/report refreshes re-run native preview and compare approved decisions.
Only recorded model creates that read back as the approved desired state may
transition from native `create` to `unchanged`. Unrelated action changes,
unavailable previews and catalog/CLI/provider drift block work and require fresh
evidence/planning. These checks are read-before-write, not atomic guarantees.

To re-plan in an existing version-4 workspace, pass fresh `--source-file`,
`--model-catalog-file`, `--destination-file` and `--capabilities-file` inputs to
`compile-plan` together with the new `--selection-file` and matching fresh native
previews for Foundry model work. This validates and
commits a new immutable generation with fresh pending approvals and behavior
checks; it does not overwrite the old baseline. Source/destination identities
must remain the workspace's selected resources. Alternatively initialize a fresh
workspace from the new evidence.

Do not invoke native `model-provider sync --yes` as a migration apply shortcut:
its stale deletion behavior conflicts with this workflow. b22 has no finite
selection, preserve-stale, or externally approved-plan binding for bulk apply.
Preview does not approve writes: accepted changes expand into individually
approved native resource operations. Convenience Foundry onboarding with
implicit identity/RBAC changes is not used.

Execute and approve each resource TODO using the skill's normal exact-digest
commands. `resourceDependencies` require predecessor read-back, while
`dependsOn` requires predecessor behavior verification. Failed/inconclusive
mapping behavior blocks downstream work. Read-before-write is not atomic.

After all required resources for a mapping are read-back verified, record each
owned source behavior separately:

```bash
"$PYTHON" "$HELPER" record-verification --state-dir <state> \
  --mapping-id <mapping-id> --behavior-id <source-behavior-id> \
  --method <control-plane-or-data-plane-or-administrator-attestation> \
  --evidence-digest <redacted-evidence-digest> --plan-digest <current-plan-digest>
```

Resource-only nodes do not become proof of source behavior. Inference payloads,
costs, actual MCP calls, identity-isolation checks and cutover need their separate
approvals. Never substitute a shared upstream identity to claim equivalent
caller-token propagation. Fresh read-back and current-plan residual acceptance
remain necessary for completion.

## Explicit b22 capability selections

The optional fields below extend existing version-1 selections. Omitting them
preserves the original finite graph. Recollect capability/destination evidence
and compile a new immutable generation with fresh approvals, preserving old
generations. Source inventory stays independent and retains all gaps/redaction.

Workspace/model policies, network edits, connection approval and key lifecycle
updates require existing verified targets and complete fresh reads. For new
targets, create/verify a foundation and re-plan first. Exporter creation and
aliases can depend on new gateway/model nodes in the same granular graph.

`policies`, `network`, `connections` and `telemetry` entries require exact
`sourceIds`, disjoint inventory `behaviorIds`, `evidence` and a nonempty
`scopeDecision`. They split those behaviors out of existing mappings, preserving
other behavior and prerequisites. Do not bind unrelated service properties to
make a capability ready. Unknown coverage remains blocked.

### Workspace and model policies

Use `policies: [...]`, one entry per workspace/model target:

```json
{
  "scope": "workspace",
  "sourceIds": ["<observed-source-policy-id>"],
  "behaviorIds": ["<observed-policy-behavior-id>"],
  "evidence": "Reviewed effective limits and required enforcement checks.",
  "scopeDecision": "Explicitly selected default-workspace identity scope.",
  "settings": {
    "calls-per-period": 100,
    "period-seconds": 60,
    "rate-counter-key": ["Identity"]
  }
}
```

For `scope: "model"`, include exact existing destination `provider` and `model`
names. Supported settings include explicit token limits/period/counter lists,
content-safety severities, and optional cost amount/period/counter/ID. Request
counts/period seconds and IP filter mode/address lists are workspace-only.
Use `ip-filter-mode: "allow"|"deny"` with validated IP/CIDR `ip-addresses`.
Counters contain Identity/IPAddress or identity/ipAddress, never expressions or
`All`. Cost periods are hour/day/week/month/year; amounts are finite and
non-negative. Opaque cost overrides are not enabled.

Cost-only new governance can bind the gateway's base behavior or already-selected
model API behavior with `newGovernance: true`. This adds explicit governance,
not source quota equivalence; original resource prerequisites remain owned.

Policies preserve sibling types and require full approved read-back. Do not
flatten APIM service/product/API/operation precedence, expression counters,
conditional increments or filter order without reviewed translation. Only
listed policy statement families are enabled, not arbitrary XML. When source
inputs are redacted, prepare a typed entry and obtain approval of its bindings,
settings and scope decision:

```bash
"$PYTHON" "$HELPER" translation-digest --path policy.intent.json
```

After approval, put that digest in `translationDigest`. It binds the proposed
translation, not proof of expression equality or enforcement. Changed intent
requires fresh approval; unowned behaviors stay unresolved. Model writes require
ETag/If-Match, while workspace writes may be unconditional without an ETag.

### Networking and private connections

`network` adds `settings` with selected `subnet`, `public-network-access` or
`disable-vnet-integration: true`, and `verificationAccess` describing an
independently verified path. Subnet and integration removal are mutually
exclusive. Bind only source networking properties. The subnet must already
exist with the required region/delegation; assert `network show`'s normalized
subnet/access fields.

`connections: [...]` additionally select the existing destination connection
`name`, exact `peerId` and approval `description`. They do not copy a source ID
or provision endpoints/DNS. Public-access disabling depends on selected
connection approvals. Independently verify the private path before removing
public verification access.

Optional `gateway.sku` selects Standard/Premium/Consumption explicitly.
Without it, b22 lets the service select Standard; never copy APIM sizing.

### Telemetry and key lifecycle

`telemetry: [...]` adds a valid exporter `name` and settings such as:

```json
{
  "kind": "ApplicationInsights",
  "application-insights": {
    "connectionString": {"$runtimeSecret": "TELEMETRY_CONNECTION"}
  },
  "payload-capture": false
}
```

Use an existing authorized resource and operator runtime credential, not a
persisted source logger secret. Review sampling, fields and payload exposure
separately. Explicit `reuseExisting`/`updateExisting` decisions protect existing
exporters; matching redacted metadata does not establish credential equality
or imply a secret-only update. Only the documented ApplicationInsights
connection-string write shape is reviewed. OpenTelemetry/free-form writes stay
blocked until their child fields are reviewed. Existing metadata verification
does not prove delivery.

Existing `keys` may add `state: "active"|"suspended"`, timezone-qualified
`expirationDate`, and `updateExisting: true`. Use the existing display name:
the service rejects rename. New keys need a metadata foundation before
lifecycle updates. No secret reads/copy/rotation occur. A suspended key cannot
be the only explicitly selected admission for model/MCP traffic.

### MCP versions and multi-backend aliases

MCP selections may include finite `versions`. Reused unchanged endpoints can
receive a versions-only update that sends only `--versions`. Endpoint replacement
still needs `replaceEndpoints` and `credentialUseApproved: true` after approval
of internal destination secret reads. Supplied membership is complete: matching
IDs/namespaces preserve nested fields, not omitted sources. MCP update does not
expose `--failure-mode`.

Models retain their original single-backend aliases by default. For a shared
pool, set participating models' `explicitAlias: true` and add an `aliases` entry
with unique `name`/`routingName`, `sourceIds`, `evidence`, `scopeDecision` and
explicit `backends`:

With `explicitAlias: true`, omit the model's single-backend `alias`/`routingName`
fields; the explicit alias entry owns the callable route.

```json
[
  {"provider": "selected-provider", "model": "model-a", "priority": 0, "weight": 75},
  {"provider": "selected-provider", "model": "model-b", "priority": 1, "weight": 25}
]
```

References are selected model registration names, not runtime deployment IDs.
Each alias has 1-30 distinct gateway-bound backends, priorities 0-100 and weights
1-100. All backends must share the selected API format and operation surface;
different model families/providers are allowed, incompatible protocols are not.
Replacement requires `updateExisting: true`. The graph shares prerequisites
and retains one owner per behavior. Without source-pool bindings, this is an
explicit destination topology decision, not proof of APIM pool translation.

### Translate an observed APIM backend pool

Read the selected backend's `properties.type`, `properties.pool.services` and
each member backend from authoritative inventory. The
[APIM 2024-05-01 backend contract](https://learn.microsoft.com/en-us/rest/api/apimanagement/backend/get?view=rest-apimanagement-2024-05-01)
defines member ARM IDs, priorities and weights. Follow the effective API/policy
route to that exact pool; do not identify it by a similar name in another scope.
Resolve each member's runtime model and protocol independently using the catalog
workflow above. A pool member URL identifies an upstream boundary, not a model
family, deployment name or callable alias.

Keep each provider bound to its single member backend and credential boundary,
not the pool resource. Set participating models' `explicitAlias: true`. Their
source bindings retain the routed API, operations and any supported routing-only
policies. Add the pool to the shared alias's `sourceIds` and select `sourcePoolId`.
Include the observed routing-policy resource in the alias's `sourceIds` when
`set-backend-service` establishes the pool route.
Each alias backend adds its exact `sourceBackendId`; `provider` remains the
destination provider name, which may differ from its catalog identity.

```json
{
  "name": "production",
  "routingName": "customer/production",
  "sourcePoolId": "<source-service-id>/backends/model-pool",
  "sourceIds": [
    "<source-service-id>/backends/model-pool",
    "<source-service-id>/apis/inference",
    "<source-service-id>/apis/inference/policies/policy"
  ],
  "evidence": "Observed API route, complete pool membership and selected model catalogs.",
  "scopeDecision": "Preserve the evidenced pool configuration; verify runtime failure behavior separately.",
  "backends": [
    {"provider": "provider-a", "model": "model-a", "sourceBackendId": "<source-service-id>/backends/upstream-a", "priority": 0, "weight": 75},
    {"provider": "provider-b", "model": "model-b", "sourceBackendId": "<source-service-id>/backends/upstream-b", "priority": 0, "weight": 25}
  ]
}
```

Compilation requires all distinct pool members exactly once, in the same source
scope, bound to their selected providers. It rejects missing/extra/nested members,
changed priorities/weights and unreviewed pool fields. Source priorities/weights
must be explicit integers within the reviewed destination ranges. APIM permits
null/omitted values and zero weights; the adapter does not invent defaults,
enable a disabled member or silently drop it. Keep those cases unresolved until
a supported separate routing decision is available.

Equal-priority weights describe relative distribution within that priority
group, not percentages across all priorities. Different priorities express
preferred/fallback groups; a lower-priority group is not an ordinary weighted
share of healthy primary traffic. Preserve numbers rather than normalizing
across groups.

### Assess failure behavior and verify routing

The reviewed b22 model-alias contract exposes backend identities, priorities and
weights, not a model `failureMode`, configurable retry policy or circuit breaker.
Do not reuse MCP's unrelated `--failure-mode` option. Before mapping a route,
inspect effective service/product/API/operation policies and fragments, plus
pool/member backend circuit-breaker configuration. Record the actual failure
status codes/error reasons, retry counts/delays, `Retry-After` handling, trip
threshold/window/duration and recovery behavior where evidenced. Redacted
expressions are unknown, not defaults.

Source circuit breakers, retry statements and nonempty `on-error` handlers
cannot become supported model-routing mappings under this contract. Planning
rejects them even if the alias priorities match. An empty `on-error` container
does not itself add failure behavior. Report unsupported behavior as an explicit
adapter gap, retain the affected source path, and assess unaffected routes
separately. Do not claim a platform limitation or remove a source safeguard to
obtain a passing plan. New native failure controls require an authoritative
CLI/API capability review before exposing them in selections or commands.

For supported configurations, first verify the alias's exact model resource IDs,
priority/weight values and prerequisite read-backs; preserve unrelated aliases
and policies, and require `updateExisting: true` for a replacement. Offline
regressions prove configuration translation, not service execution semantics.
With separate approval of inference costs, credentials and resettable fault
injection, verify weighted distribution among healthy equal-priority models,
preferred-group routing, the observed conditions that activate fallback, and
recovery to the preferred group. Include distinct models/providers in that
verification; do not substitute two names for the same deployment. Retain
redacted evidence and record each owned source behavior using the normal
current-plan verification command. Without that evidence, describe routing as
configuration-verified, not behavior-verified or ready for client cutover.
