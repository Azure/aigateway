---
name: manage-ai-gateway
version: 1.0.0
description: Create, configure, administer, troubleshoot, and operate Microsoft.ApiManagement/aigateways resources with the official Azure AI Gateway CLI. Manage providers, models, aliases, MCP sources, policies, client keys, managed identities, networking, private endpoint connections, and telemetry. Use for administrator tasks, not application integration or APIM migration.
---

# Manage Azure AI Gateway

Invoked as `/aigateway:manage-ai-gateway`, `/aigateway:create`, or
`/aigateway:manage`. Help administrators understand, configure, and operate
a gateway using the native `az aigateway` CLI.

## Platform model

| Object | Responsibility and relationships | Reference |
| --- | --- | --- |
| Gateway | Resource identity, provisioning, tags, tier, managed identities, ingress/outbound networking, and gateway-side private connections | [Lifecycle](references/gateway-lifecycle.md), [networking](references/networking.md) |
| Default workspace | Implicit container for registered assets, shared policies, and telemetry exporters; the current CLI supports only `default` | [Policies](references/policies.md), [telemetry](references/telemetry-and-troubleshooting.md) |
| Model provider | Backend endpoint and authentication configuration used by its model registrations; the external account is not owned by the registration | [Models and routing](references/models-and-routing.md) |
| Registered model | Deployment metadata, supported protocol/endpoints, and model-local policies; registration does not create the underlying deployment | [Models and routing](references/models-and-routing.md) |
| Model alias | Stable callable name and routing across registered models; an alias is not their ARM parent | [Models and routing](references/models-and-routing.md) |
| MCP ToolServer | Gateway endpoint federating backend sources, with source credentials, protocol settings, and compatible policies | [MCP](references/mcp.md) |
| Policy instance | Inline configuration on a workspace or asset; its type, attachment, accounting scope, and caller dimensions determine its effect | [Policies](references/policies.md) |
| Caller authentication / gateway identity | Prefer inbound Entra tokens with caller roles; optional API keys grant gateway-wide access. Gateway managed identities separately authenticate outbound access | [Authentication and identities](references/keys-and-identities.md) |
| Telemetry exporter | Signal endpoints, export authentication, attributes, and payload capture; the destination and its access grants remain external | [Telemetry](references/telemetry-and-troubleshooting.md) |

## Operating boundary

Manage **`Microsoft.ApiManagement/aigateways` and its own children** in the
implicit default workspace. Do not manage a legacy
`Microsoft.ApiManagement/service` destination, rewrite its ID, or create a
workspace.

All gateway mutations use official native `az aigateway` commands. No
`az rest`, generic resource writes, HTTP/SDK administration, legacy
`az ai-gateway`, patched extension, or local CLI implementation substitutes.
[Capability coverage](references/activities-and-cli-coverage.md) distinguishes
resource-provider support, native argument availability, and known gaps;
command visibility or free-form JSON alone establishes neither applicability
nor runtime behavior.

Supporting resources must already exist: resource groups, Foundry
deployments, user-assigned identities, subnets, private endpoints/DNS,
source connectors/connections, and telemetry destinations. Authorized core
Azure CLI reads and authentication may establish prerequisites. Their
creation, provider/feature registration, source administration, and Entra
application changes remain outside this skill's mutation scope.

