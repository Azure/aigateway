---
description: Assess and migrate supported APIM V2 configuration with read-only inventory, deterministic local validation, and individually approved az aigateway changes.
argument-hint: <source-apim-resource-id> [<target-gateway> <target-resource-group> [target-region]] [--model-catalog-file <file>] [--apiops-artifact <path>] [--arm-template-file <file>]
---

# /aigateway:migrate

Follow `skills/migrate-ai-gateway/SKILL.md` and its bundled Python helper,
schemas, and capability catalog. Resolve `$ARGUMENTS` into the source service ID
first. A source-only invocation is a read-only feasibility assessment, not a
request to provision a destination. Require destination IDs/subscriptions only
for destination-bound planning or execution, and a region only for creation.

Check helper dependencies, the installed `az aigateway` command contract, and
the source service profile. Only BasicV2, StandardV2, and PremiumV2 sources are initially
enabled; V1 and AIGateway source profiles are reserved for future work.
Keep the source on `Microsoft.ApiManagement/service` and target the new
`Microsoft.ApiManagement/aigateways` resource type. Check installed new-RP
dispatch support, not help alone; never fall back to legacy writes. The CLI
selects the default workspace internally; do not pass `--workspace-name`.
The reviewed b22 supports model writes, workspace policies, telemetry exporters,
and post-create networking. Refresh evidence and approvals; help mentions alone
do not establish exposed arguments or service support.
Use the reviewed model-alias and gateway key capabilities for explicit callable
routes and admission. Import/sync Foundry models from selected accounts; attempt
approved Custom `/models` discovery, then fall back to an operator manifest when
needed. Follow `references/model-workflow.md` under the skill directory.
Use its explicit scoped selections for policy, network/connection, telemetry,
key lifecycle, MCP versions and multi-backend aliases. Preserve source behavior
ownership and scope decisions. Cost governance and payload capture are opt-in.
Do not enable `mcp update --failure-mode`, key rename, unreviewed OpenTelemetry
write fields, or external provisioning. Policy/network/lifecycle updates need
verified foundations and fresh destination evidence; credential-use approvals
remain separate from metadata reuse.
For model discovery, offer the helper's separately approved APIM named-value or
subscription-key control-plane read when no protected runtime binding exists.
Keep the selected secret in process memory, bind it to the exact catalog
endpoint/header, and preserve non-secret provenance. These scoped read-only
`listValue`/`listSecrets` actions use POST; they are not source writes or permission
to enumerate/copy secrets. Follow the model workflow rather than rejecting all
control-plane secret reads.
Keep legacy checkpoints read-only; create a fresh version-4 workspace when
destination-bound planning begins.

Collect redacted source evidence through read-only ARM GETs. Collect destination
evidence only when a target is supplied and its non-secret reads are authorized.
Use local APIOps/ARM evidence only after
explicit approval of its path and current content digest. Preserve coverage
gaps, provenance conflicts, policy inheritance, and every source behavior.

Inventory model-facing APIs, MCP tools, and required dependencies first.
Traditional APIs remain outside migration scope except as dependencies. Do not
ask about replacing the entire APIM instance. Honor any supplied AI subset;
otherwise ask about all discovered AI APIs versus a named subset only after
inventory and only if the choice affects assessment or planning.
Select finite model IDs and supported operations; do not import wildcard models,
wildcard destination operations or every APIM operation. Keep model catalogs
independent of destination selection. Foundry sync adds/updates explicit models,
preserves policies and stale registrations by default, and only proposes
removals separately. Never apply opaque native bulk sync.
For Foundry model planning, require authorized `collect-sync-preview` evidence
from the latest official, reviewed CLI and pass it with repeatable
`compile-plan --sync-preview-file`. Native dry-run owns missing/stale membership;
only selected create/unchanged registrations become granular TODOs. New
providers need a foundation plan first. If alias-bound stale models block the
native preview, retain the configuration and report the blocker; do not generate
a substitute local diff. Custom discovery remains independent of native sync.

For assessment, interpret the inventory and reviewed capabilities to conclude
what is migratable, migratable with changes, not supported by this adapter, or
undetermined. Distinguish moving all assessed AI traffic from a feasible subset,
not full APIM replacement. Preserve broad inventory coverage and gaps. Resolve
technical compatibility from evidence rather than asking the user to confirm it.
Ask an actual focused question when missing facts or scope decisions affect the
verdict; do not end with an unassigned "needs confirmation" checklist.

For requested executable planning, classify each item/behavior as ready,
needs-input, or cannot-import, then compile/validate the explicit resource graph
with mapping-owned behavior checks and individually approved resource TODOs using
the local helper. Initial needs-input mappings are scaffolding, not feasibility
findings. Missing coverage is not an acceptable residual.

For requested execution, obtain per-item consequential approval against the
current plan digest.
Execute only helper-validated granular `az aigateway` templates. Do not use
legacy native migration commands, source writes, destination REST writes,
unreviewed Foundry bulk/RBAC shortcuts, or implicit configuration replacement.
Resolve secrets at runtime, verify resource state and source behavior separately,
and stop dependents on any failed or inconclusive result.
Structural prerequisites use resource read-back; completion additionally requires
every owned source behavior to be verified across all its required resources.

Use protected atomic generations and drift checks for resume. Report completion,
accepted residuals, blockers, and manual actions accurately; never imply that
unsupported behavior or mere resource existence is a fully verified migration.
