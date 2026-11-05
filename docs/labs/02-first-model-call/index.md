---
title: Publish a Foundry model and make your first call
summary: Publish a Microsoft Foundry model deployment through your gateway with its managed identity, create a runtime API key, try the model in the Catalog playground, and call it from curl, PowerShell, Python, TypeScript, and C#.
category: foundations
level: Beginner
duration: 25
tracks: [portal, cli, iac, code]
order: 2
illustration: diagrams/request-lifecycle.svg
tags: [Microsoft Foundry, model provider, alias, API key, Chat Completions, Responses API, OpenAI SDK, managed identity]
objectives:
  - Publish a Foundry model deployment through the gateway, authenticated with the gateway's managed identity
  - Create a runtime API key and keep its value out of code
  - Call the model through the gateway with the Chat Completions and Responses APIs
  - Explain what the gateway does with a request between your app and the model
prereqs:
  - 01-provision-gateway
---

# Publish a Foundry model and make your first call

The first product team wants to use `gpt-6-luna`, which already runs in your Microsoft Foundry account. You
don't want to hand every team the Foundry endpoint and a provider key. In this lab you publish the deployment
through your gateway, give the team a runtime API key of its own, and make the first call from the playground,
a shell, and code. The gateway authenticates to Foundry with its own managed identity, so the app never sees a
Foundry credential.

![A request travels from the app through the gateway to the model and back](../assets/diagrams/request-lifecycle.svg "The gateway checks the caller's key, applies policies, calls the backend with its own identity, and records telemetry on the way back.")

## Before you begin

<!-- setup: tools sign-in extension clone -->

> [!TIP]
> On the **Bicep + azd** track, `azd up` creates its own gateway, Foundry account, model, and key, so you can skip
> this section. You need only the one-time setup above, plus the language runtime for the code track if you follow it.

- Complete [Provision your AI Gateway](../01-provision-gateway/README.md). You need the gateway, its resource
  group, and its runtime URL.
- A model deployment in a Microsoft Foundry (Azure AI Services) or Azure OpenAI account, for example
  `gpt-6-luna`. If you don't have one, deploy the optional template described below.
- Permission to grant the gateway access to the account: **Owner**, **User Access Administrator**, or **Role
  Based Access Control Administrator** on the Foundry account. You also need to change the gateway, for example
  **Contributor** on its resource group.
- For the code track: Python 3.9 or later, Node.js 22.18 or later, or the .NET 8 SDK.
- Run the scripts and samples from the lab's folder, `~/aigateway/labs/02-first-model-call`.

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
# Name your gateway and its resource group, the Foundry account and its deployment, and the provider to create
export RG="<resource-group>"
export GATEWAY="<gateway>"
export FOUNDRY_RG="<foundry-resource-group>"      # resource group of the Foundry account
export FOUNDRY_ACCOUNT="<foundry-account-name>"   # the account name, not a project or deployment name
export DEPLOYMENT="gpt-6-luna"                    # the model deployment to publish
export PROVIDER="foundry-models"                  # CLI track: the gateway provider to create
echo "📝 Gateway $GATEWAY in $RG, deployment $DEPLOYMENT in Foundry account $FOUNDRY_ACCOUNT"

# Read the gateway's resource ID, and build its runtime URL from its host name
export GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"
export AI_GATEWAY_URL="https://$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
echo "🆔 Gateway ID: $GATEWAY_ID"
echo "🌐 Runtime URL: $AI_GATEWAY_URL"
```

```powershell title="PowerShell"
# Name your gateway and its resource group, the Foundry account and its deployment, and the provider to create
$RG              = "<resource-group>"
$GATEWAY         = "<gateway>"
$FOUNDRY_RG      = "<foundry-resource-group>"     # resource group of the Foundry account
$FOUNDRY_ACCOUNT = "<foundry-account-name>"       # the account name, not a project or deployment name
$DEPLOYMENT      = "gpt-6-luna"                   # the model deployment to publish
$PROVIDER        = "foundry-models"               # CLI track: the gateway provider to create
Write-Host "📝 Gateway $GATEWAY in $RG, deployment $DEPLOYMENT in Foundry account $FOUNDRY_ACCOUNT"

# Read the gateway's resource ID, and build its runtime URL from its host name
$GATEWAY_ID = az aigateway show -g $RG -n $GATEWAY --query id -o tsv
$env:AI_GATEWAY_URL = "https://$(az aigateway show -g $RG -n $GATEWAY --query properties.frontend.defaultHostname -o tsv)"
Write-Host "🆔 Gateway ID: $GATEWAY_ID"
Write-Host "🌐 Runtime URL: $env:AI_GATEWAY_URL"
```

<details>
<summary>No Foundry deployment yet? Create one with Bicep.</summary>

[infra/foundry.bicep](infra/foundry.bicep) creates an Azure AI Services account with a `gpt-6-luna`
`GlobalStandard` deployment, mirroring the reference sample. Pick a region where the model is available. Model
inference is billed per use.

```bash
# Create the resource group for the Foundry account
az group create --name "$FOUNDRY_RG" --location eastus2 --output none &&
  echo "📦 Resource group $FOUNDRY_RG is ready in eastus2"

# Deploy the template: the Foundry account and its gpt-6-luna deployment, then read the deployment's resource ID
DEPLOYMENT_ID="$(az deployment group create -g "$FOUNDRY_RG" \
  --template-file infra/foundry.bicep \
  --parameters accountName="$FOUNDRY_ACCOUNT" deploymentName="$DEPLOYMENT" \
  --query properties.outputs.deploymentId.value -o tsv)" &&
  echo "✨ Model deployment $DEPLOYMENT is ready: $DEPLOYMENT_ID"
