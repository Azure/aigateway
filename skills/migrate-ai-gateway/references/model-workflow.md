# Explicit model discovery, import, and synchronization

These are source-only facts followed by a destination selection, not an APIM API
import. Use the selected isolated Python environment and the skill's
`scripts/migration.py` helper. Examples describe shapes, not evidence that an
example model or account exists. Obtain actual identifiers from authorized
discovery or explicit operator input.

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

Unauthenticated catalogs may omit `--credential-env`. Redirects are rejected.
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
  of anonymous clients. Key values are not copied or retrieved by this workflow.
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

The published b15 CLI can fail even dry-run if a stale registration is referenced
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
its stale deletion behavior conflicts with this workflow. b15 has no finite
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
