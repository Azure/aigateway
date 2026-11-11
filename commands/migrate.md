---
description: Refine a reviewable APIM migration inventory, confirm it once, then execute direct Azure CLI commands with native per-asset TODOs and bounded smoke tests.
argument-hint: <source-apim-resource-id> [<target-gateway> <target-resource-group> [target-region]] [--model-catalog-file <file>] [--apiops-artifact <path>] [--arm-template-file <file>]
---

# /aigateway:migrate

Follow `skills/migrate-ai-gateway/SKILL.md`. Any APIM service tier is a valid
source. Bundled helpers collect read-only evidence and validate document structure;
they never apply the migration.

Resolve `$ARGUMENTS` into the source service ID first. A source-only invocation
is a read-only feasibility assessment: do not require a destination, region, or
provisioning approval. Require destination IDs and subscriptions only for
destination-bound planning or execution, and a region only for creation.

Mirror the APIM configuration by default, asking only about scope, credential
reuse and unrepresentable behavior, then produce
`migration-inventory.json` and a matching readable review. Show a per-asset
summary table in chat (result, Migrate / Migrate (with limitation) / Keep in
APIM, disposition), then offer review, approve and run, or cancel. Confirm the full
revision once, including exact commands, external prerequisites/permissions,
credential boundaries and bounded smoke tests. Create one native TODO per asset
or independently managed configuration, then run its direct Azure CLI commands.
Do not use custom deployment/reconciliation scripts or repeat global inventory
per asset. Changed intent requires an amended inventory and confirmation.

The source stays read-only; the destination is a separate
`Microsoft.ApiManagement/aigateways`. External Azure CLI writes are allowed only
when explicitly inventoried and confirmed. No source or destination REST writes,
implicit cutover or legacy migration commands. Read back each asset, reconcile
unknown outcomes before replay, and report test results, exclusions and blockers.