```

</details>

## How it works

Publishing a model has three parts. A **model provider** tells the gateway where the Foundry account is and
how to authenticate to it. A **backend model** registers one deployment under that provider. A callable
**alias** is the stable name that clients send in the request `model` field. Importing from Foundry creates all
three for you.

Clients call one runtime URL with a gateway API key. The gateway validates the key before anything else, runs
the policies that apply, swaps the caller's key for its own managed identity token, and forwards the request
unchanged to Foundry. The response comes back as is, and the gateway records token usage for monitoring.

| Step | What happens | Where you set it |
|---|---|---|
| Inbound authentication | An active runtime key in the `api-key` header, or as `Authorization: Bearer <key>` (what the OpenAI SDKs send), or the call fails with `401` | **Access** › **Keys** |
| Routing | `/default/models/openai/v1/chat/completions` or `/responses`, and `model` must equal an alias | Model details and its **Aliases** tab |
| Policies | Token limits, cost limits, and content safety run before the backend call | **Policies** (labs 06–09) |
| Backend authentication | The gateway's managed identity, with the **Foundry User** role on the account | Model provider |
| Telemetry | Tokens, latency, and the API key that made the call | **Monitoring** (lab 13) |

<!-- widget: request-lifecycle -->

## Publish the model and create a key

Pick one track. Each track publishes the deployment, gives you a callable alias, and creates a runtime API key.
The Bicep + azd track also creates its own gateway and Foundry deployment, so it doesn't need lab 01's gateway.

<!-- track: portal | Portal -->

### Import the deployment from Foundry

1. Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway in the top bar.
2. Select **Models** › **Add** › **Models from Microsoft Foundry**. (On **Home**, **Add from Microsoft Foundry** in
   the **Set up your gateway** guide starts the same import.)
3. Select the subscription and resource group of your Foundry account. The wizard discovers the deployments
   automatically. Deployments that are already in this gateway can't be selected again.
4. Select the `gpt-6-luna` deployment and keep **Managed identity** as the **Authentication method**.
5. Under **Aliases**, keep **Create an alias for each model** selected, then select **Add models**.

> [!NOTE]
> The gateway calls Foundry with its system-assigned managed identity, which needs the **Foundry User** role on
> the account. If your first call returns `403` from the backend, assign the role yourself and wait a few
> minutes for it to take effect:
>
> ```bash
> # Read the principal ID of the gateway's managed identity, and the Foundry account's resource ID
> PRINCIPAL_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query identity.principalId -o tsv)"
> FOUNDRY_ID="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)"
> echo "👤 Gateway identity: $PRINCIPAL_ID"
>
> # Give the gateway's identity the Foundry User role on the account, so that it can call the model
> az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
>   --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope "$FOUNDRY_ID" --output none &&
>   echo "🔐 The gateway's identity has the Foundry User role on $FOUNDRY_ACCOUNT"
> ```

### Copy the callable alias

Open the imported model on **Models**. The model details show its base URL and supported interfaces, such as
**OpenAI Chat Completions** and **OpenAI Responses**. Open the **Aliases** tab and copy the alias exactly as
shown, then save it in your shell. Portal imports usually name it after the provider and the deployment, for
example `<foundry-account-name>/gpt-6-luna`.

```bash title="Bash"
# Save the alias that apps send in the model field
export AI_GATEWAY_MODEL="<model-name>"    # the alias from the Aliases tab
echo "🔖 Model alias: $AI_GATEWAY_MODEL"
```

```powershell title="PowerShell"
# Save the alias that apps send in the model field
$env:AI_GATEWAY_MODEL = "<model-name>"    # the alias from the Aliases tab
Write-Host "🔖 Model alias: $env:AI_GATEWAY_MODEL"
```

### Create a runtime API key

1. Select **Access** › **Keys** › **Create API key**. Some portal versions show **Keys** directly in the left
   navigation.
2. In **Key name**, enter a name for the app that will use it, for example `app-first-call`, and select
   **Create**.
3. Copy the value from **API key created successfully**, for example with **Copy & done**. Copy it now: treat
   the value as shown only once.
4. Paste it into your shell without echoing it or writing it to a file:

```bash title="Bash"
# Paste the key without showing it, and export it for the calls and samples that follow
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
echo "🔑 Key: in AI_GATEWAY_API_KEY (${#AI_GATEWAY_API_KEY} characters, not shown)"
```

```powershell title="PowerShell"
# Paste the key without showing it, into the environment variable that the calls and samples read
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
Write-Host "🔑 Key: in AI_GATEWAY_API_KEY ($($env:AI_GATEWAY_API_KEY.Length) characters, not shown)"
```

> **Checkpoint**
> **Models** lists the Foundry deployment, its **Aliases** tab shows an alias, and **Access** › **Keys** shows
> `app-first-call`.

<!-- track: cli | Azure CLI -->

### Look up the Foundry account

Use the account name and resource group to look up its resource ID and endpoint. No need to copy a long ID from
the portal.

```bash title="Bash"
# Read the Foundry account's resource ID and endpoint, which the provider and the model use
export FOUNDRY_ID="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)"
FOUNDRY_ENDPOINT="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query properties.endpoint -o tsv)"
export FOUNDRY_ENDPOINT="${FOUNDRY_ENDPOINT%/}/"    # the provider expects a trailing slash
echo "🆔 Foundry account ID: $FOUNDRY_ID"
echo "🌐 Foundry endpoint: $FOUNDRY_ENDPOINT"
```

```powershell title="PowerShell"
# Read the Foundry account's resource ID and endpoint, with the trailing slash that the provider expects
$FOUNDRY_ID       = az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query id -o tsv
$FOUNDRY_ENDPOINT = (az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query properties.endpoint -o tsv).TrimEnd('/') + '/'
Write-Host "🆔 Foundry account ID: $FOUNDRY_ID"
Write-Host "🌐 Foundry endpoint: $FOUNDRY_ENDPOINT"
```

### Grant the gateway access to the account

The portal import does three things for you: it grants the gateway's identity access to the account, creates the
provider, and registers the deployments. From the command line, you do each step yourself. First, give the gateway's
system-assigned identity the **Foundry User** role on the account.

```bash title="Bash"
# Read the principal ID of the gateway's system-assigned managed identity
PRINCIPAL_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query identity.principalId -o tsv)"
echo "👤 Gateway identity: $PRINCIPAL_ID"

