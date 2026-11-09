---
name: manage-ai-gateway
description: Create, configure and operate Microsoft.ApiManagement/aigateways with the native Azure AI Gateway CLI. Use for explicit quickstart bootstrap, providers/models/aliases, MCP sources, policies, keys, identities, networking/private connections and telemetry. Not application integration or APIM migration.
license: MIT
metadata:
  author: Microsoft
  version: "1.1.0"
---

# Manage Azure AI Gateway

Help administrators through `/aigateway:create`, `/aigateway:manage`, or this
skill. Execute close to the native `az aigateway` CLI: resolve the task, read
affected state, make the smallest authorized change, and verify its result.
Questions and diagnostics remain read-only. References are task recipes,
not mandatory inventories or scripts to execute wholesale.

## Route by the result

| User intent | Required cues and acceptance | Reference |
| --- | --- | --- |
| Create or bootstrap a gateway | Explicit subscription, RG, region/name, optional tier; exact typed resource reaches healthy provisioning | [Lifecycle and quickstart](references/gateway-lifecycle.md) |
| Import Foundry or register a custom model | Selected existing account/deployment, finite registration scope, disclosed identity/RBAC effects; matching requested registrations/aliases | [Models and routing](references/models-and-routing.md) |
| Route across models | Exact alias/targets, common operations, priorities/weights; preserve policies and complete intended membership | [Models and routing](references/models-and-routing.md) |
| Add MCP/OpenAPI sources or authorize a connection | Exact server and source/protocol/auth contract; persisted endpoint membership, OAuth completion separately evidenced | [MCP](references/mcp.md) |
| Set token, request or cost controls | Compatible host, accounting scope, period and counter dimension; retained sibling policies and intended fields | [Policies](references/policies.md) |
| Manage client keys or outbound identity | Selected key/identity and access impact; secret-free read-back, rotation/retrieval only with approval | [Keys and identities](references/keys-and-identities.md) |
| Change public access, subnet or private connection | Existing network resources, approved connectivity effect and exact connection; bounded LRO/read-back, not just acceptance | [Networking](references/networking.md) |
| Configure export or diagnose operations | Existing destination, selected signals and capture decision; persisted configuration distinct from ingestion/runtime evidence | [Telemetry](references/telemetry-and-troubleshooting.md) |
| Check unsupported fields, IaC or product capabilities | Actual installed command/typed contract; explicit residual or owner prerequisite, no invented flags | [Capability coverage](references/activities-and-cli-coverage.md) |

The gateway owns its implicit `default` workspace, providers/registrations,
aliases, MCP ToolServers, inline policies, runtime keys and exporters.
Aliases reference models; they are not their ARM parents. Registering a model
does not provision its backend deployment. Outbound gateway identity and
incoming caller credentials are different. Saved export/policy/routing
configuration does not prove ingestion, enforcement or traffic distribution.

## Operating boundary

Manage **`Microsoft.ApiManagement/aigateways` and its own children** using only
official native `az aigateway` mutations. Do not target legacy
`Microsoft.ApiManagement/service`, rewrite resource IDs, create workspaces,
substitute `az rest`/generic writes or patch the extension to bypass a gap.

Two narrowly scoped bootstrap exceptions support the official quickstart:
create the **explicitly requested RG** with `az group create`, and use selected
Foundry onboarding only after scoped approval of its gateway identity and
**Foundry User** account-level role grant. Provider onboarding imports **every
current deployment**; confirm that scope, or use single-deployment onboarding
or low-level registration. Never infer bulk import/sync from "add a model".
See the references before either exception. Diagnostics authorize neither.

Foundry accounts/deployments, user-assigned identity resources, network/DNS/
private endpoints, connector resources, telemetry stores, provider/feature
registration, other role grants and Entra application/consent changes remain
external prerequisites. Do not provision them as hidden setup or cleanup.
IaC is separate work, not a guessed native CLI command.

APIM migration uses [migrate-ai-gateway](../migrate-ai-gateway/SKILL.md) with its
own deterministic helpers and approvals; consumption/application work uses
[use-ai-gateway](../use-ai-gateway/SKILL.md). Do not bypass those boundaries.

