---
title: Your first model call in 5 minutes
summary: Learn the building blocks of Azure AI Gateway, create a gateway with a Microsoft Foundry model in the portal, the Azure CLI, or Bicep with azd, and make your first model call, all in about five minutes.
category: foundations
level: Beginner
duration: 5
tracks: [portal, cli, iac]
order: -1
status: new
illustration: diagrams/quickstart.svg
tags: [quick start, getting started, first call, gateway, model provider, alias, API key, portal, Azure CLI, Cloud Shell, azd, Bicep, infrastructure as code]
objectives:
  - Name the building blocks that every AI Gateway call goes through
  - Create a gateway, publish a Foundry model behind an alias, and create a runtime API key in the portal, the Azure CLI, or Bicep with azd
  - Make your first model call through the gateway the way an app does, with an alias and a runtime API key
prereqs: []
---

# Your first model call in 5 minutes

Azure AI Gateway gives your apps and agents one governed endpoint for models and tools. In five minutes you create a
gateway, put a Microsoft Foundry model behind it, and call that model the way an app does: with the gateway's URL, an
alias in the `model` field, and a runtime API key. Click through the AI Gateway portal, paste a few Azure CLI
commands into Azure Cloud Shell, or clone a Bicep template and deploy it with one `azd up`.

![Create the gateway, a Foundry model, a provider, an alias, and a runtime key in the AI Gateway portal, with the Azure CLI in Cloud Shell, or with a Bicep template and azd up. Then your app calls the alias with the key, and the gateway routes the call to Foundry with its managed identity](../assets/diagrams/quickstart.svg "Set up once, in the portal, in Cloud Shell, or with azd up. Then every call goes through the gateway: it checks the key, routes the alias, and signs in to Foundry with its own identity.")

## Before you begin

<!-- setup: permissions tools sign-in extension providers regions clone -->

Every later lab reuses this one-time setup. On the portal track, you need only
**Check your subscription and permissions**.

- Permissions to create resources and role assignments, for example **Owner**, or **Contributor** plus
  **Role Based Access Control Administrator**. The gateway gets a role on your Foundry account, so that it can call
  the model with its own identity.
- A region where `gpt-6-luna` is available too, because the Azure CLI and Bicep + azd tracks create the Foundry
  account in the gateway's region. The examples use `eastus2`.

## How it works

Every call that goes through AI Gateway uses the same building blocks. In this quick start you create one of each.

| Building block | What it does | In this quick start |
| :-- | :-- | :-- |
| **Gateway** | The Azure resource (`Microsoft.ApiManagement/aigateways`) that gives your apps one runtime URL for models and tools | Your gateway, at `<gateway-url>` |
| **Model provider** | A connection to a backend. The gateway signs in to it with its own managed identity, so your apps never hold a backend key | Your Foundry account. The Azure CLI and Bicep tracks name the provider `foundry-models` |
| **Model** | A backend deployment that the gateway can route to | The Foundry deployment `gpt-6-luna` |
| **Alias** | The name that apps send in the `model` field. The gateway routes the alias to one or more models | `<foundry-account-name>/gpt-6-luna` in the portal, `gpt-6-luna` in the Azure CLI and Bicep tracks |
| **Runtime API key** | Identifies the app that calls the gateway, for limits, cost, and monitoring. Azure RBAC with Microsoft Entra ID tokens is the keyless alternative | `app-first-call` |

Your app calls the OpenAI-compatible base URL `<gateway URL>/default/models/openai/v1`, so any OpenAI SDK works with
a different base URL and the runtime key. For the full tour, watch the 3-minute video in
[How Azure AI Gateway works](../00-how-ai-gateway-works/README.md).

## Create a gateway and make your first call

Pick one track. Each one creates the same building blocks, makes your first call through the gateway, and ends with
how to clean up.

<!-- track: portal | Portal -->

**What you need:** a browser, and a model deployment in a Microsoft Foundry account, for example `gpt-6-luna`.

<details>
<summary>No Foundry deployment yet? Create one in Cloud Shell.</summary>