# Give the identity the Foundry User role on the account, so that the gateway can call its deployments
az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope "$FOUNDRY_ID" --query id -o tsv &&
  echo "🔐 The gateway's identity has the Foundry User role on $FOUNDRY_ACCOUNT"
```

```powershell title="PowerShell"
# Read the principal ID of the gateway's system-assigned managed identity
$PRINCIPAL_ID = az aigateway show -g $RG -n $GATEWAY --query identity.principalId -o tsv
Write-Host "👤 Gateway identity: $PRINCIPAL_ID"

# Give the identity the Foundry User role on the account, so that the gateway can call its deployments
az role assignment create --assignee-object-id $PRINCIPAL_ID --assignee-principal-type ServicePrincipal `
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope $FOUNDRY_ID --query id -o tsv
if ($?) { Write-Host "🔐 The gateway's identity has the Foundry User role on $FOUNDRY_ACCOUNT" }
```

### Create the Foundry provider

The provider tells the gateway where the account is and to authenticate with its managed identity.

```bash title="Bash"
# Create a Foundry provider that points at the account and signs in with the gateway's managed identity
az aigateway model-provider create -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" \
  --kind Foundry --display-name "Foundry models" \
  --foundry "{endpoint:'$FOUNDRY_ENDPOINT',resourceIds:[$FOUNDRY_ID],authentication:{kind:ManagedIdentity,managedIdentity:{resource:'https://cognitiveservices.azure.com/'}}}" \
  --query "{name:name, kind:properties.kind, endpoint:properties.foundry.endpoint}" &&
  echo "🔌 Model provider $PROVIDER points at $FOUNDRY_ACCOUNT"
```

```powershell title="PowerShell"
# Create a Foundry provider that points at the account and signs in with the gateway's managed identity
az aigateway model-provider create -g $RG --gateway-name $GATEWAY -n $PROVIDER `
  --kind Foundry --display-name "Foundry models" `
  --foundry "{endpoint:'$FOUNDRY_ENDPOINT',resourceIds:[$FOUNDRY_ID],authentication:{kind:ManagedIdentity,managedIdentity:{resource:'https://cognitiveservices.azure.com/'}}}" `
  --query "{name:name, kind:properties.kind, endpoint:properties.foundry.endpoint}"
if ($?) { Write-Host "🔌 Model provider $PROVIDER points at $FOUNDRY_ACCOUNT" }
```

### Register the deployment

A backend model registers one deployment under the provider. Name it after the deployment.

```bash title="Bash"
# Register the deployment as a backend model under the provider, with the endpoints that apps can call
az aigateway model create -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$DEPLOYMENT" \
  --display-name "$DEPLOYMENT" --api-format OpenAIChatCompletions \
  --supported-endpoints /openai/v1/chat/completions /openai/v1/responses \
  --deployment-config "{resourceId:$FOUNDRY_ID/deployments/$DEPLOYMENT,modelName:$DEPLOYMENT}" \
  --query "{name:name, deployment:properties.deployment.modelName}" &&
  echo "✨ Model $DEPLOYMENT is registered under $PROVIDER"
```

```powershell title="PowerShell"
# Register the deployment as a backend model under the provider, with the endpoints that apps can call
az aigateway model create -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER -n $DEPLOYMENT `
  --display-name $DEPLOYMENT --api-format OpenAIChatCompletions `
  --supported-endpoints /openai/v1/chat/completions /openai/v1/responses `
  --deployment-config "{resourceId:$FOUNDRY_ID/deployments/$DEPLOYMENT,modelName:$DEPLOYMENT}" `
  --query "{name:name, deployment:properties.deployment.modelName}"
if ($?) { Write-Host "✨ Model $DEPLOYMENT is registered under $PROVIDER" }
```

`--deployment-config` uses the Azure CLI shorthand syntax, so the same value works in Bash and PowerShell.

To publish more deployments, repeat this step and the next one for each name that
`az cognitiveservices account deployment list -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query "[].name" -o tsv`
returns.

> [!TIP]
> `az aigateway model-provider create -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" --foundry-resource-id "$FOUNDRY_ID"`
> does the last three steps in one command for every deployment in the account, like the portal import: it grants
> the gateway's identity **Foundry User** on the account, creates the provider, and registers each deployment. You
> can run it again safely. It doesn't publish an alias, so you still run the next step. The
> [quick start](../quickstart/README.md) uses it. This lab creates each piece itself so you see how they fit together.

