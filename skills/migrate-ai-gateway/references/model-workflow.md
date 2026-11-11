# Evidence and model mapping

Load this reference for model discovery, finite model selection or exported
source evidence. The main skill owns review, confirmation, native asset TODOs
and direct CLI execution; this reference does not add a deployment engine.

## Discover the actual model surface

Start from the models APIM configuration routes: operations, policies, backend
paths and deployments on referenced accounts. Read an upstream catalog only when
APIM routes model names dynamically; name that read in the scoping question.
Resolve exact runtime model IDs, provider/credential boundaries and supported
operations from that evidence. A public path can differ from its upstream
protocol. Follow scoped backend routing, policy fragments and pools; keep opaque
expressions unresolved rather than evaluating them.

For a model catalog:

1. Build the exact route from observed API path, operation, backend and effective
   rewriting. The Custom collector appends `/models` to the provider base URL;
   include the observed version prefix, not a guessed endpoint.
2. Prefer an APIM route when APIM injects upstream authentication. Its client
   credential belongs only at that APIM origin. A direct upstream route needs
   explicit authorization for that upstream credential boundary.
3. Approve the exact endpoint and credential source before use. Verify subscription
   scope actually covers the selected API; a suggestive name is not scope proof.
   Never send an APIM key or ARM token to the upstream model host.
4. Record success, connectivity/authentication error, malformed response, unsupported
   operation or not attempted. An unauthenticated request to a protected route is
   not an authorized catalog attempt. A 401/404 is not proof of absent models.

GET model catalogs and approved minimal MCP initialize/tools/list are discovery,
not business-tool execution or inference authorization. Do not invoke inference
just to discover capabilities without approval naming operation, payload,
credential boundary and cost. A model list does not prove protocol support.
Use model-specific catalog fields, official provider documentation or prior
approved runtime evidence; otherwise leave operations unresolved.

## Collect source model facts

`PYTHON` and `HELPER` are the isolated interpreter and collection entry point from
the main skill. Foundry discovery reads one existing account's deployments:

```bash
"$PYTHON" "$HELPER" collect-models --provider-id account-a \
  --kind Foundry --account-id <existing-account-arm-id> \
  --endpoint <observed-account-endpoint> --approved-read \
  --output-file foundry.catalog.json
```

This keeps deployment ID, runtime deployment name, family and version separate.
It creates no provider, identity, model, role or alias.

Custom discovery uses a complete header value from a securely established
environment variable, never ARM authentication:

```bash
"$PYTHON" "$HELPER" collect-models --provider-id custom-a --kind Custom \
  --endpoint <approved-https-provider-base> \
  --credential-env UPSTREAM_AUTHORIZATION --credential-header Authorization \
  --approved-read --output-file custom.catalog.json
```

The alternative is a separately approved, exact APIM named-value or subscription
read. These native POST operations only read a secret; nothing changes on APIM:

```bash
"$PYTHON" "$HELPER" collect-models --provider-id apim-a --kind Custom \
  --endpoint <observed-apim-gateway-url>/<api-suffix> \
  --source-id <source-service-id> \
  --credential-resource-id <source-service-id>/subscriptions/<subscription-id> \
  --credential-field primaryKey --credential-header Ocp-Apim-Subscription-Key \
  --approved-read --approved-credential-read --output-file apim.catalog.json
```

For a named value, use its exact `/namedValues/<id>`, field `value`, observed
upstream header and explicitly approved upstream URL. `--credential-scheme`
prefixes Bearer/Basic only when that is the observed mechanism; omit it if the
value already contains the scheme. Key Vault references are not permission to
read another secret. Never request pasted credentials. Discovery approval does
not authorize destination reuse; inventory that separately under the
[asset contract](asset-inventory.md).

Approval flags record approval already obtained. Values remain in collector
memory only, not output, argument strings, files or catalogs. Catalogs retain
non-secret credential provenance. Redirects are rejected; pagination stays on
the selected origin/path. Limits, malformed responses and failed credentials
produce explicit failed evidence, not empty successful catalogs.

