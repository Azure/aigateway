# Evidence and model mapping

Load this reference for model discovery, finite model selection or exported
source evidence. The main skill owns review, confirmation, native asset TODOs
and direct CLI execution; this reference does not add a deployment engine.

## Discover the actual model surface

The gateway has two model-provider kinds, and each backend APIM routes to maps
to one of them:

| Provider | Typical backend | How to list its models |
| --- | --- | --- |
| Foundry | Azure AI Foundry / Azure OpenAI account | ARM deployments of the account (`--kind Foundry`) |
| Custom, OpenAI-compatible | Third-party or self-hosted `/v1` API | `GET <base>/v1/models`, `data[].id` (`--kind Custom`) |
| Custom, Anthropic | Anthropic Messages API | `GET <base>/v1/models` with `x-api-key` and `anthropic-version`, `has_more`/`after_id` paging (`--catalog-format anthropic`) |

When APIM operations or policies pin a fixed set of model names, that set is
the scope and the catalog only confirms the names exist. When APIM forwards
model names through, the catalog defines the candidates the user selects from.
Follow scoped backend routing, policy fragments and pools to find each backend;
keep opaque expressions unresolved rather than evaluating them. A public path
can differ from its upstream protocol.

For a Custom catalog:

1. Use the backend base URL and observed version prefix from APIM; the collector
   appends `/models`. Do not guess another endpoint.
2. Use the credential APIM already sends to that backend (named value or backend
   header). Scoping consent covers the pre-confirmation read when it identifies
   the credential source, upstream and read-only catalog purpose. If reuse was
   declined, ask for a catalog credential or an operator manifest. Never send an
   APIM subscription key or ARM token to the upstream model host.
3. Record success, connectivity/authentication error, malformed response or not
   attempted. A 401/404 is not proof of absent models.

GET model catalogs and approved minimal MCP initialize/tools/list are discovery,
not business-tool execution or inference authorization. A model list does not
prove protocol support. Register the protocols the APIM API exposes for that
backend, narrowed by model-specific catalog fields or one official provider page
per model family when it changes which operations to register. Leave the rest to
the smoke tests only after destination support is established; do not invoke
inference to discover capabilities before confirmation.

Destination support is a separate check from source discovery. A catalog entry,
an OpenAI-compatible endpoint, a route in the gateway operation catalog or an
accepted model registration does not prove the destination supports that
model's operation or output modality. Verify the specific model capability
against current destination documentation or contract before planning its
destination assets. Keep a known unsupported model or operation in APIM; when
evidence is insufficient, mark it undetermined and do not use runtime smoke
tests to discover support.

Current product limitation (reported 2026-11-11): image-generation model
outputs are unsupported. Keep those models and their image-generation smoke
tests on APIM. This does not imply that models accepting image input are
unsupported. Recheck the current official AI Gateway model documentation before
revising this limitation because preview capabilities can change.

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

Custom discovery normally reads the APIM named value that already authenticates
the backend and sends it only to that backend. The native POST only reads the
secret; nothing changes on APIM:

```bash
"$PYTHON" "$HELPER" collect-models --provider-id custom-a --kind Custom \
  --endpoint <observed-backend-base-with-version> \
  --source-id <source-service-id> \
  --credential-resource-id <source-service-id>/namedValues/<id> \
  --credential-field value --credential-header <observed-header> \
  --approved-read --approved-credential-read --output-file custom.catalog.json
```

Add `--catalog-format anthropic` for an Anthropic backend (header usually
`x-api-key`). `--credential-scheme` prefixes Bearer/Basic only when that is the
observed mechanism; omit it if the value already contains the scheme. When the
user supplies a separate catalog credential, pass it with `--credential-env`
instead of `--credential-resource-id`. An APIM subscription key
(`/subscriptions/<id>`, field `primaryKey`, header `Ocp-Apim-Subscription-Key`)
may only be sent to the APIM gateway URL, never upstream. Key Vault references
are not permission to read another secret. Never request pasted credentials.

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