### Publish an alias

Clients send an alias in the request `model` field, not the backend model name. Publish one named after the
deployment that points at the model you registered.

```bash title="Bash"
# Name the alias after the deployment, and build the resource ID of the model that it points at
export AI_GATEWAY_MODEL="$DEPLOYMENT"
MODEL_ID="$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$DEPLOYMENT"

# Publish the alias, or update it if it exists, and print its name and the model that it points at
az aigateway model-alias set -g "$RG" --gateway-name "$GATEWAY" -n "$AI_GATEWAY_MODEL" \
  --backend-model resource-id="$MODEL_ID" \
  --query "{alias:properties.aliasName, target:properties.backendModels[0].resourceId}" &&
  echo "🔖 Alias $AI_GATEWAY_MODEL is ready"
```

```powershell title="PowerShell"
# Name the alias after the deployment, and build the resource ID of the model that it points at
$env:AI_GATEWAY_MODEL = $DEPLOYMENT
$MODEL_ID = "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$DEPLOYMENT"

# Publish the alias, or update it if it exists, and print its name and the model that it points at
az aigateway model-alias set -g $RG --gateway-name $GATEWAY -n $env:AI_GATEWAY_MODEL `
  --backend-model resource-id="$MODEL_ID" `
  --query "{alias:properties.aliasName, target:properties.backendModels[0].resourceId}"
if ($?) { Write-Host "🔖 Alias $env:AI_GATEWAY_MODEL is ready" }
```

`az aigateway model-alias set` creates the alias, or updates it if it exists, so you can run the step again. When
it creates the alias, it warns that the service doesn't enforce atomic alias creation. That's expected: it only
matters when two people create the same alias at the same time.

### Create a runtime API key

`api-key create` returns metadata only. Read the generated value with `list-secrets` straight into a variable so
it never appears on screen.

```bash title="Bash"
# Create a runtime API key for your app, which prints its name and state but not its value
az aigateway api-key create -g "$RG" --gateway-name "$GATEWAY" -n app-first-call \
  --query "{name:name, state:properties.state}" &&
  echo "🔑 API key app-first-call is ready"

# Read the key's value straight into an environment variable, so that it never shows on screen
AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets -g "$RG" --gateway-name "$GATEWAY" -n app-first-call \
  --query primaryKey -o tsv)" && export AI_GATEWAY_API_KEY
echo "🔑 Key: in AI_GATEWAY_API_KEY (${#AI_GATEWAY_API_KEY} characters, not shown)"
```

```powershell title="PowerShell"
# Create a runtime API key for your app, which prints its name and state but not its value
az aigateway api-key create -g $RG --gateway-name $GATEWAY -n app-first-call `
  --query "{name:name, state:properties.state}"
if ($?) { Write-Host "🔑 API key app-first-call is ready" }

# Read the key's value straight into an environment variable, so that it never shows on screen
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets -g $RG --gateway-name $GATEWAY -n app-first-call `
  --query primaryKey -o tsv
Write-Host "🔑 Key: in AI_GATEWAY_API_KEY ($($env:AI_GATEWAY_API_KEY.Length) characters, not shown)"
```

> **Checkpoint**
> `az aigateway model list -g "$RG" --gateway-name "$GATEWAY" --query "[].{name:name, provider:properties.providerKind}" -o table`
> lists your deployment with the provider `Foundry`, the alias command returned your model's ID as `target` and
> printed `🔖 Alias gpt-6-luna is ready`, and
> `az aigateway api-key list -g "$RG" --gateway-name "$GATEWAY" --query "[].{name:name, state:properties.state}" -o table`
> shows `app-first-call` as `active`, next to the built-in `master` key.

<!-- track: iac | Bicep + azd -->

**What you need:** the one-time setup from **Before you begin**. The template assigns a role, so you need **Owner** on
the subscription, or **Contributor** and **Role Based Access Control Administrator**. This track doesn't use your
gateway from lab 01: `azd up` creates a new one, so it works on its own.

### Review the templates

`infra/main.bicep` creates the resource group `rg-<environment name>` and composes three templates. It calls lab
01's [gateway.bicep](../01-provision-gateway/infra/gateway.bicep) for the gateway, `infra/foundry.bicep` for the
Foundry account and its `gpt-6-luna` deployment, and then `infra/publish-model.bicep` to publish the deployment
through the gateway:

<!-- include: infra/main.bicep -->

`infra/foundry.bicep` creates an Azure AI Services account with local key authentication disabled, and a
`gpt-6-luna` `GlobalStandard` deployment. Skip it in your own templates if you already have a deployment:

<!-- include: infra/foundry.bicep -->

`infra/publish-model.bicep` adds to the gateway. It grants the gateway's identity the **Foundry User** role on the
account (in the account's own resource group, with
[foundry-user-role.bicep](infra/foundry-user-role.bicep)), and only then creates a Foundry model provider that
authenticates with the managed identity. It registers the deployment as a backend model with a per-caller token
limit, publishes an alias, and creates a runtime API key. It only references the gateway and the account, so you
can also deploy it on its own to a gateway you already have, with `az deployment group create`:

<!-- include: infra/publish-model.bicep -->

### Deploy with azd up

Move into the lab's folder, create an azd environment named `aigw-lab02` in your current subscription, then provision
everything. It takes about three minutes.

