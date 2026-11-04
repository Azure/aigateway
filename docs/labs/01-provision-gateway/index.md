---
title: Provision your AI Gateway
summary: Create the shared Azure AI Gateway that your apps and agents will call, from the AI Gateway portal, the Azure CLI, or Bicep and azd, then take a guided tour of the portal.
category: foundations
level: Beginner
duration: 15
tracks: [portal, cli, iac]
order: 1
illustration: diagrams/provisioning.svg
tags: [provisioning, aigateways, az aigateway, Bicep, managed identity, regions]
objectives:
  - Find the regions where AI Gateway is available, and create a gateway in one from the portal, the Azure CLI, or Bicep and azd
  - Find the gateway's runtime URL and its system-assigned managed identity
  - Confirm that the runtime endpoint answers over HTTPS
  - Navigate the AI Gateway portal and know which area manages what
prereqs: []
---

# Provision your AI Gateway

Your platform team is about to put every model and tool that the company's apps and agents use behind one
governed entry point. Before anyone can publish a model, issue a key, or set a budget, you need the gateway
itself. In this lab you create a shared AI Gateway, find its runtime URL and managed identity, and learn your
way around the portal so you're ready for the rest of the labs.

<!-- video: media/walkthrough.mp4 | Narrated walkthrough: create an AI Gateway in the portal and tour it (3 min) -->

![What provisioning creates: you choose a name, resource group, and region; Azure creates the AI Gateway, its managed identity, and its connector gateway; you get a runtime URL, a default workspace, and the portal](../assets/diagrams/provisioning.svg "One gateway per environment is the usual starting point. Every later lab publishes models, tools, keys, and policies on it.")

## Before you begin

<!-- setup: permissions tools sign-in extension providers regions clone -->

Every later lab reuses this one-time setup.

> [!TIP]
> On the **Bicep + azd** track, `azd up` creates the resource group and the gateway and names them for you, so you
> can skip the variables at the end of this section.

- For the portal track: a browser and your Azure account.
- A region where the Foundry models of the later labs are available too.
- Recommended reading: [How AI Gateway works](../00-how-ai-gateway-works/README.md).

### Set your variables

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
# Make the subscription that you use for the labs the current one, so that every command runs in it
az account set --subscription "<subscription-id>" &&
  echo "🆔 Current subscription: $(az account show --query name -o tsv)"

# Name the resource group and the gateway, and choose the region
export RG="<resource-group>"               # for example rg-ai-gateway-labs
export GATEWAY="<gateway>"                 # globally unique, 24 characters or fewer, part of the runtime URL
export LOCATION="<location>"               # a Name from the list of available regions, for example eastus2
echo "📝 Gateway $GATEWAY in $RG ($LOCATION)"

# Read the subscription ID, which the REST call for the connector gateway uses
export SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
echo "🆔 Subscription ID: $SUBSCRIPTION_ID"
```

```powershell title="PowerShell"
# Make the subscription that you use for the labs the current one, so that every command runs in it
az account set --subscription "<subscription-id>"
if ($?) { Write-Host "🆔 Current subscription: $(az account show --query name -o tsv)" }

# Name the resource group and the gateway, and choose the region
$RG              = "<resource-group>"      # for example rg-ai-gateway-labs
$GATEWAY         = "<gateway>"             # globally unique, 24 characters or fewer, part of the runtime URL
$LOCATION        = "<location>"            # a Name from the list of available regions, for example eastus2
Write-Host "📝 Gateway $GATEWAY in $RG ($LOCATION)"

