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

Choose a globally unique gateway name and a supported region.

```bash
az login
az account set --subscription "<subscription-id>"

RG="rg-aigateway-quickstart"
GATEWAY="<globally-unique-gateway-name>"
LOCATION="<supported-region>"

az group create --name "$RG" --location "$LOCATION"
az aigateway create --resource-group "$RG" --name "$GATEWAY" --location "$LOCATION"
az aigateway show --resource-group "$RG" --name "$GATEWAY" --output table
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
  --resource-group "$RG" --gateway-name "$GATEWAY" --name learn \
  --endpoints '[{"kind":"mcp","namespace":"learn","mcp":{"transport":"streamableHttp","url":"https://learn.microsoft.com/api/mcp"}}]'

az aigateway mcp list --resource-group "$RG" --gateway-name "$GATEWAY" --output table
az aigateway mcp show --resource-group "$RG" --gateway-name "$GATEWAY" --name learn
```

Notice that `--name` now identifies the **MCP registration**; `--gateway-name`
identifies its parent gateway. The output shows the registered server and its
configuration, not a tool invocation. Use the
[coding-agent plugin](../README.md#coding-agent-plugin) to build an application
that consumes the gateway, or explore more commands in the
[command reference](command-reference.md).

### 3. Add models through a provider

For this path, you need an **existing Foundry AI Services or Azure OpenAI
account with model deployments**. Use a test account outside the tutorial
resource group. You need permission to read the account and its deployments,
update the gateway, and create role assignments on the account.

The command below imports **every current deployment** into one gateway provider.
It enables the gateway's system-assigned identity and grants that identity the
**Foundry User** role on the account. It does not create model deployments;
normal charges still apply when you use them.

Use the existing account's name and resource group to look up its resource ID
in your selected subscription. No need to copy a long ID from the portal.
Use the account name, not a project or deployment name.

```bash
FOUNDRY_RG="<foundry-resource-group>"
FOUNDRY_ACCOUNT="<foundry-account-name>"
PROVIDER="foundry-models"

FOUNDRY_RESOURCE_ID="$(az cognitiveservices account show \
  --resource-group "$FOUNDRY_RG" --name "$FOUNDRY_ACCOUNT" \
  --query id --output tsv)"

az aigateway model-provider create \
  -g "$RG" --gateway-name "$GATEWAY" --name "$PROVIDER" \
  --foundry-resource-id "$FOUNDRY_RESOURCE_ID"

az aigateway model list \
  -g "$RG" --gateway-name "$GATEWAY" \
  --model-provider "$PROVIDER" --output table
```

Review the import summary for any failed registrations. Successfully imported
models use their deployment names. Choose one from the list for the next step.

### 4. Set model policies

Apply a token limit and content safety to the selected model. The example allows
**10,000 tokens per minute per identity** and sets content safety severity to
**Medium** for hate, self-harm, sexual, and violence categories. Adjust these
example values to suit your application.

```bash
MODEL="<imported-model-name>"

az aigateway model policy set \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --token-limit 10000 --token-period minute --token-counter-key Identity \
  --content-safety Medium

az aigateway model policy list \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL"
```

These policies apply only to this gateway model registration, not every model
in the provider or calls made directly to the backend. See
[common model policies](command-reference.md#common-model-policies) to change
one policy at a time.

### 5. Test the gateway

This happy-path example assumes the earlier model setup succeeded, the gateway
has an active API key, and your selected model supports
`/openai/v1/chat/completions`. You need permission to read the key. Run the commands
in order and stop if one reports an error. The examples select the sole active
key; if there are several, list them with `az aigateway api-key list`, set
`KEY_NAME` to your chosen name, and continue from `list-secrets`.
Model calls can incur inference charges.

**Bash / curl** -- reuse the variables from the earlier steps:

```bash
AI_GATEWAY_URL="$(az aigateway show -g "$RG" -n "$GATEWAY" \
  --query properties.gatewayUrl -o tsv)"
KEY_NAME="$(az aigateway api-key list -g "$RG" --gateway-name "$GATEWAY" \
  --query "[?properties.state=='active'].name" -o tsv)" || exit 1
if [ -z "$KEY_NAME" ] || [[ "$KEY_NAME" == *$'\n'* ]]; then
  echo "Select exactly one active API key name before continuing." >&2
  exit 1
fi
AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets \
  -g "$RG" --gateway-name "$GATEWAY" -n "$KEY_NAME" --query primaryKey -o tsv)" || exit 1
: "${AI_GATEWAY_API_KEY:?No key value returned; check your key-read permissions.}"
RUNTIME_MODEL="$(az aigateway model show \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --query properties.deployment.modelName -o tsv)"

curl -fsS "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "Api-Key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  --data @- <<EOF
{"model":"$RUNTIME_MODEL","messages":[{"role":"user","content":"Describe the AI Gateway SKU of Azure API Management in one sentence."}]}
EOF
unset AI_GATEWAY_API_KEY
```

**PowerShell / `irm`** -- set the same resource names in this shell:

```powershell
$RG = "rg-aigateway-quickstart"
$GATEWAY = "<your-gateway-name>"
$PROVIDER = "foundry-models"
$MODEL = "<imported-model-name>"

$AI_GATEWAY_URL = az aigateway show -g $RG -n $GATEWAY --query properties.gatewayUrl -o tsv
$KEY_NAMES = @(az aigateway api-key list -g $RG --gateway-name $GATEWAY --query "[?properties.state=='active'].name" -o tsv)
if ($LASTEXITCODE -ne 0 -or $KEY_NAMES.Count -ne 1) { throw "Select exactly one active API key name before continuing." }
$KEY_NAME = $KEY_NAMES[0]
$AI_GATEWAY_API_KEY = az aigateway api-key list-secrets -g $RG --gateway-name $GATEWAY -n $KEY_NAME --query primaryKey -o tsv
if ($LASTEXITCODE -ne 0 -or !$AI_GATEWAY_API_KEY) { throw "Unable to read the API key; stop before calling the gateway." }
$RUNTIME_MODEL = az aigateway model show -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER -n $MODEL --query properties.deployment.modelName -o tsv
$body = @{
  model = $RUNTIME_MODEL
  messages = @(@{ role = "user"; content = "Describe the AI Gateway SKU of Azure API Management in one sentence." })
} | ConvertTo-Json -Depth 5

$reply = irm -Method Post -Uri "$($AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -Headers @{ "Api-Key" = $AI_GATEWAY_API_KEY } -ContentType "application/json" `
  -Body $body -ErrorAction Stop
$reply.choices[0].message.content
Remove-Variable AI_GATEWAY_API_KEY
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