```bash title="Bash"
# Move into the lab's folder, which holds the azd project
cd ~/aigateway/labs/02-first-model-call &&
  echo "📂 Lab folder: $(pwd)"

# Create an azd environment in your current subscription, so that azd doesn't prompt you
azd env new aigw-lab02 --location eastus2 --subscription "$(az account show --query id --output tsv)" &&
  echo "📝 azd environment aigw-lab02 deploys to eastus2"

# Provision the gateway, the Foundry deployment, the role, the provider, the model, the alias, and the key
azd up &&
  echo "🚀 Gateway $(azd env get-value AI_GATEWAY_NAME) is deployed"
```

```powershell title="PowerShell"
# Move into the lab's folder, which holds the azd project
Set-Location ~/aigateway/labs/02-first-model-call
if ($?) { Write-Host "📂 Lab folder: $(Get-Location)" }

# Create an azd environment in your current subscription, so that azd doesn't prompt you
azd env new aigw-lab02 --location eastus2 --subscription (az account show --query id --output tsv)
if ($?) { Write-Host "📝 azd environment aigw-lab02 deploys to eastus2" }

# Provision the gateway, the Foundry deployment, the role, the provider, the model, the alias, and the key
azd up
if ($?) { Write-Host "🚀 Gateway $(azd env get-value AI_GATEWAY_NAME) is deployed" }
```

