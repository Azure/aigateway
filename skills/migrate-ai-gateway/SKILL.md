---
name: migrate-ai-gateway
version: 6.0.0
description: Assess and migrate APIM AI traffic using read-only discovery, a user-reviewed asset inventory, one scoped confirmation, native per-asset TODOs, direct Azure CLI commands and bounded smoke tests.
---

# Migrate APIM AI traffic to Azure AI Gateway

Invoked as `/aigateway:migrate-ai-gateway` or `/aigateway:migrate`. This is assisted
configuration migration from any APIM tier into a separate
`Microsoft.ApiManagement/aigateways` resource, not in-place conversion or full
APIM replacement. The source `Microsoft.ApiManagement/service` stays read-only.

## Operating model

**Discover -> refine with the user -> review asset inventory -> confirm once ->
native asset TODOs -> direct Azure CLI -> smoke tests.**

The inventory is the contract. The agent executes it with host tools, not a
custom deployment script or reconciliation engine. Bundled Python supports
read-only collection, local evidence utilities and the bounded smoke helper.

- Assessment is not execution. A source-only feasibility request does not need
  a destination, deployment inventory, credentials for future writes or approvals.
- The APIM control plane defines what to recreate: endpoints, backends and their
  credential metadata, policies, identities, networking and diagnostics. The
  invocation authorizes reading its configuration; mirror it by default.
- Ask only about scope, destination, reuse of APIM-held backend credentials and
  source behavior the destination cannot represent; batch these into one round.
- Stay on the migration. Before confirmation, do not inspect backend resources
  or other subscriptions, probe runtimes or assess cost. Runtime behavior is for
  the approved smoke tests; only missing source configuration blocks an asset.
- Research only facts that would change an inventory entry. Start with the
  bundled CLI and management references, use one authoritative source per fact
  and stop once it is settled; record remaining runtime unknowns as test items,
  because extra cross-checks delay the review without changing the plan.
- Confirm the complete reviewed inventory once. It includes exact writes,
  external permissions, credential boundaries and bounded tests. Ask again for
  changed intent, not ordinary progress. Host permission controls still apply.
- Keep secrets out of persistent artifacts, logs and history. Read reused
  credentials during approved execution unless the user explicitly authorizes
  an earlier scoped read; APIM subscriptions are not gateway keys.
- Distinguish provisioning, reachability and semantic equivalence.

## 1. Start read-only inventory

Locate this skill and protect the working evidence directory. Reuse an existing
Python environment with the required dependencies when available. If they are
missing, ask before installing them in an isolated environment outside the source tree:

```bash
python3 -m venv <protected-local-venv>
<protected-local-venv>/bin/python -m pip install -r skills/migrate-ai-gateway/requirements.txt
```

Below, `PYTHON` is the selected interpreter and `HELPER` is this skill's
`scripts/migration.py`. Use that interpreter for every bundled helper, including
the smoke runner; repeat its full path when shell calls do not share state.
Output paths must be new; preserve prior evidence.

```bash
"$PYTHON" "$HELPER" collect-source \
  --source-id <complete-apim-service-id> --output-file source-inventory.json
```

Collection records the actual SKU, healthy provisioning, redacted resource
configuration, policy structure, scoped dependencies, behaviors and coverage.
Any APIM tier is a valid source. Tier affects comparison, not discovery eligibility.
The inventory is configuration evidence, not proof of traffic or runtime behavior.

Discover model-facing APIs, MCP tools and their dependencies from protocols,
operations, policies, backends and access metadata, not names. Distinguish
conventional and MCP API counts. Keep REST APIs when MCP operations or shared
dependencies need them. Identify supported inference separately from files,
administration and other non-inference paths.

The collector covers service/workspace APIs, operations, schemas, revisions,
policies, backends, named values, products, access metadata and diagnostics.
Service API typing/tools use the preview contract; workspace tools are explicitly
not applicable where the published contract is service-scoped.
MCP facts retain the complete redacted configuration, endpoint names/templates,
backend/authentication metadata, policies and tool-to-operation links.

Failed, forbidden, partial and malformed reads are gaps, not empty collections.
Only a corroborated pricing-tier restriction establishes that a collection is
not applicable. Do not repair inventory by hand or merge partial attempts into
claimed completeness. Approved exports can supplement collection; see
[evidence and model discovery](references/model-workflow.md).