## Resolve only what is needed now

1. Reuse supplied facts. Resolve cloud/tenant, explicit subscription, RG and
   gateway for this task; select by identity/purpose, never list position.
   Use `--subscription`, not changed global defaults. Authenticate only if
   needed for the authorized management request.
2. Establish `az aigateway version` once per working context and inspect only
   task-specific `--help` when syntax/capability is uncertain. Use the official
   [CLI reference](https://github.com/Azure/aigateway/blob/main/cli/command-reference.md).
   Do not fetch releases or upgrade for every read/question. Resolve published
   `cli-v...` previews only for requested setup/upgrade or a demonstrated gap;
   installation/upgrade requires approval and official checksum verification.
   Keep the version stable during an approved change.
3. Bind the exact root below. Match returned `id`/`type` and all child/alias
   references to this gateway/default workspace. Never repair foreign IDs.
   Prefer `--ids` only where help exposes it. Name-only writes can dispatch to
   legacy services: inspect scoped same-name collisions and recheck the typed
   parent before those writes. Stop on collision, disappearance or uncertainty.
   Preflight is not atomic family binding; disclose that CLI limitation when
   concurrency cannot be excluded or exact binding is required.
4. Read only relevant resources/dependencies with native `show/list` and JSON.
   Complete supported pagination before absence/dependency claims; denied
   reads and failed pages remain explicit gaps, not empty inventories.
   A diagnostic does not require every resource family.

```bash
SUBSCRIPTION="<subscription-id>"
RG="<resource-group>"
GATEWAY="<gateway-name>"
GATEWAY_ID="/subscriptions/$SUBSCRIPTION/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY"

az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
```

For creation, authoritative absence of the selected new root is expected,
not permission to overwrite another resource.

## Authorization and preservation

Explicit create/update intent authorizes routine changes in the named scope;
do not ask again for ordinary metadata edits. Explain the desired-state diff,
preserved settings, dependencies, cost and verification before execution.

Obtain immediate, specific confirmation for deletion/stale-sync removal,
overwrite/complete-collection replacement, policy removal/weakening, key
creation/state/expiry/replacement/rotation, identity or access changes,
Foundry onboarding role grants, networking/private endpoint decisions, secret
retrieval, OAuth initiation and payload capture. Pass `--yes` only after the
relevant confirmation and only where exposed. A diagnostic authorizes none.

- Preserve unrelated properties, tags, policies, routing, source membership
  and credentials. Inspect duplicate policy kinds before consolidating setters.
  JSON inputs do not interpolate environment variables.
- Keep secrets in protected process memory or approved protected files outside
  source control. Never output/log values or put them in history/replay scripts;
  disable tracing/debug/verbose for sensitive operations. Redaction markers
  are not credentials. Prefer secret-preserving updates; disclose implicit
  ToolServer secret reads during endpoint editing.
- Use supported conditional writes. Conflicts need fresh state and a new
  decision, not blind retry/wildcard overwrite. Disclose unavailable atomic
  protection. Multi-resource writes are sequential, not transactional.
- Failed prerequisites stop dependent changes. Reconcile timeout/transport
  failure and partial success against exact current state before retrying.
  Do not automatically roll back earlier successes or replay sync/rotation.

## Execute and verify

Load only the affected domain recipe, refresh state immediately before the
write, and use supported previews such as sync `--dry-run` when applicable.
Use bounded native `wait` where available, otherwise bounded read-back.
Acceptance is not completion; deletion requires authoritative absence, not
permission denial. Verify intended fields **and preserved siblings**.

Report verified IDs/configuration, partial outcomes, unknown effects and
owner prerequisites. Runtime model/MCP calls and telemetry queries need
separate authorization and the [consumer workflow](../use-ai-gateway/SKILL.md);
management reads do not prove inference, tool availability or enforcement.
Retain secret-free provisioning commands in an approved location when a
replay artifact is requested; keep destructive/access confirmation stops.

The reference evidence baseline is CLI `1.0.0b22`; installed task-specific
help takes precedence for command availability, not unmeasured runtime claims.