For another region, pick one where AI Gateway and the `gpt-6-luna` model are available, as in [Find the available
regions](../SETUP.md#find-the-available-regions).

### Read the outputs and the key

Set the variables from **Before you begin**, which the next sections and **Verify** use, from azd's environment
values. Template outputs never contain the key value, so read it from the gateway straight into a variable, where
it never shows on screen.

```bash title="Bash"
# Read the names that the next sections and Verify use from azd's environment values
export RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
export GATEWAY="$(azd env get-value AI_GATEWAY_NAME)"
export GATEWAY_ID="$(azd env get-value AI_GATEWAY_ID)"
export FOUNDRY_RG="$RG"
export FOUNDRY_ACCOUNT="$(azd env get-value FOUNDRY_ACCOUNT_NAME)"
export DEPLOYMENT="$(azd env get-value AI_GATEWAY_BACKEND_MODEL)"
export PROVIDER="$(azd env get-value AI_GATEWAY_PROVIDER)"
echo "📝 Gateway $GATEWAY and Foundry account $FOUNDRY_ACCOUNT, in $RG"

# Read the gateway's runtime URL and the alias
export AI_GATEWAY_URL="$(azd env get-value AI_GATEWAY_URL)"
export AI_GATEWAY_MODEL="$(azd env get-value AI_GATEWAY_MODEL)"

# Read the key from the gateway, so that it never lands in a file or a deployment log
export AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" \
  --query primaryKey --output tsv)"
echo "🌐 Runtime URL: $AI_GATEWAY_URL"
echo "🔖 Model alias: $AI_GATEWAY_MODEL"
echo "🔑 Key: in AI_GATEWAY_API_KEY (${#AI_GATEWAY_API_KEY} characters, not shown)"
```

```powershell title="PowerShell"
# Read the names that the next sections and Verify use from azd's environment values
$RG                     = azd env get-value AZURE_RESOURCE_GROUP
$GATEWAY                = azd env get-value AI_GATEWAY_NAME
$GATEWAY_ID             = azd env get-value AI_GATEWAY_ID
$FOUNDRY_RG             = $RG
$FOUNDRY_ACCOUNT        = azd env get-value FOUNDRY_ACCOUNT_NAME
$DEPLOYMENT             = azd env get-value AI_GATEWAY_BACKEND_MODEL
$PROVIDER               = azd env get-value AI_GATEWAY_PROVIDER
Write-Host "📝 Gateway $GATEWAY and Foundry account $FOUNDRY_ACCOUNT, in $RG"

# Read the gateway's runtime URL and the alias
$env:AI_GATEWAY_URL     = azd env get-value AI_GATEWAY_URL
$env:AI_GATEWAY_MODEL   = azd env get-value AI_GATEWAY_MODEL

# Read the key from the gateway, so that it never lands in a file or a deployment log
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" `
  --query primaryKey --output tsv
Write-Host "🌐 Runtime URL: $env:AI_GATEWAY_URL"
Write-Host "🔖 Model alias: $env:AI_GATEWAY_MODEL"
Write-Host "🔑 Key: in AI_GATEWAY_API_KEY ($($env:AI_GATEWAY_API_KEY.Length) characters, not shown)"
```

> **Checkpoint**
> `azd up` ended with `SUCCESS`, and the last commands printed `🔖 Model alias: gpt-6-luna`. In the portal, select
> the new gateway in the gateway switcher: **Models** lists `gpt-6-luna`.

### Change the token limit

The template gives each caller 10,000 tokens per minute on the model. The value comes from the
`TOKENS_PER_MINUTE` azd environment value, with the default in `infra/main.parameters.json`. To change it, set the
value and provision again. Only the model changes.

```bash title="Bash"
# Set the tokens per minute that each caller can use on the model
azd env set TOKENS_PER_MINUTE 20000 &&
  echo "📝 TOKENS_PER_MINUTE is 20000"

# Provision again, which updates only the model
azd provision &&
  echo "🔐 Token limit of 20,000 tokens per minute per caller is on $DEPLOYMENT"
```

```powershell title="PowerShell"
# Set the tokens per minute that each caller can use on the model
azd env set TOKENS_PER_MINUTE 20000
if ($?) { Write-Host "📝 TOKENS_PER_MINUTE is 20000" }

# Provision again, which updates only the model
azd provision
if ($?) { Write-Host "🔐 Token limit of 20,000 tokens per minute per caller is on $DEPLOYMENT" }
```

<!-- /tracks -->

> [!IMPORTANT]
> Role assignments can take a few minutes to take effect. Until then, calls can fail with `403` from the
> backend. Wait and retry.

## Make your first call

Use the same alias and key everywhere. The gateway exposes the OpenAI-compatible base URL
`<gateway URL>/default/models/openai/v1`, so OpenAI SDKs only need a different base URL and the runtime key.

<!-- track: portal | Playground -->

### Try the model in Catalog

1. Select **Catalog** and pick your model.
2. Send a prompt in the built-in playground, for example `Write a one-sentence status update.`
3. Copy the endpoint and the code samples (cURL, PowerShell 7+, Python, TypeScript, and .NET) for your app.

> [!TIP]
> If the playground asks you to **Sign in again**, your portal session expired. Sign in and resend the prompt.

<!-- track: cli | curl and PowerShell -->

### Call Chat Completions

```bash title="Bash"
# Call Chat Completions through the gateway: the alias in model, and the runtime key in the api-key header
curl -sS "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Write a one-sentence status update.\"}]}" \
  | jq -r 'if .choices then "🤖 \(.choices[0].message.content)" else "🚨 \(.error.message // .)" end'
```

```powershell title="PowerShell"
# Build the request: the alias in model, and one user message
$body = @{
  model    = $env:AI_GATEWAY_MODEL
  messages = @(@{ role = "user"; content = "Write a one-sentence status update." })
} | ConvertTo-Json -Depth 5

# Call Chat Completions through the gateway, with the runtime key in the api-key header
$reply = Invoke-RestMethod -Method Post `
  -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body
if ($?) { Write-Host "🤖 $($reply.choices[0].message.content)" }
```

### Call the Responses API

```bash title="Bash"
# Call the Responses API through the gateway, with the same alias and key, and print the reply's text
curl -sS "${AI_GATEWAY_URL%/}/default/models/openai/v1/responses" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"input\":\"Summarize what an AI gateway does in one sentence.\"}" \
  | jq -r 'if .output then "🤖 \([.output[] | select(.type == "message") | .content[] | select(.type == "output_text") | .text] | join(""))" else "🚨 \(.error.message // .)" end'
```

```powershell title="PowerShell"
# Build the request: the alias in model, and the prompt in input
$body = @{ model = $env:AI_GATEWAY_MODEL; input = "Summarize what an AI gateway does in one sentence." } |
  ConvertTo-Json

# Call the Responses API through the gateway, and print the text of the reply's message
$reply = Invoke-RestMethod -Method Post `
  -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/responses" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body
if ($?) { Write-Host "🤖 $(($reply.output | Where-Object type -eq "message").content.text -join '')" }
```

### Run both calls with a script

The script prints the HTTP status and the reply for each interface, which makes failures easier to read.

<!-- include: infra/call-model.sh -->

On GitHub, open [infra/call-model.sh](infra/call-model.sh) or [infra/call-model.ps1](infra/call-model.ps1).

```bash title="Bash"
# Run the script, which calls both APIs and prints the HTTP status and the reply of each
echo "🤖 Calling $AI_GATEWAY_MODEL with Chat Completions and the Responses API:"
./infra/call-model.sh
```

```powershell title="PowerShell"
# Run the script, which calls both APIs and prints the HTTP status and the reply of each
Write-Host "🤖 Calling $env:AI_GATEWAY_MODEL with Chat Completions and the Responses API:"
./infra/call-model.ps1
```

<!-- track: code | Code -->

### Install the SDK

Each sample reads `AI_GATEWAY_URL`, `AI_GATEWAY_MODEL`, and `AI_GATEWAY_API_KEY` from the environment, so the
key never lives in code. Run the commands from the lab folder.

```bash title="Python"
# Move into the samples folder, and install the OpenAI SDK for Python that requirements.txt lists
cd infra
pip install -r requirements.txt     # the openai package
echo "📦 The OpenAI SDK for Python is installed"
```

```bash title="TypeScript"
# Move into the samples folder, and install the OpenAI SDK for TypeScript that package.json lists
cd infra
npm install                         # the openai npm package
echo "📦 The OpenAI SDK for TypeScript is installed"
```

```bash title="C#"
# Move into the .NET sample, and restore it: it uses only HttpClient and System.Text.Json
cd infra/dotnet
dotnet restore                      # no extra packages: HttpClient and System.Text.Json
echo "📦 The .NET sample is restored"
```

### Call the model from code

The OpenAI SDKs send their API key as `Authorization: Bearer <key>`, which the model endpoint accepts, so the
runtime key goes straight into the SDK. Don't also add an `api-key` default header: the gateway rejects a request
that has both with `400`. The .NET sample uses `HttpClient`, like the .NET samples in the AI Gateway docs, so it
sends the `api-key` header explicitly.

```python title="Python"
import os

from openai import OpenAI

gateway_url = os.environ["AI_GATEWAY_URL"].rstrip("/")
model = os.environ["AI_GATEWAY_MODEL"]

client = OpenAI(
    base_url=f"{gateway_url}/default/models/openai/v1",
    api_key=os.environ["AI_GATEWAY_API_KEY"],
)

response = client.responses.create(model=model, input="Write a one-sentence status update.")
print(f"Responses API:    {response.output_text}")

completion = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Describe an AI gateway in one sentence."}],
)
print(f"Chat Completions: {completion.choices[0].message.content}")
```

```typescript title="TypeScript"
import OpenAI from "openai";

