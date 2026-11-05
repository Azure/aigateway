---
name: manage-ai-gateway
version: 2.0.0
description: Create, configure, and operate the AI Gateway tier in Azure API Management with az aigateway. Use for authorized administrators managing gateways, model providers and models, MCP servers, model policies, API keys, identities, or networking. APIM migration is separately gated.
---

# Manage the AI Gateway tier in Azure API Management

> Invoked as `/ai-gateway:manage-ai-gateway` when installed via the plugin.
> Also used by `/ai-gateway:create` and `/ai-gateway:manage`.

Use this skill for an authorized administrator or platform engineer changing
gateway resources. For developers consuming existing models or tools, use
`skills/use-ai-gateway/SKILL.md` instead. For APIM migration, use
`skills/migrate-ai-gateway/SKILL.md` and its local inventory/validation helpers.
Do not bypass its capability, validation, or approval gates through this workflow.

## Prerequisites and target resolution

The supported interface is `az aigateway`, documented in the external
[Azure/aigateway CLI guide](https://github.com/Azure/aigateway/tree/main/cli) and
[command reference](https://github.com/Azure/aigateway/blob/main/cli/command-reference.md).
There is no locally maintained CLI implementation or installer here.
Do not use the older `az ai-gateway` command group
or replace unsupported commands with guessed ARM calls.

1. Check `az aigateway version` against the newest published `cli-v...` release
   in Azure/aigateway, including previews; GitHub's `/releases/latest` omits
   previews. If missing or stale, follow the external guide and obtain approval
   to install the exact checksum-verified release wheel. Never substitute a
   local build, patched installation or older package. Then check `az account
   show`; if unauthenticated, ask the user to run `az login`.
2. Confirm the subscription, resource group, gateway name, and requested scope.
   Never guess a subscription or change global CLI defaults. Use an explicit
   `--subscription` when needed.
3. Check the installed command's `--help` before proposing exact arguments.
   Top-level gateway commands use `--name`; child resources generally use
   `--gateway-name` for their parent and `--name` for the child. Individual
   model commands also use `--provider-name`. Inspect each command's help for
   exceptions, including identity and network commands.
4. Inspect existing state with the matching `show` or `list` command. An
   authorization, network, or transient failure is not evidence of absence.

New gateways use `Microsoft.ApiManagement/aigateways`; the CLI also supports
existing legacy `Microsoft.ApiManagement/service` AI Gateway resources.
Preserve the returned type/ID and check support for that resource family rather
than rewriting IDs or assuming a help-visible legacy command supports new-RP.
Treat new CLI features as requiring contract review, not automatic permission
to mutate resources or change an approved plan.

## Safety and execution rules

- Explain the intended changes and possible costs, then obtain approval before
  executing mutations. Confirm consequential operations immediately before
  deletion, key regeneration, identity removal, overwrites, or network changes.
- Show the smallest command sequence that achieves the request. Inspect
  configuration files and JSON arguments; do not invent endpoints, policies,
  authentication settings, role assignments, or resource names.
- Keep secrets out of responses, logs, command previews, shell history, and
  committed files. Use protected runtime inputs supported by the installed
  command. Never persist an expanded secret-bearing command.
- `api-key list` and `show` inspect metadata. Use `list-secrets` only for an
  explicitly requested credential retrieval; never for routine inventory.
- Do not suppress confirmation with `--yes` unless the exact action has already
  been approved. Never bypass an ETag conflict or treat a failed command as
  success.
- Verify each mutation with its result and the corresponding `show` or `list`.
  Report partial failures explicitly and stop dependent changes.

## Create a gateway

Collect the gateway name, existing resource group, and supported Azure region.
Confirm permissions, preview availability, intended changes, and possible costs
using `cli/README.md`. Create a resource group only if requested. Inspect an
existing gateway before considering any update; do not overwrite it as creation.

```bash
az aigateway create \
  --resource-group <resource-group> --name <gateway> --location <region>
az aigateway show \
  --resource-group <resource-group> --name <gateway> --output json
```

Check `properties.provisioningState`; command submission alone is not proof of
successful provisioning.

## Configure gateway assets

### Model providers and models

Inspect providers and models before proposing changes:

```bash
az aigateway model-provider list \
  --resource-group <resource-group> --gateway-name <gateway>
az aigateway model list \
  --resource-group <resource-group> --gateway-name <gateway>
```

For an existing Foundry AI Services or Azure OpenAI account with deployments,
the documented import path is:

```bash
az aigateway model-provider create \
  --resource-group <resource-group> --gateway-name <gateway> \
  --name <provider> --foundry-resource-id <account-resource-id>
```

This imports every current deployment, enables the gateway's system-assigned
identity, and grants it the Foundry User role on the account. Explain and obtain
approval for these side effects, including the RBAC scope, before running it.
It does not create backend deployments. Inspect the import result for partial
failures, then list models with `--model-provider <provider>`.

For other provider types or individual models, use the installed
`model-provider` or `model` command's help. Do not reuse the legacy
`--resource-name`, `--no-sync`, or `--aliases` arguments. Provider synchronization
and model-alias management are not documented in the current public command
reference; report that limitation instead of inventing equivalents.

### MCP tool servers

Inspect `mcp list` or `mcp show` first. Review the endpoint configuration and
authentication requirements, then obtain approval:

```bash
az aigateway mcp create \
  --resource-group <resource-group> --gateway-name <gateway> \
  --name <server> --endpoints @endpoints.json
```

The file contains an endpoint array, not a URL string. Use the shape in the
external CLI guide and the latest installed help. Use `mcp source add|list|remove` for
individual sources and inspect `mcp authorize --help` for OAuth authorization.
Do not claim authorization succeeded until the command completes successfully.

### Model policies

Current documented policy commands are scoped to a model:

```bash
az aigateway model policy list \
  --resource-group <resource-group> --gateway-name <gateway> \
  --provider-name <provider> --name <model>
```

Use `model policy set`, `set-token-limit`, or `set-content-safety` with the
user's intended values and the external CLI command reference. Inspect
`model policy remove --help` and obtain explicit approval before removal.
Do not apply example thresholds as defaults or claim these policies govern
other models, MCP servers, or direct backend calls. Generic policy import and
policy translation are not documented current CLI capabilities.

### API keys

Use `api-key create|show|list|delete` for key resources. Confirm the key name,
slot, and client impact before `api-key regenerate`; inspect its installed
help for the exact arguments. Credential rotation can break clients until they
are updated. Do not include returned secret values in the report.

### Managed identities and networking

Use `identity show` before and after `identity assign` or `identity remove`.
Identity assignment alone does not establish backend RBAC access; confirm
roles and scopes separately.

Use `network show` before `network update`, and inspect the installed help for
public-access and outbound-network options. Explain connectivity effects and
obtain explicit approval before changing access. Use
`network private-endpoint-connection list|show` before approving, rejecting, or
deleting a connection, and obtain approval for each consequential change.

Telemetry-exporter management is not documented in the current public CLI.
Report the limitation and refer to the AI Gateway documentation or portal;
do not substitute the legacy command or invent a REST write.

## Operate

Use top-level `list|show|update|delete|wait` for gateway lifecycle operations and
the documented nested commands for assets. Confirm installed syntax, inspect
state, obtain approval, execute the smallest change, and verify afterward.
Gateway deletion removes registrations and retains an API Management soft-delete
record; explain that its name may not be immediately reusable. Do not delete a
resource group as a shortcut.

## Completion

Report the subscription, resource group, gateway ID, resources changed or left
unchanged, verification state, and any pending authorization or RBAC work.
Distinguish read-only findings, attempted changes, verified changes, and blocked
operations. Never include credentials or secret-bearing configuration.