Role assignments needed for the outcome belong in the plan even on external
destinations. They are the exception to the mutation boundary: follow
[access planning and grant execution](references/keys-and-identities.md#grant-caller-or-destination-access),
including authority checks and confirmation of each exact assignment.
Confirmation matters because a grant changes security outside the gateway's
ownership and outlives it. Prefer separately approved access changes over
the bundled onboarding described in [provider configuration](references/models-and-routing.md#foundry-provider).

APIM migration belongs to
[`migrate-ai-gateway`](../migrate-ai-gateway/SKILL.md) or
`/aigateway:migrate`, with its separate capability and approval gates.
Developer application integration and scaffolding are outside this skill.

## Prerequisites and target resolution

Match preparation to intent: answer conceptual questions from the relevant
references; use the steps below for diagnostics or changes on a gateway.
Check time-sensitive support when the question requires it.

1. Reuse supplied identifiers and relevant context. Resolve the cloud, tenant,
   subscription, resource group, and gateway needed now. Select resources
   by identity and purpose, not by their position in a list.
2. Inspect local `az aigateway version`, task-specific help, the
   [official reference](https://github.com/Azure/aigateway/blob/main/cli/command-reference.md),
   and [installation guide](https://github.com/Azure/aigateway/tree/main/cli).
   Resolve the newest published `cli-v...` release, including previews,
   from the [release list](https://github.com/Azure/aigateway/releases);
   `/releases/latest` alone omits previews. Installation/upgrade requires
   approval and the official checksum-verified package. Keep the tool
   version stable during an approved change.
3. Pass the subscription explicitly rather than relying on the CLI default,
   which other sessions share. Confirm returned IDs are in the intended
   scope: a command can resolve names against the default regardless of
   its selector (`--debug` shows the request URL). If so, the simplest
   remedy is usually to switch the default with the user's consent and
   restore it afterwards; ask before engineering a workaround or blocking.
   Authenticate with `az login` if needed. Read failures and permission
   denials remain explicit gaps, not empty inventories.
4. Establish the exact root:
   `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/aigateways/<name>`.
   Match an existing target's returned ID/type to this root. Child IDs and
   alias targets must belong to this gateway/default workspace; a foreign
   response cannot be repaired by re-anchoring its ID.
5. Prefer exact `--ids` only where help exposes it. Several creates,
   identity changes, and telemetry writes require name selectors whose
   dispatch can fall back to legacy `service` resources. Inspect scoped
   inventory for same-name family collisions and recheck the typed parent.
   Stop on collision, disappearance, or uncertain dispatch. A name preflight
   is not atomic family binding; if concurrent lifecycle changes cannot be
   excluded or exact binding is required, report the CLI limitation.
6. Discover the resources relevant to the task, with JSON output and complete
   supported pagination before absence/dependency claims. A simple diagnostic
   does not require inventorying every resource family.

References use these resolved Bash variables:

```bash
SUBSCRIPTION="<subscription-id>"
RG="<existing-resource-group>"
GATEWAY="<gateway-name>"
GATEWAY_ID="/subscriptions/$SUBSCRIPTION/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY"

az aigateway version
```

For an existing target, read its root:

```bash
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
```

For creation, inspect scoped inventory first and read the new root after
creation; its prior absence is expected, not permission to overwrite an
existing same-name resource.

## Derive the configuration

1. Establish the result that matters: affected resources/traffic, intended
   behavior, and relevant constraints such as accounting, access, routing,
   cost, or availability. Resolve only missing choices that change the result.
2. For diagnostics or changes, read current configuration and relevant
   dependencies. Distinguish a missing setting from missing evidence of its
   effect.
3. Compose supported mechanisms for the outcome; it may need several objects
   or policy instances, or existing configuration may suffice. Start with the
   task reference and follow links for shared controls; use the
   [platform model](#platform-model) rather than inferring support from similar
   commands or labels. Describe objects, policies and settings in gateway
   product terms, mapped to CLI/API names. Include portal behavior only when
   it affects the outcome or a capability boundary.
4. For changes, compare desired and current state. Propose the smallest
   changes, unchanged configuration, and prerequisites; order changes by
   dependency, reusing satisfied prerequisites rather than resource-list order.
   When alternatives differ in behavior, ownership, disruption, or cost,
   recommend the simplest suitable option and obtain the necessary decision.
5. Choose verification appropriate to the claim: persisted fields, completed
   provisioning, or separately authorized runtime evidence. State any part
   the native CLI cannot establish.

## Authorization and preservation

Explicit intent authorizes routine creates and updates within the specified
scope; ordinary metadata edits do not need repeated approval. Explain planned
changes, dependencies, and required confirmations before execution.

Obtain immediate, specific confirmation for deletion, stale-sync removal,
overwrite/complete-collection replacement, policy removal or weakening,
key creation/state/expiry/replacement/rotation, identity changes, role
assignments, network access changes, and private endpoint decisions. Secret retrieval, OAuth
initiation, and payload capture also require explicit authorization.
A diagnostic request authorizes none of these. Pass `--yes` only after
the relevant confirmation and only where the command exposes it.

- Preserve unrelated properties, tags, policies, source membership,
  credentials, and routing settings. Inspect duplicate policy kinds before
  using setters that consolidate them.
- Keep secrets in protected memory or approved protected files outside source
  control; never put values in command history, agent output, logs, or replay
  scripts. JSON files do not expand environment variables. Disable tracing
  and CLI debug/verbose output for sensitive operations.
- Redaction markers are not credentials. Prefer secret-preserving native
  update paths rather than rebuilding secret-bearing objects from redacted
  reads. Explain implicit ToolServer secret reads during endpoint editing.
- Use supported conditional-write paths. A conflict requires fresh reads and
  a new decision, not a blind retry or wildcard overwrite. Disclose where
  atomic concurrency protection is unavailable.
- Multi-resource changes are sequential, not transactional. Stop dependent
  actions after failure; earlier successes are not automatic rollback targets.

## Create a gateway

Use [gateway lifecycle](references/gateway-lifecycle.md) for existing-RG
creation, selected region/name, optional tier/tags/identity/subnet, and
provisioning. Only requested settings and assets belong in the change.
Verify the exact created resource and readiness, then retain secret-free
reproducible provisioning commands.

## Configure gateway assets

Load only the task and shared-control references needed for the outcome,
using the platform model above. Cross-resource dependencies inform ordering
and prerequisites, not permission to configure additional resources.
Unsupported requirements remain explicit gaps, not approximated features.

## Operate

1. Refresh affected resources and dependencies immediately before a mutation.
   Use only advertised previews, such as provider sync `--dry-run`.
2. Execute the smallest supported change and capture nonsecret per-resource
   outcomes. Failed prerequisites stop dependent actions.
3. Use matching native `wait` conditions with bounded timeout/interval where
   available; otherwise perform bounded read-back. Acceptance is not completion.
4. Verify the intended fields and preserved siblings on the exact resource.
   Deletion requires authoritative absence, not a denied read. Allow for
   propagation between management configuration and runtime behavior.
5. Reconcile timeout, transport failure, or partial success through current
   state before retrying. Rotations, creates, deletes, and whole syncs are
   not safe to repeat blindly.
6. Report verified configuration/IDs, unverified effects, unsupported work,
   and precise owner prerequisites. Saved state does not establish model
   behavior, tool availability, enforcement, connectivity, or telemetry delivery.

Provisioning output includes an approved-location replay script with explicit
scope, necessary inputs, preserved-state decisions, and verification commands.
Use `set -euo pipefail`, keep secret values out, retain confirmation stops for
destructive replay, and reconcile existing state before replaying creates.
Repository files and ignore rules require approval before being changed.

## Keeping the references current

Maintain each contract or procedure in one home. The platform model links to
the owners: policies covers compatibility, attachment, accounting and writes;
keys and identities covers access planning and grants. This workflow owns
common safeguards, replay and reporting; the [capability inventory](references/activities-and-cli-coverage.md)
owns the native surface index, reviewed baseline and dated support evidence.
Link to the owner at the task step that needs it; keep only local integration
detail to avoid competing copies.

A CLI release does not automatically require a skill rewrite. Compare the
task's commands and relevant release changes with the recorded baseline.
Update affected command recipes and capability evidence when flags, schemas,
resource dispatch, or behavior change; update this workflow only when those
changes alter the operating model or safeguards. Do not treat newer help as
proof that a previously unsupported mutation is safe.

The migration helper has a separate, stricter reviewed capability profile.
A new CLI version must pass that profile's review and fresh plan approvals
before migration writes; this management guidance does not bypass that gate.