Operator-supplied catalog evidence uses `schemas/model-catalog.schema.json`
with `provenance: "operator-manifest"`, `complete: false`, explicit IDs, actual
attestation time and unknown fields left null/empty. Approve its digest before
importing; it describes intent, not exhaustive discovery:

```bash
"$PYTHON" "$HELPER" document-digest --path operator.models.json
"$PYTHON" "$HELPER" import-models --manifest-file operator.models.json \
  --approved-digest <document-digest> --output-file manual.catalog.json
"$PYTHON" "$HELPER" merge-model-catalogs \
  --catalog-file foundry.catalog.json --catalog-file manual.catalog.json \
  --output-file models.catalog.json
```

## Map finite assets, not an entire API

Create inventory entries for each provider, model and callable alias. Separate
accounts/credential boundaries need separate providers even when hosts or model
names match. Configuration examples in the official CLI reference describe the
current input shapes; validate selected fields rather than guessing them.

- Provider: exact endpoint, kind, account and explicit authentication. Low-level
  `model-provider create` does not implicitly grant RBAC or import models.
- Model: exact runtime/deployment ID, name, version and finite evidenced protocol
  operations. Registration does not deploy the upstream model.
- Alias: explicit ARM name, callable routing name and exact backend registrations.
  The caller uses the alias's routing name, not necessarily the deployment name.
- Access: explicit gateway admission. Gateway-wide keys differ from source
  per-API/product subscriptions or anonymous admission.
- Policy: explicit scope, counter identity, windows and semantic differences,
  not an automatic conversion of APIM XML.

For Foundry, use the verified deployment catalog to plan direct native model
registrations. Do not require a sync preview against an uncreated foundation.
If the user actually needs synchronization membership analysis on an existing
provider, an authorized native `model-provider sync --dry-run` may supply evidence.
Inspect its scope and proposed actions. Bulk apply/delete is not authorized by
that read or by selecting individual registrations.

When an inference API also exposes files, administration or wildcard operations,
map only the evidenced finite inference subset and explicitly retain or resolve
the rest. Never infer all wildcard paths are inference or model names establish
supported operations.

### Shared routing and source pools

For a shared alias, inventory exact provider/model registrations, common protocol/
operation support, priorities and weights. Follow source pool members to each
backend/account/credential boundary and preserve observed priorities/weights
when claiming equivalent routing. Nested pools, dynamic membership, zero/default
weights and opaque routing need separate conclusions.

Source retries, circuit-breaker conditions and error handlers are not proven by
an alias registration. Retain required behavior or explicitly approve a redesign;
do not describe dropped failure handling as equivalent failover.

## Approved local exports

APIOps and ARM exports supplement authorized reads; their presence alone does not
prove completeness. Compute and approve the current artifact digest first:

```bash
"$PYTHON" "$HELPER" export-digest --path <local-export>
"$PYTHON" "$HELPER" collect-source --source-id <source-id> \
  --apiops-artifact <directory> --apiops-approved-digest <approved-digest> \
  --output-file source.with-export.json
```

`--arm-template-file` with `--arm-approved-digest` adds advisory ARM evidence.
Changed files need new approval. Running an extractor needs separate authorization;
never run a publisher, deploy a source template, evaluate expressions or resolve
export secrets.

Recognized APIOps information files, policy XML and structural contracts retain
their scoped IDs. Unknown artifacts, conflicting facts or failed reads stay
explicit. Recovering a collection requires `inventory-metadata.json` claims with
the exact source, supported domain/scope, resource IDs and completeness statement;
do not fabricate those claims. Authority order is complete live discovery,
approved complete APIOps evidence, advisory ARM evidence, partial observation.

The [asset inventory contract](asset-inventory.md) links this evidence to the
reviewed destination design. Discovery evidence is never itself write approval.
