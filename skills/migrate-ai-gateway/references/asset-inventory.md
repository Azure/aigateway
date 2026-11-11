# Asset inventory and review

The approved inventory is the migration contract, not executable code. The agent
runs native CLI commands using host tools; no helper applies this document.
Schemas check structure, not platform support, authorization or command safety.

## Files

Keep evidence and migration artifacts in protected local storage:

- `source-inventory.json` and relevant catalogs: read-only discovery evidence.
- `migration-inventory.json`: desired assets, exact operations, tests and exclusions.
- `migration-review.md`: readable projection of that inventory revision.
- Non-secret JSON argument files referenced by the inventory, each with a digest.
- `migration-results.json`: confirmation and per-asset receipts, not an execution engine.
- Optional `commands.txt`: secret-free direct CLI sequence for reproduction.

The [labelled example](../examples/migration-inventory.json) creates a gateway and
its identity. It is not a deployable recommendation: replace example IDs and
evidence with authorized observations. Use the same asset IDs in native TODOs.

## Inventory fields

| Field | Meaning |
| --- | --- |
| `revision`, source/destination IDs | Explicit reviewed scope; a different desired configuration is a new revision |
| `evidence` | Protected evidence paths, canonical document digests, capture times and scope |
| `decisions`, `exclusions`, `blockers` | Resolved choices, retained behavior with impact/follow-up, and unresolved required facts |
| `inputs` | Non-secret JSON file paths/digests or secret references with exact source, allowed destination and safe handling |
| `assets` | One stable entry per gateway, provider, model, alias, MCP server or independently managed configuration/external prerequisite |
| Asset `configuration` | Desired non-secret state, with source provenance and explicit semantic differences |
| `preconditions`, `dependsOn` | Exact target state and asset prerequisites, not list-order assumptions |
| `commands`, `readBack` | Ordered `az` argument arrays and configuration assertions; no shell expressions or custom executors |
| `outputs` | Non-secret values extracted from successful read-back with type/scope constraints |
| `smokeTests` | Exact bounded request, credential references, expected outcome and permitted skip conditions |
| `verificationLimits` | What read-back or these tests cannot establish |
| `sideEffects`, `rollback` | Charges, access/replacement impacts and rollback limits; no implicit cleanup |

An argument object `{"inputId":"provider-config"}` refers to an inventoried input.
An argument object `{"assetId":"gateway-identity","output":"principal-id"}` refers
to a declared output of a dependency. These are review notation, not strings to
send to Azure CLI. The agent resolves them only within the approved constraints.
JSON inputs contain actual advertised CLI shapes; files do not interpolate values.

For an external role assignment, inventory the exact account scope and role ID,
bind `--assignee-object-id` to the new identity's read-back principal, and state
`--assignee-principal-type ServicePrincipal`. Inspect existing assignments first;
do not grant a broader role to resolve an error. Authorizing this binding does not
authorize a different principal, role or scope.

Secret values never appear in inventory, evidence, reviews, TODO descriptions,
logged output, receipts or command records. An existing APIM-held backend
credential may be reused for the same upstream when the review explicitly
includes its exact source, destination asset, upstream URL, header and handling.
Record the secret source and permitted destination in a `secret` input, not its
value or digest. The user's reuse choice plus migration confirmation authorize
reading it during execution; do not read it earlier.

Use the narrowest source read: an APIM backend GET can return all of that
backend's credential fields, even when CLI `--query` filters its output. Include
that read and its scope in the review. An explicitly identified named value has
a read-only `listValue` POST. Resolve references from non-secret evidence and do
not evaluate policy expressions. Key Vault access is a separate scope, not
implied by an APIM reference. A denied read, redaction, unresolved expression or
incompatible credential input blocks the affected asset. Explain that sharing a
key increases its holders and couples rotation or revocation across services.

APIM client subscription keys are not gateway admission keys. If explicitly
approved as an outbound credential for an APIM bridge, send one only to the
selected APIM origin, never to an unrelated upstream.

### Protected native input

Inventory the exact Azure CLI read and destination command as argument arrays,
and record private temporary paths, projection, validation and cleanup in the
secret input's `handling`. Resolve its `inputId` to the verified temporary
file only for the approved destination command. Check current non-secret source
routing against the review before reading the credential. Use fresh files in an
owner-only directory outside the repository, restrict permissions before creation,
keep tracing off, and remove those exact files after use or interruption.
Owner-only permissions do not isolate processes sharing that OS identity; block
if the host cannot protect the credential sufficiently. Never put the secret
in arguments or display raw output. Without a safe native input mechanism,
block rather than invent a Python/shell credential executor.