## 2. Finalize what migrates and how

Derive the design from source configuration. Honor an already selected subset
and earlier answers. For assessment-only requests, deliver the verdict and stop.

For each selected component compare:

- **Models:** exact deployment/runtime IDs, protocols, finite operations, backend
  accounts, input/output modalities and credential boundaries. A catalog ID,
  shared API route or accepted registration does not prove that the destination
  supports that model's operation or output modality. Verify destination support
  before including a model; keep unsupported models in APIM and leave unknown
  support undetermined rather than probing it with a smoke test. Follow
  [model discovery and routing](references/model-workflow.md) when relevant.
- **MCP:** endpoints/versions, tools/schemas, routing/rewrites, auth, policies
  and access. Compare native MCP and OpenAPI sources (which need a REST contract)
  directly or through APIM; prefer direct when evidence supports it. For tools
  exported from REST operations, the collector's `restSources` gives the backing
  API, upstream and operation policies, and `publishedEndpoint` the APIM URL. Check
  operations and credentials; tool names and schemas may differ. Derive endpoints
  from evidence, require only necessary upstream identifiers and treat failed
  probes as inconclusive rather than proof of unsupported behavior.
- **Access and identity:** client admission separately from backend identity.
  Gateway-wide keys do not preserve per-API/product or anonymous admission.
  Shared backend credentials do not establish per-caller token propagation.
- **Policies and routing:** effective inheritance, counter identities, windows,
  conditions and response changes. Classic/v2 source rate-limit semantics can
  differ. Retries, circuit breakers and arbitrary XML are not automatically
  equivalent to destination routing or typed policies.
- **Networking and monitoring:** mirror the source topology, diagnostics
  destinations and payload logging; where the source has none, plan none.

Give each source asset one status: **Migrate**, **Migrate (with <limitation>)**
or **Keep in APIM**. Explain the destination mapping, semantic changes and, for
retained behavior, whether the cause is the platform, this workflow or missing
evidence, plus the next technical resolution.

Before destination design, establish distinct complete source/destination ARM
IDs, explicit subscriptions, destination resource group/name and region if new.
For name-based gateway calls, verify that the CLI's effective subscription and
tenant match the selected target as well as passing explicit target arguments.
If they differ, use a protected isolated CLI context set to the target; do not
change the shared default. Protect and clean that context like other credentials.
Check only the selected commands' help and `aigateways` dispatch;
[capabilities](capabilities.json) is reviewed knowledge, not proof for future releases.

The read-only inspector verifies the installed official wheel and inspects only
the requested command surface:

```bash
"$PYTHON" "$HELPER" inspect-cli --command create --command "model create" \
  --output-file cli-evidence.json
"$PYTHON" "$HELPER" collect-destination \
  --destination-id <complete-aigateways-id> --group model-provider --group model \
  --output-file destination-inventory.json
```

Use the latest official published CLI, including previews. Installation requires
approval; do not downgrade, patch the extension or substitute destination REST
writes to work around missing support. Do not upgrade during the approved
execution sequence. External commands such as `az role assignment create` need
their own selected-command/scope review.

Source control-plane configuration reads need no separate approval. A scoping
answer can authorize listing a Custom provider's models with its APIM-held
credential if it identifies the secret source, upstream and read-only catalog
purpose. Any other pre-confirmation upstream call, secret read or inference is
rarely needed; if the design truly depends on one, name it in the scoping question.

## 3. Produce the reviewable asset inventory

Write `migration-inventory.json` and a matching `migration-review.md` using the
[asset contract and checklist](references/asset-inventory.md) and
[labelled example](examples/migration-inventory.json). Store them in protected
local storage; don't add migration artifacts to the repository implicitly.

The JSON is the source of truth. Include:

- Exact assets/configurations, target IDs, desired public state, source evidence,
  create/update/reuse/manual disposition and dependencies.
- Direct Azure CLI argument arrays, non-secret JSON input files and digests,
  preconditions, read-back assertions, side effects and rollback limits.
- Explicit late-bound outputs and allowed uses: for example, the new gateway
  principal consumed by one exact account-scoped role assignment.
- Credential references/use boundaries, finite test payloads/endpoints,
  request/token bounds, any user-set cost ceiling, expected outcomes and skip
  conditions.