# Read the subscription ID, which the REST call for the connector gateway uses
$SUBSCRIPTION_ID = az account show --query id -o tsv
Write-Host "🆔 Subscription ID: $SUBSCRIPTION_ID"
```

> [!IMPORTANT]
> Create the resource group in the same region as the gateway, so that defaults line up. The gateway
> name must be 1–24 characters: letters, digits, and hyphens, starting with a letter and not ending with a hyphen.

## How it works

An AI Gateway is an Azure Resource Manager resource of type `Microsoft.ApiManagement/aigateways`. You manage it
in the [AI Gateway portal](https://ai.gateway.azure.com), which is separate from the Azure portal, or through
Azure Resource Manager with the CLI, REST, or Bicep. Each gateway has a companion connector gateway
(`Microsoft.Web/connectorGateways`) with the same name. There's no capacity to size, so the only real decisions
are the name, the region, and the resource group.

| Property | Value |
|---|---|
| Resource type | `Microsoft.ApiManagement/aigateways` (API version `2025-09-01-preview`), plus `Microsoft.Web/connectorGateways` with the same name |
| Regions | The list grows over time. List them as in [Find the available regions](../SETUP.md#find-the-available-regions) |
| Name | 1–24 characters: letters, digits, and hyphens. Its first 10 characters start the runtime host name |
| Runtime URL | `https://` + `properties.frontend.defaultHostname`: the name's first 10 characters, a hyphen, a 13-character hash, and `.<region>-01.ai.gateway.azure.com`. A gateway named `aigw-labs-001` in East US 2 answers at a URL like `https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com`. Always read it from the gateway; you can't build it from the name |
| Runtime routes | Models under `/default/models/…`, MCP servers under `/default/toolservers/<server>/mcp` |
| Outbound identity | A system-assigned managed identity, used to call Foundry and other Microsoft Entra–protected backends |
| SKU | `Standard`, the default for the portal, `az aigateway create`, and templates that omit `sku`. The labs use `Standard`, and their Bicep templates set it explicitly |
| Provisioning time | A few minutes, often less |

Everything you publish later lives in the gateway's `default` workspace. That's why every runtime route
starts with `/default/`. Applications authenticate **inbound** with an API key or a Microsoft Entra token. The
gateway authenticates **outbound** to each backend, usually with its managed identity, so apps never hold
provider credentials.

![AI Gateway architecture: apps and agents call one gateway that governs models and tools](../assets/diagrams/architecture.svg "Apps and agents call one runtime URL. The gateway applies access, policies, and telemetry before it routes to models and MCP servers.")

## Create the gateway

Pick one track. Each track produces the same result: a gateway named `<gateway>` in `<resource-group>`, with a
system-assigned managed identity. The Bicep + azd track picks the names for you: `aigw-` plus six unique characters,
in `rg-aigw-lab01`.

<!-- track: portal | Portal -->

### Sign in to the AI Gateway portal