const gatewayUrl = process.env.AI_GATEWAY_URL!.replace(/\/+$/, "");
const model = process.env.AI_GATEWAY_MODEL!;

const client = new OpenAI({
  baseURL: `${gatewayUrl}/default/models/openai/v1`,
  apiKey: process.env.AI_GATEWAY_API_KEY!,
});

const response = await client.responses.create({ model, input: "Write a one-sentence status update." });
console.log(`Responses API:    ${response.output_text}`);

const completion = await client.chat.completions.create({
  model,
  messages: [{ role: "user", content: "Describe an AI gateway in one sentence." }],
});
console.log(`Chat Completions: ${completion.choices[0].message.content}`);
```

```csharp title="C#"
using System.Net.Http.Json;
using System.Text.Json;

var gatewayUrl = Environment.GetEnvironmentVariable("AI_GATEWAY_URL")!.TrimEnd('/');
var model = Environment.GetEnvironmentVariable("AI_GATEWAY_MODEL")!;

using var http = new HttpClient { BaseAddress = new Uri($"{gatewayUrl}/default/models/openai/v1/") };
http.DefaultRequestHeaders.Add("api-key", Environment.GetEnvironmentVariable("AI_GATEWAY_API_KEY"));

using var reply = await http.PostAsJsonAsync("chat/completions", new
{
    model,
    messages = new[] { new { role = "user", content = "Describe an AI gateway in one sentence." } },
});
reply.EnsureSuccessStatusCode();
using var json = JsonDocument.Parse(await reply.Content.ReadAsStringAsync());
Console.WriteLine(json.RootElement.GetProperty("choices")[0].GetProperty("message").GetProperty("content").GetString());
```

The full samples in `infra` also call the Responses API from C# and print token usage: open
[first-call.py](infra/first-call.py), [first-call.ts](infra/first-call.ts), and
[dotnet/Program.cs](infra/dotnet/Program.cs).

### Run the sample

```bash title="Python"
# Run the sample, which calls the model through the gateway with the Responses API and Chat Completions
echo "🤖 Replies from the model, through the gateway:"
python first-call.py
```

```bash title="TypeScript"
# Run the sample, which calls the model through the gateway with the Responses API and Chat Completions
echo "🤖 Replies from the model, through the gateway:"
node first-call.ts      # Node.js 22.18 or later; on older versions run: npx tsx first-call.ts
```

```bash title="C#"
# Build and run the sample, which calls the model through the gateway with the Responses API and Chat Completions
echo "🤖 Replies from the model, through the gateway:"
dotnet run
```

Expected output (your text differs):

```text
🤖 Replies from the model, through the gateway:
Responses API:    All systems are running normally and the release is on track for Friday.
Chat Completions: An AI gateway is a governed entry point that routes, secures, and observes calls to AI models and tools.
```

<!-- /tracks -->

> **Checkpoint**
> The model answers through the gateway, and you never used a Foundry key or endpoint.

## Verify

<!-- steps -->

### Confirm the model is published

```bash title="Bash"
# List the models that the gateway publishes, with the kind of provider of each
echo "✨ Models on gateway $GATEWAY:"
az aigateway model list -g "$RG" --gateway-name "$GATEWAY" --query "[].{name:name, provider:properties.providerKind}" -o table
```

```powershell title="PowerShell"
# List the models that the gateway publishes, with the kind of provider of each
Write-Host "✨ Models on gateway ${GATEWAY}:"
az aigateway model list -g $RG --gateway-name $GATEWAY --query "[].{name:name, provider:properties.providerKind}" -o table
```

The list includes your deployment. In the portal, **Catalog** lists the model too.

### Get a 200 with the key

```bash title="Bash"
# Call Chat Completions with the key, and print only the HTTP status
STATUS="$(curl -sS -o /dev/null -w "%{http_code}" "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}")" &&
  echo "🔑 With the key: HTTP $STATUS"
```

```powershell title="PowerShell"
# Build a short request: the alias in model, and one user message
$body = @{ model = $env:AI_GATEWAY_MODEL; messages = @(@{ role = "user"; content = "ping" }) } | ConvertTo-Json -Depth 5

# Call Chat Completions with the key, and print only the HTTP status
$status = (Invoke-WebRequest -Method Post -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body -SkipHttpErrorCheck).StatusCode
if ($?) { Write-Host "🔑 With the key: HTTP $status" }
```

Expect `🔑 With the key: HTTP 200`.

### Get a 401 without the key

Send the same request without the `api-key` header. The gateway rejects it before any policy runs or the
backend is called.

```bash title="Bash"
# Send the same request without the api-key header, and print only the HTTP status
STATUS="$(curl -sS -o /dev/null -w "%{http_code}" "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}")" &&
  echo "🚦 Without a key: HTTP $STATUS"
