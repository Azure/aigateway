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
custom deployment script or reconciliation engine. Bundled Python is only for
read-only collection and local evidence/document utilities.

- Assessment is not execution. A source-only feasibility request does not need
  a destination, deployment inventory, credentials for future writes or approvals.
- The APIM control plane defines what to recreate: endpoints, backends and their
  credentials, policies, identities, networking and diagnostics. The invocation
  authorizes reading all of it; mirror it by default instead of asking.
- Ask only about scope, destination, reuse of APIM-held backend credentials and
  source behavior the destination cannot represent; batch these into one round.
- Stay on the migration. Before confirmation, do not inspect backend resources
  or other subscriptions, probe runtimes or assess cost. Runtime behavior is for
  the approved smoke tests; only missing source configuration blocks an asset.
- Confirm the complete reviewed inventory once. It includes exact writes,
  external permissions, credential boundaries and bounded tests. Ask again for
  changed intent, not ordinary progress. Host permission controls still apply.
- Keep secrets out of persistent artifacts, logs and history. Read reused
  credentials only during approved execution; APIM subscriptions are not gateway keys.
- Provisioning, reachability and semantic equivalence are different claims.
  Report failed, blocked, skipped and unverified behavior explicitly.

## 1. Start read-only inventory

Locate this skill and protect the working evidence directory. Ask before
installing dependencies in an isolated Python environment outside the source tree:

```bash
python3 -m venv <protected-local-venv>
<protected-local-venv>/bin/python -m pip install -r skills/migrate-ai-gateway/requirements.txt
```

Below, `PYTHON` is that interpreter and `HELPER` is this skill's
`scripts/migration.py`. Output paths must be new; preserve prior evidence.

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
  accounts and credential boundaries. A model list or OpenAI-shaped endpoint
  does not prove operation support. Follow
  [model discovery and routing](references/model-workflow.md) when relevant.
- **MCP:** endpoints/versions, tools/schemas, routing/rewrites, auth, policies
  and access. Compare native MCP and OpenAPI sources (which need a REST contract)
  directly or through APIM; prefer direct when evidence supports it. Check
  operations and credentials; tool names and schemas may differ. Do not guess
  endpoint names, require an upstream ID without need, append templates to
  guessed URLs or equate an APIM 404 with lack of support.
- **Access and identity:** client admission separately from backend identity.
  Gateway-wide keys do not preserve per-API/product or anonymous admission.
  Shared backend credentials do not establish per-caller token propagation.
- **Policies and routing:** effective inheritance, counter identities, windows,
  conditions and response changes. Classic/v2 source rate-limit semantics can
  differ. Retries, circuit breakers and arbitrary XML are not automatically
  equivalent to destination routing or typed policies.
- **Networking and monitoring:** mirror the source topology, diagnostics
  destinations and payload logging; where the source has none, plan none.

Use these outcomes: **Inference only**, **Migratable**, **Migratable with changes**,
**Not supported by the current workflow**, or **Undetermined**. Explain the
destination mapping, semantic changes, what stays on APIM and the next technical
resolution. Separate automation gaps from platform limitations.

Before destination design, establish distinct complete source/destination ARM
IDs, explicit subscriptions, destination resource group/name and region if new.
Do not silently change Azure CLI defaults. Check selected commands against the
current official CLI release, relevant docs, help and actual `aigateways` dispatch.
The [capability reference](capabilities.json) records reviewed knowledge, not a
compiler allowlist or proof for future releases.

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
writes to work around missing support. Review relevant release changes once
during planning; do not rescan all help or download releases for each asset.
Do not upgrade during the approved execution sequence. External commands such
as `az role assignment create` need their own selected-command/scope review.

Source control-plane reads need no separate approval. A pre-confirmation
upstream call, secret read or inference is rarely needed; if the design truly
depends on one, name it in the scoping question.

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

Present the full readable review, exact commands and input files. Explain changed
authentication, paths, policy semantics, external writes, possible charges,
excluded behavior, test limits and rollback constraints. Resolve required
blockers before asking for confirmation; do not hide them by declaring a tiny
foundation phase a completed migration.

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
deployment, reconciliation or shell runner. Read-only helpers do not execute the
inventory. Keep an optional secret-free direct command record for reproduction.

At run start, check the approved revision/files, selected tenant/subscription,
CLI version and prerequisite availability. Reuse the collected evidence; refresh
only facts made stale or contradicted for the affected operation. Do not recollect
the entire source, models, release catalog or unrelated destination collections
before every asset or to render a report.

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
as such. Monitoring payload capture is opt-in. Destination key retrieval for an
approved smoke test requires an explicit secret source/use boundary.

## 7. Smoke-test, resume and report

Each asset requires configuration read-back. Run only the inventoried tests:

| Asset | Applicable bounded check |
| --- | --- |
| Model/alias | Minimal request on the exact approved operation/model, payload and budget |
| MCP | Initialize and tools/list; compare tools/schemas. No business-tool calls unless separately specified in the approved inventory |
| Identity/RBAC | Read back principal and exact role/scope; this does not prove inference |
| Monitoring | Exporter read-back; ingestion check only with the approved access/test |
| Policy/network | Relevant enforcement/connectivity check when feasible; a successful request is not policy equivalence |

Record passed, failed, blocked or skipped tests and non-secret evidence. Optional
tests may be skipped only with a reason; skipped required tests block verified
completion. Mark native TODOs done only after read-back and required checks pass.
Do not fabricate administrator attestation or call mere reachability equivalence.

On resume, use the approved inventory plus result receipts and native TODOs.
Reconcile interrupted assets by targeted reads; preserve completed assets.
Old engine checkpoints/approvals are historical evidence, not runnable authority.

Report provisioning separately from runtime verification, list residuals and
manual follow-up, and link the inventory/results/direct command record. Do not
call partial or unverified work a completed migration. Reporting itself does
not trigger a fresh global inventory or another approval round.