Open [Azure Cloud Shell](https://shell.azure.com) in Bash and paste these commands. They create a Foundry account with
a `gpt-6-luna` deployment in a new resource group, in a minute or two. Then create the gateway in the same resource
group, so that you can clean up with one command. Model inference is billed per use.

```bash title="Bash"
# Name the resource group, and give the Foundry account a random, globally unique name
RG="rg-aigw-quickstart"; FOUNDRY="aigw$(openssl rand -hex 3)"

# Create the resource group that holds the Foundry account and, later, the gateway
az group create --name "$RG" --location eastus2 --output none &&
  echo "📦 Resource group $RG is ready in eastus2"

# Create the Foundry account, with a custom subdomain so that the gateway can sign in with Microsoft Entra ID
az cognitiveservices account create --resource-group "$RG" --name "$FOUNDRY" --location eastus2 \
  --kind AIServices --sku S0 --custom-domain "$FOUNDRY" --yes --output none &&
  echo "🏭 Foundry account $FOUNDRY is ready"

# Deploy gpt-6-luna with 10,000 tokens per minute of Global Standard capacity
az cognitiveservices account deployment create --resource-group "$RG" --name "$FOUNDRY" \
  --deployment-name gpt-6-luna --model-name gpt-6-luna --model-version 2026-09-22 --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 10 --output none &&
  echo "✨ Model deployment gpt-6-luna is ready"
echo "✅ Create the gateway in $RG, and import gpt-6-luna from $FOUNDRY"
```

</details>

### Create the gateway

1. Open the [AI Gateway portal](https://ai.gateway.azure.com) and sign in. For your first gateway, the portal opens
   **Create AI gateway** right away. Otherwise, open the gateway switcher in the top bar and select
   **Create new gateway**.

   ![The gateway switcher open in the top bar, with Recent gateways, View all gateways, and Create new gateway](../assets/screens/quickstart-01-switcher.webp "The gateway switcher lists your recent gateways. Create new gateway opens the Create AI gateway dialog.")

2. Enter a **Name**, or select **Generate a new name**. Then choose your **Subscription**, a **Resource group**, and
   a **Region**. For the resource group, select **New**, or select **Existing** and pick the resource group of your
   Foundry account, so that you can clean up both with one command.

   ![The Create AI gateway dialog with a name, the Existing resource group rg-aigw-quickstart, and the East US 2 region](../assets/screens/quickstart-02-create.webp "Create AI gateway: a generated name, the existing resource group of the Foundry account, and East US 2.")

3. Keep the **Advanced** defaults and select **Create gateway**. **All gateways** opens and shows the provisioning
   status, which moves from **Activating** to **Succeeded** in a few minutes. Then the portal selects your new
   gateway.

   ![All gateways with the banner Gateway creation is in progress and the new gateway in the Activating state](../assets/screens/quickstart-03-provisioning.webp "All gateways while the gateway provisions. You can keep using other gateways in the meantime.")

### Import the model from Foundry

1. **Home** opens with the **Set up your gateway** guide. Under **Add a model**, select
   **Add from Microsoft Foundry**.

   ![Home with the new gateway in the switcher and the Set up your gateway guide, with Add from Microsoft Foundry highlighted](../assets/screens/quickstart-04-home.webp "Set up your gateway walks you through three steps: add a model, test a model, and apply policies.")

   You can also start from **Models** › **Add** › **Models from Microsoft Foundry**.

   ![The Models page with the Add menu open on Models from Microsoft Foundry](../assets/screens/quickstart-05-add-menu.webp "Models › Add imports models from Microsoft Foundry or a custom provider, or creates an alias for a model that you already added.")

2. **Add models from Microsoft Foundry** discovers the model deployments in your subscriptions and selects all of
   them. In **Resource groups**, select only the resource group of your Foundry account. Then check that **Models**
   selects only your Foundry account with `gpt-6-luna`.
3. Keep **Managed identity** as the **Authentication method**, with the system-assigned managed identity, and keep
   **Create an alias for each model** selected. Then select **Add models**.

   ![Add models from Microsoft Foundry, filtered to one resource group, with Managed identity, Create an alias for each model, one selected Foundry account with gpt-6-luna, and the Add models button highlighted](../assets/screens/quickstart-06-import.webp "Filter by resource group, so that you import only the deployment that you need. The gateway calls Foundry with its managed identity.")

4. **Models** opens. The **Backend models** tab lists `gpt-6-luna`, and the **Aliases** tab shows the alias that
   apps call: `<foundry-account-name>/gpt-6-luna`. Note the alias.

   ![The Aliases tab of Models with the alias aigwb92bd1/gpt-6-luna, its backend model gpt-6-luna, and its provider](../assets/screens/quickstart-07-alias.webp "Each alias is named after the Foundry account and the deployment, and routes to the backend model gpt-6-luna.")

### Create a runtime API key

A key is the quickest way to start. Azure RBAC is the keyless alternative: grant the app the
**AI Gateway Models User** role in **Access** › **Entra ID**, and it sends a Microsoft Entra ID token instead of a
key. [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md) shows how.

1. Select **Access**, then the **Keys** tab, then **Create API key**.

   ![Access with the Keys tab, the Create API key button, and the new key app-first-call in the list](../assets/screens/quickstart-08-keys.webp "Access › Keys lists the built-in all-access subscription and your keys. After the next step, app-first-call appears here.")

2. Enter `app-first-call` as the **Key name**, then select **Create**.

   ![The Create API key dialog with the key name app-first-call and the Create button](../assets/screens/quickstart-09-key-create.webp "Give the key a name that identifies the app. Limits, cost, and monitoring use it.")

3. In **API key created successfully**, select **Copy & done** to copy the key. Keep it somewhere safe: you paste it
   in the next steps. You can view, rotate, or delete it later in **Access** › **Keys**.

   ![The API key created successfully dialog with a masked key, the key name, and the Copy & done button](../assets/screens/quickstart-10-key-done.webp "The key stays masked until you select Show. Copy & done copies it and closes the dialog.")

### Make your first call

Call the model through the gateway in the playground, with your new key, the way an app does.

1. Select **Catalog**, then select your model.

   ![The Catalog with the model card aigwb92bd1/gpt-6-luna](../assets/screens/quickstart-11-catalog.webp "The Catalog lists the models and MCP servers that apps can call through this gateway.")

2. Under **Authentication**, choose `app-first-call` as the **API key**, so that the playground calls the gateway
   with your new key. Then send a prompt, for example `In one sentence, what does an AI gateway do?`.

   ![The model page with the API key app-first-call, the prompt, and the model's reply](../assets/screens/quickstart-12-playground.webp "The playground calls the gateway's endpoint with the key that you choose, and shows the reply, the latency, and the tokens.")

3. Optional: to make the same call from code, select **Continue in code**. It shows the endpoint URL and snippets
   for cURL, the OpenAI SDK, LangChain, Vercel AI, the GitHub Copilot SDK, and Microsoft Agent Framework, plus a
   prompt that installs the AI Gateway plugin in your coding agent.

   ![Continue in code with the cURL snippet selected, which calls the alias with the api-key header](../assets/screens/quickstart-13-code.webp "The cURL snippet has your gateway's URL and alias, and reads the key from the AI_GATEWAY_API_KEY environment variable.")

To run the cURL snippet, open [Azure Cloud Shell](https://shell.azure.com) in Bash, paste your key at this prompt so
that it never shows on screen, and then paste the snippet:

```bash title="Bash"
# Read the key without showing it, and export it for the snippet
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
echo "🔑 Key: in AI_GATEWAY_API_KEY (${#AI_GATEWAY_API_KEY} characters, not shown)"
```

> **Checkpoint:** the playground answered with the key `app-first-call`. Your gateway is live, and your app never
> needs a Foundry key: only the gateway's managed identity calls Foundry.

### Clean up

To keep exploring, skip this step: [lab 03](../03-multi-provider-aliases/README.md) and the labs after it work on this
gateway. On the labs site, save the resource group and the gateway name in **Your values**. Otherwise, delete the
gateway.

1. Open the gateway switcher in the top bar and select **View all gateways**.

2. On your gateway's row, select **More actions** (**⋮**), and then select **Delete**.

   ![All gateways filtered to lucky-brook, with the More actions menu open on its row and Delete marked](../assets/screens/quickstart-14-delete.webp "The More actions menu on a gateway's row: open the gateway in the Azure portal, copy its resource ID, or delete it.")

3. To confirm, select **Delete** in the dialog. The row shows **Deleting** until Azure removes the gateway, in about
   five minutes.

   ![The dialog Delete "lucky-brook-5340"? with the Cancel and Delete buttons, and Delete marked](../assets/screens/quickstart-15-delete-confirm.webp "Deleting a gateway removes its models, aliases, keys, and policies. It can't be undone.")

Deleting the gateway keeps its resource group and your Foundry account. If you created them in Cloud Shell for this
quick start, delete the resource group and purge the Foundry account there too: deleted Foundry accounts stay
soft-deleted for 48 hours and keep counting against your quota until you purge them.

```bash title="Bash"
# Find the Foundry account in the resource group, so that you can purge it after the delete
FOUNDRY="$(az cognitiveservices account list --resource-group rg-aigw-quickstart --query "[0].name" --output tsv)"
echo "🏭 Foundry account: $FOUNDRY"

# Delete the resource group, with everything in it
az group delete --name rg-aigw-quickstart --yes &&
  echo "🚮 Resource group rg-aigw-quickstart is deleted"

# Purge the deleted Foundry account, so that it stops counting against your quota
az cognitiveservices account purge --name "$FOUNDRY" --resource-group rg-aigw-quickstart --location eastus2 &&
  echo "🚮 Foundry account $FOUNDRY is purged"
```

> **Checkpoint:** after you refresh the page, **All gateways** no longer lists your gateway.

<!-- track: cli | Azure CLI -->

**What you need:** only the one-time setup from **Before you begin**. The track creates the Foundry deployment for
you.

### Set your variables

Paste the block for your shell. It sets the names, and a random suffix keeps the gateway and Foundry account names
globally unique.

```bash title="Bash"
# Name the resources: the random suffix keeps the gateway and Foundry account names globally unique
export RG="rg-aigw-quickstart"
export LOCATION="eastus2"                     # or another region from Find the available regions
SUFFIX="$(openssl rand -hex 3)"
export GATEWAY="aigw-$SUFFIX"                 # part of the runtime URL
export FOUNDRY="aigw$SUFFIX"                  # the Foundry account and its subdomain
export DEPLOYMENT="gpt-6-luna"
export PROVIDER="foundry-models"

# Read your subscription ID, and build the gateway's resource ID that later commands use
export SUBSCRIPTION_ID="$(az account show --query id --output tsv)"
export GATEWAY_ID="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY"
echo "📝 Gateway $GATEWAY and Foundry account $FOUNDRY, in $RG ($LOCATION)"
echo "🆔 Subscription: $SUBSCRIPTION_ID"
```

```powershell title="PowerShell"
# Name the resources: the random suffix keeps the gateway and Foundry account names globally unique
$RG         = "rg-aigw-quickstart"
$LOCATION   = "eastus2"                       # or another region from Find the available regions
$SUFFIX     = [guid]::NewGuid().ToString("N").Substring(0, 6)
$GATEWAY    = "aigw-$SUFFIX"                  # part of the runtime URL
$FOUNDRY    = "aigw$SUFFIX"                   # the Foundry account and its subdomain
$DEPLOYMENT = "gpt-6-luna"
$PROVIDER   = "foundry-models"

# Read your subscription ID, and build the gateway's resource ID that later commands use
$SUBSCRIPTION_ID = az account show --query id --output tsv
$GATEWAY_ID      = "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY"
Write-Host "📝 Gateway $GATEWAY and Foundry account $FOUNDRY, in $RG ($LOCATION)"
Write-Host "🆔 Subscription: $SUBSCRIPTION_ID"
```

### Start creating the gateway

Create a resource group, and start creating the gateway. With `--no-wait`, Azure keeps provisioning the gateway in the
background, so you can move on right away. The portal and the Bicep template also create a companion connector gateway
for connector-based MCP tools. The quick start doesn't use connectors, so this track skips it.

```bash title="Bash"
# Create the resource group that holds the gateway and the Foundry account
az group create --name "$RG" --location "$LOCATION" --output none &&
  echo "📦 Resource group $RG is ready in $LOCATION"

# Start creating the gateway, with a system-assigned managed identity; --no-wait returns right away
az aigateway create --resource-group "$RG" --name "$GATEWAY" --location "$LOCATION" --system-assigned true --no-wait &&
  echo "⏳ Gateway $GATEWAY is provisioning in the background"
```

```powershell title="PowerShell"
# Create the resource group that holds the gateway and the Foundry account
az group create --name $RG --location $LOCATION --output none
if ($?) { Write-Host "📦 Resource group $RG is ready in $LOCATION" }

# Start creating the gateway, with a system-assigned managed identity; --no-wait returns right away
az aigateway create --resource-group $RG --name $GATEWAY --location $LOCATION --system-assigned true --no-wait
if ($?) { Write-Host "⏳ Gateway $GATEWAY is provisioning in the background" }
```

### Deploy the model in Foundry

While the gateway provisions, create a Foundry account with a `gpt-6-luna` deployment.

```bash title="Bash"
# Create the Foundry account, with a custom subdomain so that the gateway can sign in with Microsoft Entra ID,
# and keep its resource ID for the import in the next step
export FOUNDRY_ID="$(az cognitiveservices account create --resource-group "$RG" --name "$FOUNDRY" --location "$LOCATION" \
  --kind AIServices --sku S0 --custom-domain "$FOUNDRY" --yes --query id --output tsv)" &&
  echo "🏭 Foundry account $FOUNDRY is ready"

# Deploy gpt-6-luna with 10,000 tokens per minute of Global Standard capacity
az cognitiveservices account deployment create --resource-group "$RG" --name "$FOUNDRY" \
  --deployment-name "$DEPLOYMENT" --model-name gpt-6-luna --model-version 2026-09-22 --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 10 --output none &&
  echo "✨ Model deployment $DEPLOYMENT is ready"
```

```powershell title="PowerShell"
# Create the Foundry account, with a custom subdomain so that the gateway can sign in with Microsoft Entra ID,
# and keep its resource ID for the import in the next step
$FOUNDRY_ID = az cognitiveservices account create --resource-group $RG --name $FOUNDRY --location $LOCATION `
  --kind AIServices --sku S0 --custom-domain $FOUNDRY --yes --query id --output tsv
if ($?) { Write-Host "🏭 Foundry account $FOUNDRY is ready" }

# Deploy gpt-6-luna with 10,000 tokens per minute of Global Standard capacity
az cognitiveservices account deployment create --resource-group $RG --name $FOUNDRY `
  --deployment-name $DEPLOYMENT --model-name gpt-6-luna --model-version 2026-09-22 --model-format OpenAI `
  --sku-name GlobalStandard --sku-capacity 10 --output none
if ($?) { Write-Host "✨ Model deployment $DEPLOYMENT is ready" }
```

### Publish the model

Wait for the gateway, then publish the deployment with two commands:

- `az aigateway model-provider create --foundry-resource-id` imports the Foundry account. It gives the gateway's
  managed identity the **Foundry User** role on the account, adds a model provider that signs in with that identity,
  and adds a model for each deployment. The gateway calls the model with this identity, so your apps never hold a
  Foundry key.
- `az aigateway model-alias set` adds the alias that apps send in the `model` field, or updates it if it exists, so
  you can run the step again. The import doesn't add aliases.

```bash title="Bash"
# Wait until the gateway finishes provisioning
az aigateway wait --resource-group "$RG" --name "$GATEWAY" --created &&
  echo "🚀 Gateway $GATEWAY is ready"

# Import the Foundry account: role for the gateway's identity, a model provider, and a model for each deployment
MODELS="$(az aigateway model-provider create --resource-group "$RG" --gateway-name "$GATEWAY" --name "$PROVIDER" \
  --foundry-resource-id "$FOUNDRY_ID" --query "join(', ', models[].name)" --output tsv)" &&
  echo "🔌 Model provider $PROVIDER imported $MODELS from $FOUNDRY"

# Add or update the alias that apps send in the model field
ALIAS="$(az aigateway model-alias set --resource-group "$RG" --gateway-name "$GATEWAY" --name "$DEPLOYMENT" --only-show-errors \
  --backend-model resource-id="$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$DEPLOYMENT" \
  --query properties.aliasName --output tsv)" &&
  echo "🔖 Alias $ALIAS is ready"
```

```powershell title="PowerShell"
# Wait until the gateway finishes provisioning
az aigateway wait --resource-group $RG --name $GATEWAY --created
if ($?) { Write-Host "🚀 Gateway $GATEWAY is ready" }

# Import the Foundry account: role for the gateway's identity, a model provider, and a model for each deployment
$MODELS = az aigateway model-provider create --resource-group $RG --gateway-name $GATEWAY --name $PROVIDER `
  --foundry-resource-id $FOUNDRY_ID --query "models[].name" --output tsv
if ($?) { Write-Host "🔌 Model provider $PROVIDER imported $($MODELS -join ', ') from $FOUNDRY" }

# Add or update the alias that apps send in the model field
$ALIAS = az aigateway model-alias set --resource-group $RG --gateway-name $GATEWAY --name $DEPLOYMENT --only-show-errors `
  --backend-model resource-id="$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$DEPLOYMENT" `
  --query properties.aliasName --output tsv
if ($?) { Write-Host "🔖 Alias $ALIAS is ready" }
```

### Create a runtime API key

Create a key for your app. Then read the key, the gateway URL, and the alias into environment variables, so that
the key never shows on screen. Azure RBAC is the keyless alternative: grant the app the **AI Gateway Models User**
role, and it sends a Microsoft Entra ID token instead of a key, as
[Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md) shows.

```bash title="Bash"
# Create a runtime API key for your app
az aigateway api-key create --resource-group "$RG" --gateway-name "$GATEWAY" --name app-first-call --output none &&
  echo "🔑 API key app-first-call is ready"

# Read the key, the gateway's runtime URL, and the alias into environment variables
export AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets --resource-group "$RG" --gateway-name "$GATEWAY" \
  --name app-first-call --query primaryKey --output tsv)"
export AI_GATEWAY_URL="https://$(az aigateway show --resource-group "$RG" --name "$GATEWAY" --query properties.frontend.defaultHostname --output tsv)"
export AI_GATEWAY_MODEL="$DEPLOYMENT"
echo "🔑 Key: in AI_GATEWAY_API_KEY (${#AI_GATEWAY_API_KEY} characters, not shown)"
echo "🌐 Runtime URL: $AI_GATEWAY_URL"
echo "🔖 Model alias: $AI_GATEWAY_MODEL"
```

```powershell title="PowerShell"
# Create a runtime API key for your app
az aigateway api-key create --resource-group $RG --gateway-name $GATEWAY --name app-first-call --output none
if ($?) { Write-Host "🔑 API key app-first-call is ready" }

# Read the key, the gateway's runtime URL, and the alias into environment variables
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets --resource-group $RG --gateway-name $GATEWAY `
  --name app-first-call --query primaryKey --output tsv
$env:AI_GATEWAY_URL     = "https://" + (az aigateway show --resource-group $RG --name $GATEWAY --query properties.frontend.defaultHostname --output tsv)
$env:AI_GATEWAY_MODEL   = $DEPLOYMENT
Write-Host "🔑 Key: in AI_GATEWAY_API_KEY ($($env:AI_GATEWAY_API_KEY.Length) characters, not shown)"
Write-Host "🌐 Runtime URL: $env:AI_GATEWAY_URL"
Write-Host "🔖 Model alias: $env:AI_GATEWAY_MODEL"
```

> **Checkpoint:** the commands printed `🔖 Alias gpt-6-luna is ready` and your gateway's runtime URL, for example
> `🌐 Runtime URL: https://aigw-abc12-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com`.

### Make your first call

Send a Chat Completions request to the gateway's OpenAI-compatible base URL, the way an app does: the alias in the
`model` field and the key in the `api-key` header.

```bash title="Bash"
# Call the model through the gateway, the way an app does: the alias in model, and the key in the api-key header
curl -sS "$AI_GATEWAY_URL/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"In one sentence, what does an AI gateway do?\"}]}" \
  | jq -r 'if .choices then "🤖 \(.choices[0].message.content)" else "🚨 \(.error.message // .)" end'
```

```powershell title="PowerShell"
# Build the request: the alias in model, and one user message
$body = @{
  model    = $env:AI_GATEWAY_MODEL
  messages = @(@{ role = "user"; content = "In one sentence, what does an AI gateway do?" })
} | ConvertTo-Json -Depth 5

# Call the model through the gateway, the way an app does: with the key in the api-key header
$reply = Invoke-RestMethod -Method Post -Uri "$env:AI_GATEWAY_URL/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body
if ($?) { Write-Host "🤖 $($reply.choices[0].message.content)" }
```

> **Checkpoint:** the model answers in one sentence. Your gateway is live, and your app never needed a Foundry key:
> only the gateway's managed identity calls Foundry. If you get `403` or `404` in the first minute, the gateway's new
> role on the Foundry account is still taking effect. Wait a minute and run the call again.

To see what you created, open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway in the top
bar: **Models**, **Access** › **Keys**, and the **Catalog** playground.

### Clean up

To keep exploring, skip this step: [lab 03](../03-multi-provider-aliases/README.md) and the labs after it work on this
gateway. On the labs site, save the resource group and the gateway name (`$RG` and `$GATEWAY`) in **Your values**.
Otherwise, delete the resource group, which holds the gateway and the Foundry account. Then purge the Foundry account:
deleted Foundry accounts stay soft-deleted for 48 hours and keep counting against your quota until you purge them.

```bash title="Bash"
# Delete the resource group, with the gateway and the Foundry account in it
az group delete --name "$RG" --yes &&
  echo "🚮 Resource group $RG is deleted"

# Purge the deleted Foundry account, so that it stops counting against your quota
az cognitiveservices account purge --name "$FOUNDRY" --resource-group "$RG" --location "$LOCATION" &&
  echo "🚮 Foundry account $FOUNDRY is purged"
```

```powershell title="PowerShell"
# Delete the resource group, with the gateway and the Foundry account in it
az group delete --name $RG --yes
if ($?) { Write-Host "🚮 Resource group $RG is deleted" }

# Purge the deleted Foundry account, so that it stops counting against your quota
az cognitiveservices account purge --name $FOUNDRY --resource-group $RG --location $LOCATION
if ($?) { Write-Host "🚮 Foundry account $FOUNDRY is purged" }
```

If Cloud Shell timed out, set `RG`, `FOUNDRY`, and `LOCATION` again with the names that you used: the suffix in
**Set your variables** is random.

> **Checkpoint:** `az group exists --name $RG` prints `false`.

<!-- track: iac | Bicep + azd -->

**What you need:** only the one-time setup from **Before you begin**. The template creates the Foundry deployment for
you.

### Review the template

The template is a small azd project in the
[`labs/quickstart`](https://github.com/Azure/ai-gateway/tree/main/labs/quickstart) folder of the repo: an `azure.yaml`
and a Bicep file for each scope. `infra/main.bicep` creates the resource group `rg-<environment name>` and passes
unique names to `infra/resources.bicep`, which creates the building blocks in the same order as the other tracks:

<!-- include: infra/resources.bicep -->

### Deploy with azd up

Move into the quick start's folder, create an azd environment named `aigw-quickstart` in your current subscription,
so that azd doesn't prompt you, then provision everything with one command. It takes about three minutes.

```bash title="Bash"
# Move into the quick start's folder, which holds the azd project
cd ~/ai-gateway/labs/quickstart &&
  echo "📂 Template folder: $(pwd)"

# Create an azd environment in your current subscription, so that azd doesn't prompt you
azd env new aigw-quickstart --location eastus2 --subscription "$(az account show --query id --output tsv)" &&
  echo "📝 azd environment aigw-quickstart deploys to eastus2"

# Provision the gateway, the Foundry deployment, the provider, the model, the alias, and the key
azd up &&
  echo "🚀 Gateway deployed: $(azd env get-value AI_GATEWAY_URL)"
```

```powershell title="PowerShell"
# Move into the quick start's folder, which holds the azd project
Set-Location ~/ai-gateway/labs/quickstart
if ($?) { Write-Host "📂 Template folder: $(Get-Location)" }

# Create an azd environment in your current subscription, so that azd doesn't prompt you
azd env new aigw-quickstart --location eastus2 --subscription (az account show --query id --output tsv)
if ($?) { Write-Host "📝 azd environment aigw-quickstart deploys to eastus2" }

# Provision the gateway, the Foundry deployment, the provider, the model, the alias, and the key
azd up
if ($?) { Write-Host "🚀 Gateway deployed: $(azd env get-value AI_GATEWAY_URL)" }
```

For another region, use its name from [Find the available regions](../SETUP.md#find-the-available-regions).
azd saves the template's outputs, like the gateway URL and the alias, as environment values. The API key isn't an
output, so it never lands in a file or a deployment log.

### Read the URL, the alias, and the key

Read the outputs, and read the key from the gateway into an environment variable, so that it never shows on screen.
Azure RBAC is the keyless alternative to the key: grant the app the **AI Gateway Models User** role, and it sends a
Microsoft Entra ID token instead, as [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md) shows.

```bash title="Bash"
# Read the template's outputs: the gateway's runtime URL and the alias
export AI_GATEWAY_URL="$(azd env get-value AI_GATEWAY_URL)"
export AI_GATEWAY_MODEL="$(azd env get-value AI_GATEWAY_MODEL)"

# Read the key from the gateway, so that it never lands in a file or a deployment log
export AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets --ids "$(azd env get-value AI_GATEWAY_ID)/apiKeys/app-first-call" \
  --query primaryKey --output tsv)"
echo "🌐 Runtime URL: $AI_GATEWAY_URL"
echo "🔖 Model alias: $AI_GATEWAY_MODEL"
echo "🔑 Key: in AI_GATEWAY_API_KEY (${#AI_GATEWAY_API_KEY} characters, not shown)"
```

```powershell title="PowerShell"
# Read the template's outputs: the gateway's runtime URL, the alias, and the gateway's resource ID
$env:AI_GATEWAY_URL     = azd env get-value AI_GATEWAY_URL
$env:AI_GATEWAY_MODEL   = azd env get-value AI_GATEWAY_MODEL
$GATEWAY_ID             = azd env get-value AI_GATEWAY_ID

# Read the key from the gateway, so that it never lands in a file or a deployment log
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" `
  --query primaryKey --output tsv
Write-Host "🌐 Runtime URL: $env:AI_GATEWAY_URL"
Write-Host "🔖 Model alias: $env:AI_GATEWAY_MODEL"
Write-Host "🔑 Key: in AI_GATEWAY_API_KEY ($($env:AI_GATEWAY_API_KEY.Length) characters, not shown)"
```

> **Checkpoint:** `azd up` ended with `SUCCESS`, and the last commands printed your gateway's runtime URL, for example
> `🌐 Runtime URL: https://aigw-abc12-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com`.

### Make your first call

Send a Chat Completions request to the gateway's OpenAI-compatible base URL, the way an app does: the alias in the
`model` field and the key in the `api-key` header.

```bash title="Bash"
# Call the model through the gateway, the way an app does: the alias in model, and the key in the api-key header
curl -sS "$AI_GATEWAY_URL/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"In one sentence, what does an AI gateway do?\"}]}" \
  | jq -r 'if .choices then "🤖 \(.choices[0].message.content)" else "🚨 \(.error.message // .)" end'
```

```powershell title="PowerShell"
# Build the request: the alias in model, and one user message
$body = @{
  model    = $env:AI_GATEWAY_MODEL
  messages = @(@{ role = "user"; content = "In one sentence, what does an AI gateway do?" })
} | ConvertTo-Json -Depth 5

# Call the model through the gateway, the way an app does: with the key in the api-key header
$reply = Invoke-RestMethod -Method Post -Uri "$env:AI_GATEWAY_URL/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body
if ($?) { Write-Host "🤖 $($reply.choices[0].message.content)" }
```

> **Checkpoint:** the model answers in one sentence. Your gateway is live, and your app never needed a Foundry key:
> only the gateway's managed identity calls Foundry. If you get `403` or `404` in the first minute, the gateway's new
> role on the Foundry account is still taking effect. Wait a minute and run the call again.

To see what you created, open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway in the top
bar: **Models**, **Access** › **Keys**, and the **Catalog** playground.

### Clean up

To keep exploring, skip this step: [lab 03](../03-multi-provider-aliases/README.md) and the labs after it work on this
gateway. Otherwise, in the `ai-gateway/labs/quickstart` folder, delete everything that `azd up` created. `--purge` also purges
the Foundry account, which would otherwise stay soft-deleted for 48 hours and keep counting against your quota. It
takes about ten minutes.

```bash title="Bash"
# Delete everything that azd up created, and purge the Foundry account
azd down --purge --force &&
  echo "🚮 Everything that azd up created is deleted"
```

```powershell title="PowerShell"
# Delete everything that azd up created, and purge the Foundry account
azd down --purge --force
if ($?) { Write-Host "🚮 Everything that azd up created is deleted" }
```

> **Checkpoint:** `azd down` ended with `SUCCESS`. The resource group `rg-aigw-quickstart` is gone, and you can delete
> the `ai-gateway` folder.

<!-- /tracks -->

## Next steps

- [How Azure AI Gateway works](../00-how-ai-gateway-works/README.md): a 3-minute video and a guided tour of every building block.
- [Provision your AI Gateway](../01-provision-gateway/README.md) and [Publish a Foundry model and make your first call](../02-first-model-call/README.md): the same setup in depth, with Bicep, the Responses API, and more SDKs.
- [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md): put models from several providers behind names your apps keep.
- [Throttle tokens per caller with token limits](../06-token-limits/README.md): give every app its own allowance.
- [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md): replace the API key with Entra ID tokens and Azure RBAC roles.