```

```powershell title="PowerShell"
# Send the same request without the api-key header, and print only the HTTP status
$status = (Invoke-WebRequest -Method Post -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -ContentType "application/json" -Body $body -SkipHttpErrorCheck).StatusCode
if ($?) { Write-Host "🚦 Without a key: HTTP $status" }
```

Expect `🚦 Without a key: HTTP 401`.

### Check that the alias is what clients call

Change one character in `model` and resend the request with the key. The call fails with `404` and
`model_not_found` because `model` must match an alias exactly. Backend model names and Foundry deployment names
aren't callable unless an alias with that name exists.

<!-- /steps -->

> **Checkpoint**
> You got `200` with the key, `401` without it, and an error for a name that isn't an alias.

## Go further

- **Publish more deployments.** After you add deployments in Foundry, rerun the portal import, or repeat the
  CLI track's **Register the deployment** and **Publish an alias** steps for each new deployment.
- **Add a per-caller token limit.** The Bicep + azd track already sets `tokensPerMinute`, and its **Change the
  token limit** step changes it. Learn how limits behave in
  [Throttle tokens per caller with token limits](../06-token-limits/README.md).
- **Publish models from other providers.** Put OpenAI, Anthropic, AWS Bedrock, or Google Vertex AI models behind
  the same gateway in [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md).

## Clean up

The portal and CLI tracks of the next labs reuse the gateway, model, alias, and key, so keep them until you finish
the labs you plan to do.

<!-- track: cli | Portal and Azure CLI -->

### Delete what you published

When you're done with the labs, delete the key, the alias, and the provider, then remove the role assignment that
the gateway received on the Foundry account. Delete the alias first: deleting the provider also deletes its
models, but not the aliases that point at them. Deleting a model from the gateway doesn't delete the Foundry
deployment. The commands use the names from the CLI track. If you imported in the portal, use the provider
and alias names shown on **Models**.

```bash title="Bash"
# Delete the runtime API key, so that it stops working
az aigateway api-key delete -g "$RG" --gateway-name "$GATEWAY" -n app-first-call --yes &&
  echo "🚮 API key app-first-call is deleted"

# Delete the alias first: deleting the provider doesn't delete the aliases that point at its models
az aigateway model-alias delete -g "$RG" --gateway-name "$GATEWAY" -n "$DEPLOYMENT" --yes &&
  echo "🚮 Alias $DEPLOYMENT is deleted"

# Delete the provider, with its models. The Foundry deployment stays.
az aigateway model-provider delete -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" --yes &&
  echo "🚮 Model provider $PROVIDER is deleted"

# Read the principal ID of the gateway's identity, and the Foundry account's resource ID
PRINCIPAL_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query identity.principalId -o tsv)"
FOUNDRY_ID="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)"
echo "👤 Gateway identity: $PRINCIPAL_ID"

# Remove the Foundry User role that the gateway's identity has on the account
az role assignment delete --assignee "$PRINCIPAL_ID" --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope "$FOUNDRY_ID" &&
  echo "🚮 The gateway's Foundry User role on $FOUNDRY_ACCOUNT is removed"
```

```powershell title="PowerShell"
# Delete the runtime API key, so that it stops working
az aigateway api-key delete -g $RG --gateway-name $GATEWAY -n app-first-call --yes
if ($?) { Write-Host "🚮 API key app-first-call is deleted" }

# Delete the alias first: deleting the provider doesn't delete the aliases that point at its models
az aigateway model-alias delete -g $RG --gateway-name $GATEWAY -n $DEPLOYMENT --yes
if ($?) { Write-Host "🚮 Alias $DEPLOYMENT is deleted" }

# Delete the provider, with its models. The Foundry deployment stays.
az aigateway model-provider delete -g $RG --gateway-name $GATEWAY -n $PROVIDER --yes
if ($?) { Write-Host "🚮 Model provider $PROVIDER is deleted" }

# Read the principal ID of the gateway's identity, and the Foundry account's resource ID
$PRINCIPAL_ID = az aigateway show -g $RG -n $GATEWAY --query identity.principalId -o tsv
$FOUNDRY_ID = az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query id -o tsv
Write-Host "👤 Gateway identity: $PRINCIPAL_ID"

# Remove the Foundry User role that the gateway's identity has on the account
az role assignment delete --assignee $PRINCIPAL_ID --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope $FOUNDRY_ID
if ($?) { Write-Host "🚮 The gateway's Foundry User role on $FOUNDRY_ACCOUNT is removed" }
```

If you created the Foundry account with `infra/foundry.bicep`, delete its resource group with
`az group delete --name "$FOUNDRY_RG"`.

<!-- track: iac | Bicep + azd -->

### Delete everything azd created

You don't need to keep this gateway for the Bicep + azd tracks of later labs: each of them creates its own. If you
continue with the portal or CLI track of [lab 03](../03-multi-provider-aliases/README.md), you can keep it instead:
it has what that lab needs, the `gpt-6-luna` alias and the `app-first-call` key, in the resource group
`rg-aigw-lab02`.

Otherwise, in the `aigateway/labs/02-first-model-call` folder, delete the resource group with the gateway and the
Foundry account. [`--purge`](../SETUP.md#delete-what-azd-created) also purges the soft-deleted Foundry account. It
takes up to fifteen minutes.

```bash
# Delete everything that azd up created, purge the Foundry account, and don't ask you to confirm
azd down --purge --force &&
  echo "🚮 Everything that azd up created is deleted"
```

`azd down` doesn't touch the gateway from lab 01, because this track created its own.

<!-- /tracks -->

## Next steps

- [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md): add other providers and retarget aliases.
- [Issue and rotate runtime API keys](../10-api-keys/README.md): give each app its own key and rotate it safely.
- [Throttle tokens per caller with token limits](../06-token-limits/README.md): protect the deployment from noisy neighbors.
- Docs: [Access models through AI Gateway](https://ai.gateway.azure.com/docs/model-access) and
  [Microsoft Foundry and AI Gateway](https://ai.gateway.azure.com/docs/foundry).