- Exclusions, retained source behavior, impacts, manual actions and blockers.

Model providers, models, aliases and MCP servers are distinct assets. Identity,
policies, client access, networking and monitoring configurations get separate
entries when independently managed. Multiple CLI commands implementing one
asset stay in that asset, not separate TODOs.

External resources or permissions may be included only as explicit inventory
assets with exact scope and effects. Otherwise they are prerequisites/manual
blockers. Gateway identity assignment grants no backend RBAC by itself.
Source mutation, deletion, DNS and client cutover remain outside this workflow.

For selected Foundry deployments, plan explicit native model registrations from
verified catalog evidence. No mandatory sync preview or foundation write is
needed merely to compile the inventory. Use native `model-provider sync --dry-run`
only when synchronization membership is actually relevant and its existing
prerequisites/read authorization are available. Never use bulk sync apply to
expand or delete beyond the approved asset inventory.

Validate structure with `validate-document --schema migration-inventory --path
<file>` and complete the review checklist. Schema validity does not establish
support, readiness or user consent.

## 4. Confirm the migration

The user must be able to decide from the chat, not only from linked files.
Before asking, show a table with one row per source asset: source asset,
inventory result, status (Migrate / Migrate (with <limitation>) / Keep in APIM)
and proposed disposition. Follow it with brief notes on changed authentication,
paths and policy semantics, external writes, possible charges, test limits and
rollback constraints. Resolve required blockers first; do not hide them by
declaring a tiny foundation phase a completed migration.

Then offer three choices: review the detailed plan (open the readable review with
exact commands and inputs, then return to the same choice), approve and run, or
cancel.

Get one explicit confirmation bound to the reviewed revision and document digest,
including referenced input-file digests. `document-digest --path <file>` computes
the canonical JSON digest without a write. Verify every referenced file matches
its digest. Keep inventory/input files unchanged after confirmation.

Record confirmation separately in `migration-results.json`. This authorizes only
the displayed operations, credential use and tests. Changed targets, commands,
role scopes, secret sources, payloads or cost bounds require an amended inventory
and fresh confirmation. Successful planned writes do not invalidate remaining work.

## 5. Create one native TODO per asset

After confirmation, populate the host's native TODO capability from the approved
asset IDs and dependencies. For Copilot use `todos` and `todo_deps` through the SQL
tool; other hosts use their native equivalent. Insert all TODOs before dependency
rows. Include the inventory path/digest, asset ID and required verification in
descriptions. Do not maintain a competing hand-written checklist or custom TODO
file. If a host has no native capability, display progress from result receipts.

Create/update/reuse assets get TODOs. Manual prerequisites are visible blockers
with an owner and verification path, not fake successful work. Namespace native
IDs if several migrations share a session. Preserve their relation to asset IDs.

## 6. Execute native Azure CLI commands directly

Use host command tools to run the approved `az aigateway` commands and expressly
approved external `az` commands in dependency order. Do not invoke a custom apply,
deployment, reconciliation or provisioning runner. The dedicated smoke helper
below is the only permitted runtime test runner. Read-only helpers do not execute
the inventory. If requested, keep a secret-free script recording successful direct
provisioning commands and protected-input references, never values, as work proceeds.
It is a reproducibility record, not authority to replay against existing resources.

At run start, check the approved revision/files, selected tenant/subscription,
CLI version and prerequisite availability. Reuse the collected evidence; refresh
only facts made stale or contradicted for the affected operation. Do not recollect
the entire source, models, release catalog or unrelated destination collections
before every asset or to render a report.

Answer status questions from existing TODOs and receipts before continuing. An
explicit pause suspends migration work until the user resumes it.

For each asset:

1. Mark its native TODO in progress and identify the current operation.
2. Read the exact target/prerequisites. Establish absence before create; reuse
   matching state; stop on unexpected differences. Errors are not absence.
3. Execute only approved commands with explicit subscriptions and resource
   identifiers. Bind declared non-secret outputs from verified read-back; reject
   values outside the approved type/scope. Preserve sibling state and service
   concurrency controls. Read-before-write is not atomic.
4. Read back the requested configuration, perform the approved applicable checks,
   and persist non-secret per-asset receipts before advancing dependents.

Avoid concurrent writers to the same target. On timeout or interruption, inspect
the exact resource before any replay. A write may have succeeded despite missing
output. Never blindly retry, broaden permissions or silently redesign to fix a
failure. Stop affected dependents; propose changed intent for review.

