# AI Gateway CLI

Create an AI Gateway, register model providers and MCP servers, and manage
policies, keys, identities, and networking from your terminal with `az aigateway`.

> **Public preview**: commands and behavior may change before general availability.
> Current extension release: **1.0.0b22**.

[Install](#install) | [Quickstart](#quickstart) | [Command reference](command-reference.md) | [AI Gateway documentation](https://aka.ms/aigateway/docs)

## Install

Install [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
first (`az --version`). The extension declares Azure CLI **2.75.0 or later**;
using a current Azure CLI release is recommended.

**Bash (macOS / Linux)**

```bash
curl -fsSL https://aka.ms/aigateway-cli-install | bash
```

Requires `curl` and a SHA-256 utility (`shasum` or `sha256sum`, normally
preinstalled).

**PowerShell (Windows / macOS / Linux)**

```powershell
irm https://aka.ms/aigateway-cli-install-ps | iex
```

PowerShell does not need `curl`. Neither installer needs Git, GitHub CLI, a
separate Python installation, or an Azure login. Both need HTTPS access and
permission to write to your Azure CLI extension directory.

The installers download the published release, verify the wheel's SHA-256,
and install or upgrade the `aigateway` extension. To inspect a script before
running it, see [install.sh](install.sh) or [install.ps1](install.ps1).

Running an installer again reinstalls the pinned release, including when the
same version is already present, so a stale local build is replaced. Download
and checksum failures leave the existing extension untouched. Once the wheel
is verified, a same-version installation is removed before reinstalling; if
installation fails, correct the reported error and rerun the installer.

### Verify

```bash
az aigateway version
az aigateway --help
```

`version` reports `extensionName: aigateway`, `extensionVersion: 1.0.0b22`,
and `apiVersion: 2025-09-01-preview`. Neither command needs an Azure login.

## Quickstart

Create a gateway, then register the public
[Microsoft Learn MCP server](https://learn.microsoft.com/training/support/mcp),
[add models through a provider](#3-add-models-through-a-provider), or both.
The model path also shows how to [set common policies](#4-set-model-policies).
Then [test the gateway](#5-test-the-gateway) with `curl` or PowerShell.
These examples use **Bash**; replace the placeholder values before running them.
The MCP path needs no model deployment or GitHub credential.

### Before using Azure resources

You need an Azure subscription with access to the AI Gateway preview, a supported
region, and permission to create resources in the subscription or target resource
group (for example, Contributor at the appropriate scope). The
`Microsoft.ApiManagement` resource provider must be registered in the subscription;
ask your subscription administrator if registration is needed. See the
[AI Gateway documentation](https://aka.ms/aigateway/docs) for availability.

**This tutorial creates Azure resources.** The AI Gateway tier is currently free
during public preview; connected services and other Azure resources may incur
charges. Use a new, dedicated resource group and review pricing before proceeding.

### 1. Sign in and create a gateway

Create a gateway in your subscription and save `group` and `aigateway` defaults
with `az configure` so you don't have to repeat `-g` and `--gateway-name` on
every command.

```bash
az login

RG="rg-aigateway-quickstart"
LOCATION="eastus2"
GATEWAY="aigw-quickstart-$RANDOM"

az group create --name "$RG" --location "$LOCATION"
az aigateway create --resource-group "$RG" --name "$GATEWAY" --location "$LOCATION"
az configure --defaults group="$RG" aigateway="$GATEWAY" output=json
```

Creation waits for provisioning to finish. The gateway is an Azure AI Gateway
resource (`Microsoft.ApiManagement/aigateways`); omitting `--sku` lets the
service apply its default SKU (`Standard`), or pass
`--sku Standard|Premium|Consumption` on `create` and `update`.

### 2. Register an MCP server

The Learn endpoint does not require backend authentication. This command adds a
registration to your gateway; it does not deploy a new MCP server.

```bash
az aigateway mcp create \
  --name learn \
  --endpoints '[{"kind":"mcp","namespace":"learn","mcp":{"transport":"streamableHttp","url":"https://learn.microsoft.com/api/mcp"}}]'

az aigateway mcp list --output table
az aigateway mcp show --name learn
```

Use the [coding-agent plugin](../README.md#coding-agent-plugin) to build an
application that consumes the gateway, or explore more commands in the
[command reference](command-reference.md).

### 3. Add models through a provider

For this path, you need an **existing Foundry AI Services or Azure OpenAI
account with model deployments**. You need permission to read the account and
its deployments, update the gateway, and create role assignments on the account.

The commands below look up your Foundry account by name across the subscription,
import **every current deployment** into a gateway provider, enable the
gateway's system-assigned identity with the **Foundry User** role on the
account, and publish a callable model alias for each imported deployment.

```bash
# List Foundry accounts in your subscription
az resource list --resource-group= --resource-type Microsoft.CognitiveServices/accounts \
  --query "[?kind=='AIServices'].{Name:name, ResourceGroup:resourceGroup, Location:location}" -o table

# Set your Foundry account name, import its models, and publish default aliases
FOUNDRY_ACCOUNT="<foundry-account-name>"
FOUNDRY_RESOURCE_ID="$(az resource list --resource-group= \
  --resource-type Microsoft.CognitiveServices/accounts \
  --name "$FOUNDRY_ACCOUNT" --query "[0].id" -o tsv)"

az aigateway model-provider create \
  --name foundry-prod \
  --foundry-resource-id "$FOUNDRY_RESOURCE_ID"
az aigateway model list --provider-name foundry-prod | az aigateway model-alias create
```

### 4. Set gateway policies

Apply a gateway-wide token limit and content-safety baseline across models in
the default workspace. The example allows **10,000 tokens per minute per
identity** and sets content safety severity to **Medium** for hate, self-harm,
sexual, and violence categories.

```bash
az aigateway policy set \
  --token-limit 10000 --token-period minute --token-counter-key Identity \
  --content-safety Medium

az aigateway policy list
```

You can also set policies on individual models with `az aigateway model policy set`.
See [common model policies](command-reference.md#common-model-policies) to change
one policy at a time.

### 5. Test the gateway

Retrieve the gateway hostname, an active runtime key, and the first published
model alias, then send a Chat Completions request. Model calls can incur
inference charges.

**Bash / curl** (uses `jq` to print the reply text):

```bash
AI_GATEWAY_URL="https://$(az aigateway show --query properties.frontend.defaultHostname -o tsv)"
KEY_NAME="$(az aigateway api-key list --query "[?properties.state=='active'] | [0].name" -o tsv)"
test -n "$KEY_NAME" || KEY_NAME="$(az aigateway api-key create --name default --display-name "Default key" --state active --query name -o tsv)"
if ! AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets -n "$KEY_NAME" --query primaryKey -o tsv)"; then
  echo "Failed to retrieve the API key secret." >&2
  exit 1
fi
test -n "$AI_GATEWAY_API_KEY" || { echo "No API key secret was returned." >&2; exit 1; }
MODEL="$(az aigateway model-alias list --query "[?contains(properties.supportedEndpoints, '/openai/v1/chat/completions')] | [0].properties.aliasName" -o tsv)"
test -n "$MODEL" || { echo "No chat completions model alias was found." >&2; exit 1; }

curl -sS "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "api-key: $AI_GATEWAY_API_KEY" \
  -d '{"model":"'"$MODEL"'","messages":[{"role":"user","content":"Write a one-sentence status update."}]}' \
  | jq -r '.choices[0].message.content'
unset AI_GATEWAY_API_KEY
```

**PowerShell / `irm`**:

```powershell
$GatewayUrl = "https://$((az aigateway show --query properties.frontend.defaultHostname -o tsv).Trim())"
$KeyName = az aigateway api-key list --query "[?properties.state=='active'] | [0].name" -o tsv
if (-not $KeyName) {
  $KeyName = az aigateway api-key create --name default --display-name "Default key" --state active --query name -o tsv
}
$ApiKey = az aigateway api-key list-secrets -n $KeyName --query primaryKey -o tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ApiKey)) {
  throw "Failed to retrieve the API key secret."
}
$Model = az aigateway model-alias list --query "[?contains(properties.supportedEndpoints, '/openai/v1/chat/completions')] | [0].properties.aliasName" -o tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Model)) {
  throw "No chat completions model alias was found."
}

$headers = @{ "api-key" = $ApiKey }
$body = @{
  model = $Model
  messages = @(@{ role = "user"; content = "Write a one-sentence status update." })
} | ConvertTo-Json -Depth 4

(Invoke-RestMethod `
  -Method Post `
  -Uri "$GatewayUrl/default/models/openai/v1/chat/completions" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body).choices[0].message.content
Remove-Variable ApiKey
```

Expect a short reply from the model (`choices[0].message.content` in the curl
JSON response). This direct model call does not invoke the registered Learn MCP
server; an MCP-capable client or agent must connect and call its tools to ground
the answer in retrieved documentation. Keep the key out of logs and source control.
For key discovery, protocol checks, and troubleshooting, see the
[expanded model test](command-reference.md#test-models-with-additional-checks).
If you followed only the MCP path, use the
[MCP smoke test](command-reference.md#test-mcp-tools).

### 6. Optional cleanup

Only run these commands for the dedicated tutorial resources. Gateway deletion
removes its registrations and retains an API Management soft-delete record;
the name may not be immediately reusable. Resource group deletion removes
**everything** remaining in that group. Both commands prompt for confirmation.
An existing Foundry account outside the group and its deployments are not
deleted. If you followed the model path, also review the account-scoped role
assignment created for the gateway identity and remove it when no longer needed.

```bash
az aigateway delete --resource-group "$RG" --name "$GATEWAY"
az group delete --name "$RG"
```

## Uninstall

```bash
az extension remove --name aigateway
```

This removes the local CLI extension, not your Azure resources.