For example, after confirmation, an MCP source with one literal backend header
can be projected by the Azure CLI into its native endpoint array. Replace every
non-secret example value with the reviewed source and destination values:

```bash
umask 077
set -o noclobber
az rest --method get --subscription "$SOURCE_SUBSCRIPTION" \
  --url "$APIM_BACKEND_URL?api-version=2024-05-01" \
  --query '[{kind:`"mcp"`,namespace:`"example"`,required:`true`,
    mcp:{url:`"https://upstream.example/mcp"`,transport:`"streamableHttp"`},
    credentials:{type:`"header"`,headers:{"X-Backend-Key":properties.credentials.header."X-Backend-Key"}}}]' \
  --only-show-errors --output json > "$MCP_ENDPOINTS_FILE" 2> "$MCP_ERROR_FILE"
```

Check the command's status, then validate the protected file without printing
it: the exact reviewed URL and endpoint shape must match, and the selected
header must contain the expected nonempty literal value, not a redaction marker,
expression or control characters. On failure, report it without exposing
sensitive output, remove both files and block the asset. On success, use the
file as `--endpoints @<file>` with the approved `az aigateway mcp create`
command, then remove both files. A named-value `listValue` read or a provider
input needs its own reviewed projection and JSON shape. The reviewed
`az rest --output-file` saves the raw response, not the `--query` projection;
recheck CLI behavior rather than using it to capture filtered secrets.

## Review checklist

Complete this review before asking for confirmation:

1. Evidence is authoritative for the selected behavior. Every selected behavior
   has an asset mapping or an explicit retained/excluded disposition. Missing
   source configuration blocks its asset; unverified runtime behavior is a test
   limitation, not a blocker.
2. Source and destination IDs are distinct resource families. Targets, tenant,
   subscriptions and external scopes are explicit. Source writes, DNS/client
   cutover, deletion and unlisted role grants are absent.
3. Asset/input IDs are unique. Dependencies and input/output references resolve,
   outputs come from declared dependencies, and dependencies have no cycles.
   There is one native TODO per executable asset, not per CLI command.
4. Each command is supported for the exact target family. Verify selected flags
   and JSON shapes using current official CLI evidence. Inspect commands as
   data, not a string to evaluate; `az rest` destination writes are not substitutes.
5. Creates cannot overwrite unapproved state; updates preserve siblings and use
   service concurrency controls where supported. Read-before-write is not atomic.
6. Every non-secret argument file matches its recorded canonical digest. Review
   and inventory are the same revision. `blockers` is empty for the approved
   execution scope; manual prerequisites have an owner and verification path.
7. Identity, access scope, policy semantics, monitoring, external writes and
   charges are explicit. Model IDs alone do not prove operation support.
8. Each asset has read-back assertions. Smoke-test requests specify the endpoint,
   method/protocol, payload, credential inputs and maximum requests; include
   `bounds.maxTokens` for model tests. Disclose possible charges in the review
   without requiring a pricing study for small routine tests. Honor any user-set
   cost ceiling: if compliance cannot be established, omit the affected test
   and record the blocker. An estimate is not an enforceable billing cap.
9. Exclusions, test limitations, manual actions and rollback limits are visible.
   Approval includes them; it is not inferred acceptance of unseen behavior.

Use the collection entry point's `validate-document --schema migration-inventory`
for a structural check and `document-digest` to identify the reviewed document.
Neither performs a write or establishes execution readiness. The inventory
digest covers referenced non-secret file digests; verify those files separately.
Do not digest secrets. Confirmation goes into `migration-results.json`, bound to
that digest, with a pointer to the user's actual confirmation rather than
fabricated attestation.

## Native TODOs and receipts

After confirmation, create all asset TODOs, then dependency links. For Copilot use
the host SQL `todos`/`todo_deps` tables; use the corresponding native facility on
other hosts. Namespace IDs if several migrations share a session, retaining the
inventory asset ID in the description. No second handwritten TODO plan is needed.

Create/update/reuse assets get TODOs. Manual assets are named prerequisites, not
automatic commands or fake completed work. If the host lacks native TODO support,
display asset progress from receipts without inventing a tool.

Keep the approved JSON and argument files unchanged. Results separately record
per-asset provisioning and check outcomes. Persist non-secret receipts before
advancing dependents; do not make reporting recollect the entire source.
Mark a native TODO done only after read-back and all required tests pass.
Optional tests can be skipped with the approved reason; explicitly report the
remaining unverified behavior. A skipped required test leaves verification blocked.

On resume, compare the approved revision and receipts with native TODOs, read the
exact interrupted target and reconcile unknown outcomes before retry. Matching
state may be reused after read-back; conflicting state requires review. Old
engine generations and approvals are historical evidence only, not permission to
replay writes under this workflow.