Open the [AI Gateway portal](https://ai.gateway.azure.com) and sign in with your Azure account. If this is your
first gateway, the portal takes you straight into gateway creation. If you already have a gateway, open the
gateway switcher in the top bar and start creating a new one from there.

### Enter the gateway details

In **Create AI gateway**, enter a globally unique **Name** of 24 characters or fewer, or select
**Generate a new name**. Then choose the subscription, a **Resource group** (**New** or **Existing**), and the
**Region**. Under **Advanced**, keep **Enable system-assigned managed identity** selected, **Public network access** set to **Enabled**, and
**Public routing**. **Private routing** connects the gateway to private backends through a virtual network. You can
also add it later under **Networking**. [Lab 18](../18-private-networking/README.md) covers it.

![What to choose in Create AI gateway: a unique name, a subscription, a resource group, and a region, with the Advanced defaults kept](../assets/diagrams/create-gateway.svg "Fill in the basics, keep the Advanced defaults, then select Create gateway.")

> [!NOTE]
> The subscription picker lists every subscription you can see. Subscriptions where you lack write permission
> for API Management and connector gateways are disabled, and the portal explains why.

### Watch it provision

Select **Create gateway**. The portal shows provisioning progress in place, and a new gateway is typically ready
in a few minutes.

### Open the setup guide on Home

When provisioning finishes, **Home** opens with a setup guide for publishing models, adding MCP servers, and
creating runtime access. Leave it for now. You publish your first model in the next lab, and the guide stays
on **Home** until you finish it.

> **Checkpoint**
> The gateway switcher in the top bar shows `<gateway>`, and **Home** shows the setup guide.

<!-- track: cli | Azure CLI -->

If you haven't yet, [register the resource providers](../SETUP.md#register-the-resource-providers) in this
subscription: the gateway lives in `Microsoft.ApiManagement` and its connector gateway in `Microsoft.Web`.

### Create a resource group

```bash
# Create the resource group that holds the gateway, in the gateway's region
az group create --name "$RG" --location "$LOCATION" --output none &&
  echo "📦 Resource group $RG is ready in $LOCATION"
```

### Create the connector gateway

Every AI gateway has a companion `Microsoft.Web/connectorGateways` resource with the same name, and either one
can be created first. The `aigateway` extension creates only the AI gateway, so
create the connector gateway through the Azure Resource Manager REST API with `az rest`.

```bash title="Bash"
# Create the companion connector gateway through the REST API, because the aigateway extension doesn't create it
az rest --method put --output none \
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Web/connectorGateways/$GATEWAY?api-version=2026-05-01-preview" \
  --body "$(jq -cn --arg location "$LOCATION" '{location: $location, properties: {}}')" &&
  echo "🔌 Connector gateway $GATEWAY is ready"
```

```powershell title="PowerShell"
# Write the request body to a file, so that PowerShell passes the JSON to az rest unchanged
@{ location = $LOCATION; properties = @{} } | ConvertTo-Json -Compress | Set-Content body.json

# Create the companion connector gateway through the REST API, because the aigateway extension doesn't create it
az rest --method put --output none `
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Web/connectorGateways/${GATEWAY}?api-version=2026-05-01-preview" `
  --body "@body.json"
if ($?) { Write-Host "🔌 Connector gateway $GATEWAY is ready" }
Remove-Item body.json
```

### Create the AI gateway

`az aigateway create` only needs the name, the region, and the managed identity. Without `--sku`, the gateway gets
the service's default SKU, `Standard`, like a gateway that you create in the portal. There's no capacity or
publisher to set. The command waits until provisioning finishes, usually within a few minutes.

```bash title="Bash"
# Create the gateway in the default Standard SKU with a system-assigned managed identity, and wait until it's ready
az aigateway create -g "$RG" -n "$GATEWAY" --location "$LOCATION" --system-assigned true -o none &&
  echo "🚀 Gateway $GATEWAY is ready in $LOCATION"
```

```powershell title="PowerShell"
# Create the gateway in the default Standard SKU with a system-assigned managed identity, and wait until it's ready
az aigateway create -g $RG -n $GATEWAY --location $LOCATION --system-assigned true -o none
if ($?) { Write-Host "🚀 Gateway $GATEWAY is ready in $LOCATION" }
```

> [!TIP]
> Add `--no-wait` to return right away, then run `az aigateway wait -g "$RG" -n "$GATEWAY" --created` when you
> need the gateway.

### Read the runtime URL and identity

```bash title="Bash"
# Show the gateway's SKU and state, its runtime host name, and the principal ID of its managed identity
echo "📊 Gateway $GATEWAY, its runtime host, and its identity:"
az aigateway show -g "$RG" -n "$GATEWAY" \
  --query "{name:name, location:location, sku:sku.name, state:properties.provisioningState, host:properties.frontend.defaultHostname, principalId:identity.principalId}" \
  -o table
```

```powershell title="PowerShell"
# Show the gateway's SKU and state, its runtime host name, and the principal ID of its managed identity
Write-Host "📊 Gateway $GATEWAY, its runtime host, and its identity:"
az aigateway show -g $RG -n $GATEWAY `
  --query "{name:name, location:location, sku:sku.name, state:properties.provisioningState, host:properties.frontend.defaultHostname, principalId:identity.principalId}" `
  -o table
```

> **Checkpoint**
> The table shows the `Standard` SKU, `Succeeded`, a `Host` like `aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com`,
> and a `PrincipalId` GUID.

<!-- track: iac | Bicep + azd -->

**What you need:** the [Setup guide](../SETUP.md) tasks from **Before you begin**. `azd up` creates the resource
group and the gateway, so you don't need the variables.

### Review the template

`infra/gateway.bicep` declares the gateway. It follows the AI Gateway [reference sample](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/infra/ai-gateway/main.bicep). It creates the AI gateway
(`Microsoft.ApiManagement/aigateways`) in the `Standard` SKU with a system-assigned identity, then a
`Microsoft.Web/connectorGateways` resource with the same name. There's no capacity or publisher to set. Keep both
resources together in your own templates. `Standard` is also the default when a template omits `sku`.

| Parameter | Description |
|---|---|
| `gatewayName` | Required. The gateway name, 24 characters or fewer |
| `location` | `eastus2` (default), or another region where AI Gateway is available |
| `tags` | Optional. Tags applied to both resources |
| `backendSubnetId` | Optional. A subnet for outbound virtual network integration, which can only be set at creation. See [Lab 18](../18-private-networking/README.md) |

<!-- include: infra/gateway.bicep -->

`infra/main.bicep` is the template that azd deploys. It creates the resource group `rg-<environment name>`, then
calls `infra/gateway.bicep` with the name `aigw-` plus six characters that are unique to your subscription,
environment, and region. Its outputs become azd environment values:

<!-- include: infra/main.bicep -->

Later labs reuse `infra/gateway.bicep` as a module. You can also deploy it on its own to a resource group you
already have, with `az deployment group create`, as **Go further** shows.

> [!TIP]
> Bicep has no type definitions yet for `Microsoft.ApiManagement/aigateways` and `Microsoft.Web/connectorGateways`.
> As in the reference sample, each `#disable-next-line BCP081` line silences the warning about it. Without these
> lines, the build shows `BCP081` warnings, which don't block the deployment.

### Deploy with azd up

Move into the lab's folder, create an azd environment named `aigw-lab01` in your current subscription, then provision
the resource group and the gateway. It takes about three minutes.

```bash title="Bash"
# Move into the lab's folder, which holds the azd project
cd ~/ai-gateway/labs/01-provision-gateway &&
  echo "📂 Lab folder: $(pwd)"

# Create an azd environment in your current subscription, so that azd doesn't prompt you
azd env new aigw-lab01 --location eastus2 --subscription "$(az account show --query id --output tsv)" &&
  echo "📝 azd environment aigw-lab01 deploys to eastus2"

# Provision the resource group, the gateway, and its connector gateway
azd up &&
  echo "🚀 Gateway $(azd env get-value AI_GATEWAY_NAME) is deployed"
```

```powershell title="PowerShell"
# Move into the lab's folder, which holds the azd project
Set-Location ~/ai-gateway/labs/01-provision-gateway
if ($?) { Write-Host "📂 Lab folder: $(Get-Location)" }

# Create an azd environment in your current subscription, so that azd doesn't prompt you
azd env new aigw-lab01 --location eastus2 --subscription (az account show --query id --output tsv)
if ($?) { Write-Host "📝 azd environment aigw-lab01 deploys to eastus2" }

# Provision the resource group, the gateway, and its connector gateway
azd up
if ($?) { Write-Host "🚀 Gateway $(azd env get-value AI_GATEWAY_NAME) is deployed" }
```

For another region, use its name from [Find the available regions](../SETUP.md#find-the-available-regions).

### Read the outputs

Set the variables that **Verify** and **Go further** use from azd's environment values, then print the runtime URL
and the gateway's principal ID.

```bash title="Bash"
# Read the resource group, the gateway name, and the region from azd's environment values
export RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
export GATEWAY="$(azd env get-value AI_GATEWAY_NAME)"
export LOCATION="$(azd env get-value AZURE_LOCATION)"
echo "📝 Gateway $GATEWAY in $RG ($LOCATION)"

# Print the gateway's runtime URL and the principal ID of its managed identity
echo "🌐 Runtime URL: $(azd env get-value AI_GATEWAY_URL)"
echo "👤 Gateway identity: $(azd env get-value AI_GATEWAY_PRINCIPAL_ID)"
```

```powershell title="PowerShell"
# Read the resource group, the gateway name, and the region from azd's environment values
$RG       = azd env get-value AZURE_RESOURCE_GROUP
$GATEWAY  = azd env get-value AI_GATEWAY_NAME
$LOCATION = azd env get-value AZURE_LOCATION
Write-Host "📝 Gateway $GATEWAY in $RG ($LOCATION)"

# Print the gateway's runtime URL and the principal ID of its managed identity
Write-Host "🌐 Runtime URL: $(azd env get-value AI_GATEWAY_URL)"
Write-Host "👤 Gateway identity: $(azd env get-value AI_GATEWAY_PRINCIPAL_ID)"
```

> **Checkpoint**
> `azd up` ended with `SUCCESS`. The commands print a runtime URL like
> `🌐 Runtime URL: https://aigw-x7k2q-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com`, and `👤 Gateway identity:` with a
> principal ID GUID.

<!-- /tracks -->

## Verify

<!-- steps -->

### Call the runtime URL

Read the host name from the gateway rather than building it yourself, then send a request without a key. Any
HTTP status proves that DNS, TLS, and the gateway are up. A new gateway with no models answers `404`; after you
add a model and a key in the next lab, a call without a key gets `400` or `401`.

```bash title="Bash"
# Read the runtime host name from the gateway, and build the runtime URL from it
export AI_GATEWAY_URL="https://$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
echo "🌐 Runtime URL: $AI_GATEWAY_URL"

# Call the Chat Completions route without a key, and print only the HTTP status that the gateway answers with
curl -sS -o /dev/null -w "🌐 The gateway answered: HTTP %{http_code}\n" "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
```

```powershell title="PowerShell"
# Read the runtime host name from the gateway, and build the runtime URL from it
$env:AI_GATEWAY_URL = "https://$(az aigateway show -g $RG -n $GATEWAY --query properties.frontend.defaultHostname -o tsv)"
Write-Host "🌐 Runtime URL: $env:AI_GATEWAY_URL"

# Call the Chat Completions route without a key, and print only the HTTP status that the gateway answers with
$status = (Invoke-WebRequest -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -SkipHttpErrorCheck).StatusCode
if ($?) { Write-Host "🌐 The gateway answered: HTTP $status" }
```

A `Could not resolve host` error means the gateway isn't ready yet. Wait a minute and try again.

### Find the gateway on Home

Open the [AI Gateway portal](https://ai.gateway.azure.com). If you created the gateway with the CLI or with Bicep
and azd, select it in the gateway switcher in the top bar. **Home** shows the setup guide for your new gateway.

### Check the managed identity

Select **Managed identities**. On the **Configure identities** tab, the system-assigned identity is enabled.
Its principal ID matches `principalId` from the CLI output, or `AI_GATEWAY_PRINCIPAL_ID` from azd. In later labs
you grant this identity access to Foundry so that the gateway can call your models without keys.

![The Managed identities page with the system-assigned identity enabled](../assets/screens/managed-identities.png "Managed identities › Configure identities shows the system-assigned identity with its principal ID and tenant ID. You can add user-assigned identities here too.")

### Tour the portal

Use the left navigation to get familiar with each area. You visit most of them in later labs.

| Area | What you do there | Where you learn it |
|---|---|---|
| **Home** | Follow the setup guide for models, MCP servers, and runtime access | This lab |
| **Catalog** | Browse published models and MCP servers, try them in the playground, and copy endpoints and code samples | [Lab 02](../02-first-model-call/README.md) |
| **Access** | Create runtime API keys on the **Keys** tab and grant Microsoft Entra roles on the **Entra ID** tab | [Lab 10](../10-api-keys/README.md), [Lab 11](../11-entra-rbac/README.md) |
| **Models** | Import Foundry deployments, add custom models from other providers, and manage aliases | [Lab 02](../02-first-model-call/README.md), [Lab 03](../03-multi-provider-aliases/README.md) |
| **MCP servers** | Publish MCP servers and control which tools are available | [Lab 04](../04-federate-mcp-tools/README.md), [Lab 05](../05-mcp-tool-controls/README.md) |
| **Policies** | Add token and request rate limits, cost limits, content safety, and IP filters at gateway or asset scope | [Lab 06](../06-token-limits/README.md), [Lab 09](../09-gateway-baselines/README.md) |
| **Monitoring** | Send telemetry to an OTLP destination and use the built-in dashboard and traces | [Lab 13](../13-monitoring/README.md) |
| **Networking** | Review network access and outbound virtual network integration | [Lab 18](../18-private-networking/README.md) |
| **Managed identities** | Manage the identities that the gateway uses to call backends | [Lab 12](../12-backend-identity/README.md) |

The top bar holds the gateway switcher, **What's new**, notifications, and a command palette (Ctrl+K) to jump
to any page.

> [!NOTE]
> Some portal versions show **Keys** directly in the left navigation instead of **Access** › **Keys**. Both
> lead to the same runtime API keys.

<!-- /steps -->

> **Checkpoint**
> The runtime URL answers with an HTTP status, the gateway appears on **Home**, and **Managed identities**
> shows the system-assigned identity enabled.

## Go further

- **One gateway per environment.** Run `azd env new <name>` and `azd up` once for each of dev, test, and
  production: every azd environment gets its own resource group and gateway. Keep the template in source control
  next to your app.
- **Tag for ownership and chargeback.** The template's `tags` parameter applies the same tags to the gateway
  and its connector gateway, so set them when you create each environment's gateway. To add them to the gateway
  you have, deploy `infra/gateway.bicep` on its own from the lab folder:

  ```bash
  # Deploy the gateway's template again with tags, which updates the gateway and its connector gateway in place
  az deployment group create -g "$RG" --template-file infra/gateway.bicep --output none \
    --parameters gatewayName="$GATEWAY" location="$LOCATION" \
                 tags='{"workload":"ai-gateway-labs","owner":"platform-team","costCenter":"1234"}' &&
    echo "📝 Tags are set on gateway $GATEWAY and its connector gateway"
  ```
- **Use a user-assigned identity.** When several gateways must share one backend identity, add a
  user-assigned identity on **Managed identities**. See
  [Call backends with managed identities](../12-backend-identity/README.md).

## Clean up

The portal and CLI tracks of every later lab reuse the gateway, so **keep it** until you finish the labs you plan to
do.

<!-- track: cli | Portal and Azure CLI -->

### Delete the resource group

When you're done with all the labs, delete the resource group. That removes the gateway, its connector gateway,
and everything else in the group. The command asks for confirmation.

```bash title="Bash"
# Delete the resource group, with the gateway, its connector gateway, and everything else in it, after you confirm
az group delete --name "$RG" &&
  echo "🚮 Resource group $RG is deleted"
```

```powershell title="PowerShell"
# Delete the resource group, with the gateway, its connector gateway, and everything else in it, after you confirm
az group delete --name $RG
if ($?) { Write-Host "🚮 Resource group $RG is deleted" }
```

### Delete only the gateway

To keep the resource group, delete the AI gateway first and then its connector gateway. Deleting the gateway
also deletes everything you published on it.

```bash title="Bash"
# Delete the AI gateway, with everything that you published on it
az aigateway delete -g "$RG" -n "$GATEWAY" --yes &&
  echo "🚮 Gateway $GATEWAY is deleted"

# Delete its companion connector gateway, which has the same name
az resource delete -g "$RG" -n "$GATEWAY" --resource-type Microsoft.Web/connectorGateways --api-version 2026-05-01-preview &&
  echo "🚮 Connector gateway $GATEWAY is deleted"
```

```powershell title="PowerShell"
# Delete the AI gateway, with everything that you published on it
az aigateway delete -g $RG -n $GATEWAY --yes
if ($?) { Write-Host "🚮 Gateway $GATEWAY is deleted" }

# Delete its companion connector gateway, which has the same name
az resource delete -g $RG -n $GATEWAY --resource-type Microsoft.Web/connectorGateways --api-version 2026-05-01-preview
if ($?) { Write-Host "🚮 Connector gateway $GATEWAY is deleted" }
```

<!-- track: iac | Bicep + azd -->

### Delete everything azd created

You don't need to keep this gateway for the Bicep + azd tracks of later labs: each of them creates its own gateway.
If you continue with the portal or CLI track of [lab 02](../02-first-model-call/README.md), you can keep it and use
its names instead: the resource group is `rg-aigw-lab01`, and `azd env get-value AI_GATEWAY_NAME` prints the gateway
name.

Otherwise, in the `ai-gateway/labs/01-provision-gateway` folder, delete the resource group with the gateway and its
connector gateway. It takes up to ten minutes.

```bash
# Delete everything that azd up created, without asking you to confirm
azd down --purge --force &&
  echo "🚮 Everything that azd up created is deleted"
```

<!-- /tracks -->

## Next steps

- [Publish a Foundry model and make your first call](../02-first-model-call/README.md): import a model, create a key, and call it.
- [Issue and rotate runtime API keys](../10-api-keys/README.md): give each app its own key.
- [How AI Gateway works](../00-how-ai-gateway-works/README.md): the concepts behind models, tools, policies, and identity.
- Docs: [Configure AI Gateway in the portal](https://ai.gateway.azure.com/docs/quickstarts/portal) and
  [AI Gateway CLI quickstart](https://ai.gateway.azure.com/docs/quickstarts/cli).
