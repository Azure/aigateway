# Azure AI Gateway CLI

Use `az aigateway` to create gateways and manage model aliases, providers,
MCP servers, policies, identities, networking, and client keys.
The CLI is in **public preview**. This guide and the
[searchable command reference](command-reference.md) cover release **1.0.0b22**.
The CLI implementation is distributed as a released Azure CLI extension,
not built from this plugin checkout.

## Install

Install [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
**2.75.0 or later** first. Then open the
[CLI releases list](https://github.com/Azure/aigateway/releases) and choose
the newest published `cli-v...` release, including previews. GitHub's
`releases/latest` endpoint can omit previews.

Download that release's `aigateway-<version>-py3-none-any.whl` asset and
compare its SHA-256 with the asset's published digest **before installing**.
The following examples install the reviewed `1.0.0b22` release. If a newer
release is available, use its wheel URL and its own published digest instead;
do not reuse this checksum for another version.
An agent must obtain approval before installing or upgrading a tool.

**Bash**

```bash
WHEEL="aigateway-1.0.0b22-py3-none-any.whl"
curl -fL --output "$WHEEL" \
  "https://github.com/Azure/aigateway/releases/download/cli-v1.0.0b22/$WHEEL" || exit 1
printf '%s  %s\n' \
  '3363ee0efde6ec22f445fd11f2b6b625867c1ab49b8ab76108f6e1bfa920060a' "$WHEEL" \
  | sha256sum --check || exit 1
az extension add --source "$WHEEL" --upgrade
```

On macOS without `sha256sum`, use `shasum -a 256 --check` instead.

**PowerShell**

```powershell
$wheel = "aigateway-1.0.0b22-py3-none-any.whl"
Invoke-WebRequest -Uri "https://github.com/Azure/aigateway/releases/download/cli-v1.0.0b22/$wheel" `
  -OutFile $wheel -ErrorAction Stop
$expected = "3363ee0efde6ec22f445fd11f2b6b625867c1ab49b8ab76108f6e1bfa920060a"
if ((Get-FileHash $wheel -Algorithm SHA256).Hash -ne $expected) {
  throw "CLI wheel checksum mismatch; do not install."
}
az extension add --source $wheel --upgrade
if ($LASTEXITCODE -ne 0) { throw "CLI extension installation failed." }
```

Verify the installation without signing in to Azure:

```bash
az aigateway version
az aigateway --help
```

For this release, `version` reports extension `aigateway`, version
`1.0.0b22`, and API `2025-09-01-preview`. Do not substitute legacy
`az ai-gateway`, a source build, or locally patched installed modules.

## Quickstart

### 1. Create a gateway in an existing resource group

You need preview access, a supported region, and permission to create the
gateway in the selected subscription/resource group. Ask the subscription
owner to prepare provider registration and other prerequisites.
Connected services and model calls may incur charges.

These examples use Bash. Replace the placeholders and stop on any error.
Keep the explicit subscription when copying commands.

```bash
az login
SUBSCRIPTION="<subscription-id>"
RG="<existing-resource-group>"
GATEWAY="<globally-unique-gateway-name>"
LOCATION="<supported-region>"

az aigateway create --subscription "$SUBSCRIPTION" \
  -g "$RG" -n "$GATEWAY" --location "$LOCATION"
az aigateway show --subscription "$SUBSCRIPTION" \
  -g "$RG" -n "$GATEWAY" -o json
```

Check the returned type is `Microsoft.ApiManagement/aigateways` and
provisioning has succeeded before adding assets. This is not a legacy
API Management `service` resource.

### 2. Register a public MCP server

The [Microsoft Learn MCP server](https://learn.microsoft.com/training/support/mcp)
needs no backend credential. Put the following endpoint array in
`endpoints.json`:

```json
[
  {
    "kind": "mcp",
    "namespace": "learn",
    "mcp": {
      "transport": "streamableHttp",
      "url": "https://learn.microsoft.com/api/mcp"
    }
  }
]
```

```bash
az aigateway mcp create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n learn --endpoints @endpoints.json
az aigateway mcp show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n learn -o json
```

Here `--name` identifies the MCP registration; `--gateway-name` identifies
its parent. Registration does not deploy the backend or test a tool call.

### 3. Publish models through aliases

For model traffic, use an existing backend deployment and prepare its access
grants. Register the provider, register the selected model, then create an
alias pointing to that registration. **Clients call the alias name, not the
backend deployment name.** A model registration without an alias is not a
published model route.

Follow the [provider, model, and alias examples](command-reference.md#models-and-aliases).
Those low-level paths keep external role grants separate. The convenience
`model-provider create --foundry-resource-id` path instead imports every
deployment and enables gateway identity/grants **Foundry User** on the
account; use it only when that broader change is intended and authorized.

### 4. Connect an application

Prefer inbound **Microsoft Entra ID** with a gateway data-plane role for the
caller. Gateway managed identity authenticates the separate **outbound**
connection to models/tools; attaching it does not authorize the caller.
Optional gateway API keys grant broad runtime access and need protected
storage and staged rotation.
See [caller authentication and outbound identity](../skills/manage-ai-gateway/references/keys-and-identities.md).

Use the [coding-agent plugin](../README.md#coding-agent-plugin) to discover
the published aliases or MCP endpoints and integrate the intended protocol.
A successful management read is not a model or tool invocation test.
Authorize any runtime test separately, especially for tools with side effects.

## Next steps

Use [the reference](command-reference.md) to find commands and configuration
examples; use task-specific `--help` to check the installed version's options.
Keep the CLI version stable during an approved change.

For an existing APIM workload, follow the
[APIM migration skill](../skills/migrate-ai-gateway/SKILL.md) for its supported
scope, prerequisites, validation, and approval requirements.

## Removal

`az extension remove --name aigateway` removes the local extension only.
To delete a gateway, inspect its consumers first and use
`az aigateway delete --subscription "$SUBSCRIPTION" -g "$RG" -n "$GATEWAY"`
only after confirming the deletion. Do not delete the shared resource group.
Gateway registration removal does not delete external model deployments,
tool backends, or their role assignments.