Use safe supported native credential input mechanisms; see the asset contract.
Do not print keys, enable debug/shell tracing, persist secret-bearing CLI output,
or put values in command arguments. Protected temporary JSON is allowed when
needed, but no custom credential executor. Block when safe input is unavailable.
MCP endpoint replacement can trigger native secret reads and must be inventoried
as such. Monitoring payload capture is opt-in.

## 7. Smoke-test, resume and report

Each asset requires configuration read-back. If the approved inventory has no
non-manual aliases or MCP servers, report those runtime checks as inapplicable.
Otherwise, after confirmation, run the dedicated minimum smoke helper:

```bash
"$PYTHON" "$HELPER" validate-document --schema migration-inventory --path <inventory.json>
"$PYTHON" skills/migrate-ai-gateway/scripts/smoke.py \
  --inventory-file <inventory.json> \
  --confirmation-file <approved-results.json> \
  --approved-digest <confirmed-sha256-digest> \
  --output-file <new-protected-results.json>
```

The helper verifies the confirmation receipt against the inventory digest and
performs no Azure writes. It reads gateway, alias and tool-server
properties, verifies their IDs and uses the advertised runtime endpoint URLs;
it never constructs or guesses a hostname. It rejects missing, multiple or
over-budget smoke tests before traffic; each migrated alias or MCP server has
one approved test bounded as in the table. It does not retry, follow redirects,
execute tools or paginate. The inventory names the exact inference API and MCP
protocol version;
the helper verifies each is advertised by the resource before sending traffic.
Image-generation and unknown routes are rejected; an advertised route is not
proof that the destination supports the model's output modality.

Inbound calls use an Entra token for `https://ai.gateway.azure.com`, acquired
in memory from the explicitly selected Azure CLI subscription. The review states
the caller's required runtime role and possible inference charges. The helper does
not retrieve or fall back to gateway keys, so identity-based policies are
honored; missing runtime role/consent or a policy denial is reported as a
failed check. MCP versions must be supported session-based versions; when the
resource omits versions, the documented legacy compatibility set applies. The
report contains status, HTTP result, route or tool names/count, and
timing only; response content and credentials are not persisted.
It writes schema-valid migration results after each asset, with a durable
placeholder before sending a request. If interrupted, inspect that receipt and
do not replay an existing smoke check. To continue unchecked assets, use the
updated results as the confirmation receipt; the helper skips prior checks and
preserves their outcomes.

Run only the inventoried checks:

| Asset | Applicable bounded check |
| --- | --- |
| Model/alias | One request and one output token on the exact approved text-inference API |
| MCP | At most three requests: initialize, initialized notification and one tools/list; report tool names/count |
| Identity/RBAC | Read back principal and exact role/scope; this does not prove inference |
| Monitoring | Exporter read-back; ingestion check only with the approved access/test |
| Policy/network | Relevant enforcement/connectivity check when feasible; a successful request is not policy equivalence |

Record passed, failed, blocked or skipped tests and non-secret evidence. Optional
tests may be skipped only with a reason; failed or unrun required tests leave
verification incomplete. Mark a provisioning TODO done when its planned write or
reuse and read-back are complete and required test outcomes are recorded. A
failed test remains failed; it does not undo successful provisioning. Leave
unfinished provisioning pending or blocked. Do not fabricate administrator
attestation or call mere reachability equivalence.

On resume, use the approved inventory plus result receipts and native TODOs.
Reconcile interrupted assets by targeted reads; preserve completed assets.
Old engine checkpoints/approvals are historical evidence, not runnable authority.

In chat, use the inventory and latest applicable receipts to show a table
covering every selected asset and explicitly retained or excluded source asset,
with columns for asset, migration outcome/state and verification/test state.
Name each asset; group only those with the same outcome and state. Identify
passed, failed, blocked, skipped, unrun and inapplicable tests, with reasons
for failures and skips.

State whether provisioning is complete from the planned writes, read-backs and
approved exclusions. A failed smoke test leaves runtime verification incomplete,
not provisioning incomplete; do not call failed or unfinished provisioning
complete. List residuals and manual follow-up, and link the inventory, results
and any requested command record. Reporting itself does not trigger a fresh global
inventory or another approval round.
