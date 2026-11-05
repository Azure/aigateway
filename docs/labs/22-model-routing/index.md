---
title: Route an alias across models by priority and weight
summary: Put two Foundry models behind one alias, canary a new model version with an 80/20 weighted split, then prefer one model by priority, all without changing the model name that clients send.
category: models
level: Intermediate
duration: 25
tracks: [portal, cli, iac]
order: 3.5
status: new
illustration: diagrams/alias-routing.svg
tags: [model alias, routing, priority, weight, canary, A/B test, load balancing, provisioned throughput]
objectives:
  - Explain how priority and weight decide which backend model serves a request
  - Put two backend models behind one alias with an 80/20 weighted split
  - Tell which backend model served each request from the response
  - Prefer one backend model by priority, then promote the other without changing clients
prereqs:
  - 02-first-model-call
---

# Route an alias across models by priority and weight

Your team wants to try `gpt-6.1-sol`, but every app already sends `"model": "chat"`, and nobody wants a big-bang
switch. In this lab you put the current model and the new one behind the same alias, send a fifth of the traffic
to the new model, count where the requests land, and then use priority to choose which model is preferred. The
apps never change the model name they send.

![Clients call one alias. The gateway prefers the backend models with the lowest priority number and splits their traffic by weight](../assets/diagrams/alias-routing.svg "Priority picks the tier. Weight splits the traffic inside it.")

<!-- widget: alias-routing {"alias":"chat"} -->

## Before you begin

<!-- setup: tools sign-in extension clone -->

> [!TIP]
> On the **Bicep + azd** track, `azd up` creates its own gateway, both models, the alias, and a key, so you can skip
> this section. You need only the one-time setup above.

- Complete [Publish a Foundry model and make your first call](../02-first-model-call/README.md). You need the
  gateway, a runtime API key, and the `gpt-6-luna` backend model. Lab 02 also gave the gateway the
  **Foundry User** role on your Foundry account, which covers the new deployment in this lab.
- Permission to change the gateway, for example **Contributor** on its resource group, and to create deployments
  in the Foundry account.
- Optional: [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md)
  explains aliases in more depth.
- Run the scripts and samples from the lab's folder, `~/aigateway/labs/22-model-routing`.

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
# Name your gateway, the Foundry account from lab 02, the two backend models, and the alias that clients call
export RG="<resource-group>"
export GATEWAY="<gateway>"
export FOUNDRY_RG="<foundry-resource-group>"     # resource group of the Foundry account from lab 02
export FOUNDRY_ACCOUNT="<foundry-account-name>"
export PROVIDER="foundry-models"                 # the gateway provider that holds gpt-6-luna
export PRIMARY="gpt-6-luna"                      # the backend model that serves today's traffic
export CANDIDATE="gpt-6.1-sol"                   # the new model to try
export CANDIDATE_VERSION="2026-09-29"
export ALIAS="chat"                              # the name that clients send in "model"
echo "📝 Alias $ALIAS will route between $PRIMARY and $CANDIDATE on gateway $GATEWAY in $RG"

# Read the resource IDs of the gateway and the Foundry account, and the gateway's runtime URL
export GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"
export FOUNDRY_ID="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)"
export AI_GATEWAY_URL="https://$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
echo "🆔 Gateway: $GATEWAY_ID"
echo "🆔 Foundry account: $FOUNDRY_ID"
echo "🌐 Runtime URL: $AI_GATEWAY_URL"

# Paste the gateway runtime key from lab 02 without showing it, and don't commit it or write it to a file
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
echo "🔑 Key: in AI_GATEWAY_API_KEY (${#AI_GATEWAY_API_KEY} characters, not shown)"
```

```powershell title="PowerShell"
# Name your gateway, the Foundry account from lab 02, the two backend models, and the alias that clients call
$RG                = "<resource-group>"
$GATEWAY           = "<gateway>"
$FOUNDRY_RG        = "<foundry-resource-group>"    # resource group of the Foundry account from lab 02
$FOUNDRY_ACCOUNT   = "<foundry-account-name>"
$PROVIDER          = "foundry-models"              # the gateway provider that holds gpt-6-luna
$PRIMARY           = "gpt-6-luna"                  # the backend model that serves today's traffic
$CANDIDATE         = "gpt-6.1-sol"                 # the new model to try
$CANDIDATE_VERSION = "2026-09-29"
$ALIAS             = "chat"                        # the name that clients send in "model"
Write-Host "📝 Alias $ALIAS will route between $PRIMARY and $CANDIDATE on gateway $GATEWAY in $RG"

# Read the resource IDs of the gateway and the Foundry account, and the gateway's runtime URL
$GATEWAY_ID = az aigateway show -g $RG -n $GATEWAY --query id -o tsv
$FOUNDRY_ID = az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query id -o tsv
$env:AI_GATEWAY_URL = "https://$(az aigateway show -g $RG -n $GATEWAY --query properties.frontend.defaultHostname -o tsv)"
Write-Host "🆔 Gateway: $GATEWAY_ID"
Write-Host "🆔 Foundry account: $FOUNDRY_ID"
Write-Host "🌐 Runtime URL: $env:AI_GATEWAY_URL"

# Paste the gateway runtime key from lab 02 without showing it, and don't commit it or write it to a file
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
Write-Host "🔑 Key: in AI_GATEWAY_API_KEY ($($env:AI_GATEWAY_API_KEY.Length) characters, not shown)"
```

The CLI and Bicep tracks of lab 02 name the provider `foundry-models`. A portal import names it after your
Foundry account. To check, list the backend models. The **Provider** column shows the provider of each one.

```bash title="Bash"
# List the backend models on the gateway, with the provider that holds each one
echo "✨ Backend models on $GATEWAY:"
az aigateway model list -g "$RG" --gateway-name "$GATEWAY" -o table
```

```powershell title="PowerShell"
# List the backend models on the gateway, with the provider that holds each one
Write-Host "✨ Backend models on ${GATEWAY}:"
az aigateway model list -g $RG --gateway-name $GATEWAY -o table
```

Deploy the candidate model in the same Foundry account as `gpt-6-luna`. Pick a region where the model is
available. Model inference is billed per use.

```bash title="Bash"
# Deploy the candidate model next to gpt-6-luna, with 10,000 tokens per minute of Global Standard capacity
az cognitiveservices account deployment create -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" \
  --deployment-name "$CANDIDATE" --model-name "$CANDIDATE" --model-version "$CANDIDATE_VERSION" \
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10 \
  --query "{name:name, state:properties.provisioningState}" &&
  echo "✨ Model deployment $CANDIDATE is ready in $FOUNDRY_ACCOUNT"
```

```powershell title="PowerShell"
# Deploy the candidate model next to gpt-6-luna, with 10,000 tokens per minute of Global Standard capacity
az cognitiveservices account deployment create -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT `
  --deployment-name $CANDIDATE --model-name $CANDIDATE --model-version $CANDIDATE_VERSION `
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10 `
  --query "{name:name, state:properties.provisioningState}"
if ($?) { Write-Host "✨ Model deployment $CANDIDATE is ready in $FOUNDRY_ACCOUNT" }
```

## How it works

An alias holds a list of backend models. Each one has a priority and a weight:

| Setting | Values | Default | What it does |
|---|---|---|---|
| **Priority** | Whole number from 0 to 100 | `0` | Lower numbers are preferred. Requests go to the backend models with the lowest priority number. |
| **Weight** | Whole number from 1 to 100 | `1` | Splits traffic among the backend models that share a priority, in proportion to their weights. |

A backend model's **Share within priority** is its weight divided by the sum of the weights at its priority.
Weights `80` and `20` give 80% and 20%; weights `3` and `1` give 75% and 25%. With one backend model, the alias
behaves like the single-target aliases of labs 02 and 03.

Pick the values from the job you need to do:

| Scenario | Priority | Weight |
|---|---|---|
| **Canary a new model version** | Same for both | Small share for the new version, for example `95` and `5`, then raise it |
| **A/B test two models** | Same for both | Equal, for example `50` and `50` |
| **Balance deployments** across regions or providers | Same for all | In proportion to each deployment's capacity, for example `3` and `1` |
| **Prefer purchased capacity** | Provisioned deployment `0`, pay-as-you-go `1` | Any |

A few rules keep every request answerable:

- Each backend model can appear only once in an alias.
- All backend models must support at least one interface in common, for example **OpenAI Chat Completions**.
  Mixing an Anthropic Messages model with an OpenAI model in one alias fails.
- The response tells you which backend served the request: the `model` field holds the backend's model name and
  version, for example `gpt-6.1-sol-2026-09-29`, and Foundry models also return an `x-ms-served-model` header.

> [!IMPORTANT]
> Priority sets a preference, not a guaranteed failover. In our tests, when the preferred backend returned an error
> such as `429` or `404`, the gateway passed that error to the client instead of retrying a lower-priority
> backend. Test how your gateway behaves under throttling before you rely on priority for
> availability, and keep retries in your clients.

## Split traffic 80/20 between two models

Register the candidate model in the gateway, then create the `chat` alias with both models at priority `0` and
weights `80` and `20`.

<!-- track: portal | Portal -->

### Import the candidate model

1. Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway in the top bar.
2. Select **Models** › **Add** › **Models from Microsoft Foundry**.
3. Select the subscription and resource group of your Foundry account, then select the `gpt-6.1-sol`
   deployment. Keep **Managed identity** as the **Authentication method**.
4. Select **Add models**. If the wizard also creates an alias named after the model, keep it; this lab doesn't
   use it.

### Create the chat alias

1. Select **Models** › **Aliases** › **Add alias**.
2. On **Basics**, set **Alias name** to `chat` and **Description** to `Canary: 80/20 between the current and the
   new model`. Select **Next**.
3. On **Select models**, select `gpt-6-luna` and `gpt-6.1-sol` in **Available backend models**. Select **Next**.
4. On **Priority and weights**, keep **Priority** at `0` for both models. Set **Weight** to `80` for
   `gpt-6-luna` and `20` for `gpt-6.1-sol`. **Share within priority** shows `80%` and `20%`. Select **Next**.
5. On **Review**, check the shares, then select **Create**.

![The Priority and weights step of Create alias, with Priority, Weight, and Share within priority columns for each backend model](../assets/screens/models-alias-routing.png "Priority and weights. This example from the product documentation uses three GPT-4o deployments: one at priority 0, and two at priority 1 that split 75/25.")

> **Checkpoint**
> **Models** › **Aliases** lists `chat`. Its **Backend models** tab shows `gpt-6-luna` and `gpt-6.1-sol`, both at
> priority `0`, with weights `80` and `20`.

<!-- track: cli | Azure CLI -->

### Register the candidate model

A backend model registers one deployment under the provider. This is the same command as in lab 02, with the
model version.

```bash title="Bash"
# Register the candidate deployment as a backend model under the provider, with its model version
az aigateway model create -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$CANDIDATE" \
  --display-name "$CANDIDATE" --api-format OpenAIChatCompletions \
  --supported-endpoints /openai/v1/chat/completions /openai/v1/responses \
  --deployment-config "{resourceId:$FOUNDRY_ID/deployments/$CANDIDATE,modelName:$CANDIDATE,modelVersion:$CANDIDATE_VERSION}" \
  --query "{name:name, version:properties.deployment.modelVersion}" &&
  echo "✨ Model $CANDIDATE is published through $PROVIDER"
```

```powershell title="PowerShell"
# Register the candidate deployment as a backend model under the provider, with its model version
az aigateway model create -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER -n $CANDIDATE `
  --display-name $CANDIDATE --api-format OpenAIChatCompletions `
  --supported-endpoints /openai/v1/chat/completions /openai/v1/responses `
  --deployment-config "{resourceId:$FOUNDRY_ID/deployments/$CANDIDATE,modelName:$CANDIDATE,modelVersion:$CANDIDATE_VERSION}" `
  --query "{name:name, version:properties.deployment.modelVersion}"
if ($?) { Write-Host "✨ Model $CANDIDATE is published through $PROVIDER" }
```

### Create the chat alias

Each `--backend-model` adds an entry to the alias's `backendModels` list, with a `resource-id`, a `priority`, and
a `weight`. With more than one backend model, each entry needs both a priority and a weight.

```bash title="Bash"
# Build the resource ID prefix of the provider's backend models, which each --backend-model entry uses
export MODELS="$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models"

# Create or update the alias with both backend models at priority 0 and weights 80 and 20, then print the routing
echo "🔖 Alias $ALIAS routes to:"
az aigateway model-alias set -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" \
  --description "Canary: 80/20 between the current and the new model" \
  --backend-model resource-id="$MODELS/$PRIMARY" priority=0 weight=80 \
  --backend-model resource-id="$MODELS/$CANDIDATE" priority=0 weight=20 \
  --only-show-errors --query properties.backendModels -o json |
  jq -r '.[] | "\(.resourceId | split("/") | last)  priority \(.priority)  weight \(.weight)"'
```

```powershell title="PowerShell"
# Build the resource ID prefix of the provider's backend models, which each --backend-model entry uses
$MODELS = "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models"

# Create or update the alias with both backend models at priority 0 and weights 80 and 20, then print the routing
Write-Host "🔖 Alias $ALIAS routes to:"
az aigateway model-alias set -g $RG --gateway-name $GATEWAY -n $ALIAS `
  --description "Canary: 80/20 between the current and the new model" `
  --backend-model resource-id="$MODELS/$PRIMARY" priority=0 weight=80 `
  --backend-model resource-id="$MODELS/$CANDIDATE" priority=0 weight=20 `
  --only-show-errors --query properties.backendModels -o json |
  ConvertFrom-Json | ForEach-Object { '{0}  priority {1}  weight {2}' -f ($_.resourceId -split '/')[-1], $_.priority, $_.weight }
```

`az aigateway model-alias set` creates the alias, or updates it if it exists, so you can run the step again.

> **Checkpoint**
> The output shows `gpt-6-luna  priority 0  weight 80` and `gpt-6.1-sol  priority 0  weight 20`.

<!-- track: iac | Bicep + azd -->

**What you need:** only the one-time setup from **Before you begin**. This track doesn't use your gateway from lab 02:
`azd up` creates a new one, so it works on its own.

### Review the templates

`infra/main.bicep` creates the resource group `rg-<environment name>` and calls the quick start's
[resources.bicep](../quickstart/infra/resources.bicep) for the gateway, `gpt-6-luna`, its default alias, and the
`app-first-call` key. Then it deploys the candidate model in the same Foundry account and publishes the `chat`
alias:

<!-- include: infra/main.bicep -->

`infra/candidate-deployment.bicep` deploys `gpt-6.1-sol` next to `gpt-6-luna`. The gateway's **Foundry User** role
on the account already covers it:

<!-- include: infra/candidate-deployment.bicep -->

`infra/alias-routing.bicep` registers the candidate deployment under the existing provider and publishes the alias.
It only references `gpt-6-luna`, so that model's settings stay as they are. Its `strategy` parameter switches
between a weighted split and a priority preference. You can also deploy it on its own to the gateway from lab 02:

<!-- include: infra/alias-routing.bicep -->

### Deploy with azd up

Move into the lab's folder, create an azd environment named `aigw-lab22` in your current subscription, then provision
everything. It takes about five minutes.

```bash title="Bash"
# Move into the lab's folder, which holds the azd project
cd ~/aigateway/labs/22-model-routing &&
  echo "📂 Lab folder: $(pwd)"

# Create an azd environment named aigw-lab22 in your current subscription, so that azd doesn't prompt you
azd env new aigw-lab22 --location eastus2 --subscription "$(az account show --query id --output tsv)" &&
  echo "📝 azd environment aigw-lab22 deploys to eastus2"

# Provision the resource group, the gateway, the Foundry account with both models, the chat alias, and the key
azd up &&
  echo "🚀 Gateway deployed: $(azd env get-value AI_GATEWAY_URL)"
```

```powershell title="PowerShell"
# Move into the lab's folder, which holds the azd project
Set-Location ~/aigateway/labs/22-model-routing
if ($?) { Write-Host "📂 Lab folder: $(Get-Location)" }

# Create an azd environment named aigw-lab22 in your current subscription, so that azd doesn't prompt you
azd env new aigw-lab22 --location eastus2 --subscription (az account show --query id --output tsv)
if ($?) { Write-Host "📝 azd environment aigw-lab22 deploys to eastus2" }

# Provision the resource group, the gateway, the Foundry account with both models, the chat alias, and the key
azd up
if ($?) { Write-Host "🚀 Gateway deployed: $(azd env get-value AI_GATEWAY_URL)" }
```

For another region, pick one where AI Gateway and the `gpt-6-luna` and `gpt-6.1-sol` models are available, as in [Find
the available regions](../SETUP.md#find-the-available-regions). The parameters come from azd
environment values, with the defaults in `infra/main.parameters.json`: `ROUTING_STRATEGY` (`weighted`),
`ROUTING_CANDIDATE_WEIGHT` (`20`), `CANDIDATE_MODEL` (`gpt-6.1-sol`), and `CANDIDATE_MODEL_VERSION` (`2026-09-29`).

### Read the outputs and the key

Set the variables that the next sections and **Verify** use from azd's environment values, read the key from the
gateway so that it never shows on screen, then print the alias's routes.

```bash title="Bash"
# Read azd's outputs into the variables that the next sections use, and build the backend models' ID prefix
export RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
export GATEWAY="$(azd env get-value AI_GATEWAY_NAME)"
export GATEWAY_ID="$(azd env get-value AI_GATEWAY_ID)"
export PROVIDER="$(azd env get-value AI_GATEWAY_PROVIDER)"
export PRIMARY="$(azd env get-value AI_GATEWAY_BACKEND_MODEL)"
export CANDIDATE="$(azd env get-value AI_GATEWAY_CANDIDATE_MODEL)"
export ALIAS="$(azd env get-value AI_GATEWAY_MODEL)"
export MODELS="$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models"
export AI_GATEWAY_URL="$(azd env get-value AI_GATEWAY_URL)"
echo "📝 Alias $ALIAS routes between $PRIMARY and $CANDIDATE on gateway $GATEWAY in $RG"
echo "🌐 Runtime URL: $AI_GATEWAY_URL"

# Read the app-first-call key from the gateway, so that it never shows on screen or lands in a file
export AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" \
  --query primaryKey --output tsv)"
echo "🔑 Key: in AI_GATEWAY_API_KEY (${#AI_GATEWAY_API_KEY} characters, not shown)"

# Print the alias's backend models, with the priority and the weight of each one
echo "🔖 Alias $ALIAS routes to:"
az aigateway model-alias show -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" --query properties.backendModels -o json |
  jq -r '.[] | "\(.resourceId | split("/") | last)  priority \(.priority)  weight \(.weight)"'
```

```powershell title="PowerShell"
# Read azd's outputs into the variables that the next sections use, and build the backend models' ID prefix
$RG                     = azd env get-value AZURE_RESOURCE_GROUP
$GATEWAY                = azd env get-value AI_GATEWAY_NAME
$GATEWAY_ID             = azd env get-value AI_GATEWAY_ID
$PROVIDER               = azd env get-value AI_GATEWAY_PROVIDER
$PRIMARY                = azd env get-value AI_GATEWAY_BACKEND_MODEL
$CANDIDATE              = azd env get-value AI_GATEWAY_CANDIDATE_MODEL
$ALIAS                  = azd env get-value AI_GATEWAY_MODEL
$MODELS                 = "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models"
$env:AI_GATEWAY_URL     = azd env get-value AI_GATEWAY_URL
Write-Host "📝 Alias $ALIAS routes between $PRIMARY and $CANDIDATE on gateway $GATEWAY in $RG"
Write-Host "🌐 Runtime URL: $env:AI_GATEWAY_URL"

# Read the app-first-call key from the gateway, so that it never shows on screen or lands in a file
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" `
  --query primaryKey --output tsv
Write-Host "🔑 Key: in AI_GATEWAY_API_KEY ($($env:AI_GATEWAY_API_KEY.Length) characters, not shown)"

# Print the alias's backend models, with the priority and the weight of each one
Write-Host "🔖 Alias $ALIAS routes to:"
az aigateway model-alias show -g $RG --gateway-name $GATEWAY -n $ALIAS --query properties.backendModels -o json |
  ConvertFrom-Json | ForEach-Object { '{0}  priority {1}  weight {2}' -f ($_.resourceId -split '/')[-1], $_.priority, $_.weight }
```

> **Checkpoint**
> `azd up` ended with `SUCCESS`, and the last command printed `gpt-6-luna  priority 0  weight 80` and
> `gpt-6.1-sol  priority 0  weight 20`.

<!-- /tracks -->

## Watch the split

Send 20 requests to `chat` and count which backend model answered each one. The script sends one request every
half second and reads the `model` field of each response.

```bash title="Bash"
# Send 20 requests to the alias, one every half second, and count which backend model answered each one
echo "📊 Counting the backend models that serve $ALIAS, one request every half second"
./infra/count-models.sh "$ALIAS" 20
```

```powershell title="PowerShell"
# Send 20 requests to the alias, one every half second, and count which backend model answered each one
Write-Host "📊 Counting the backend models that serve $ALIAS, one request every half second"
./infra/count-models.ps1 -Alias $ALIAS -Count 20
```

```text
Requests per backend model:
  16 gpt-6-luna-2026-09-22
   4 gpt-6.1-sol-2026-09-29
```

In our tests the gateway interleaved the two models, four requests to `gpt-6-luna` and then one to
`gpt-6.1-sol`, so 20 requests split exactly 16 and 4. Plan around the shares, not the exact order.

To see the header for a single call:

```bash title="Bash"
# Send one request to the alias, and print only the x-ms-served-model header of the response
echo "✨ Backend model that served one request to $ALIAS:"
curl -sS -D - -o /dev/null "$AI_GATEWAY_URL/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\": \"$ALIAS\", \"max_completion_tokens\": 16, \"messages\": [{\"role\": \"user\", \"content\": \"Hi\"}]}" |
  grep -i "^x-ms-served-model"
```

```powershell title="PowerShell"
# Build a short request to the alias, capped at 16 completion tokens
$body = @{ model = $ALIAS; max_completion_tokens = 16; messages = @(@{ role = "user"; content = "Hi" }) } | ConvertTo-Json -Compress

# Send it, and print only the x-ms-served-model header of the response
Write-Host "✨ Backend model that served one request to ${ALIAS}:"
(Invoke-WebRequest -Method Post -Uri "$env:AI_GATEWAY_URL/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body).Headers["x-ms-served-model"]
```

> **Checkpoint**
> About four of every five requests show `gpt-6-luna-…`, and the rest show `gpt-6.1-sol-…`. The client sent
> `"model": "chat"` every time.

## Prefer one model by priority

The canary looks good, but finance wants `gpt-6-luna` to handle the traffic until the new model is approved.
Give `gpt-6.1-sol` priority `1`. It stays in the alias, ready to promote, but requests go to `gpt-6-luna`.

<!-- track: portal | Portal -->

### Edit the alias

1. In **Models** › **Aliases**, open `chat` and select **Edit**.
2. Select **Next** until you reach **Priority and weights**.
3. Set **Priority** to `1` for `gpt-6.1-sol` and set both weights to `1`. `gpt-6-luna` now shows `100%` at
   priority `0`, and `gpt-6.1-sol` shows `100%` at priority `1`.
4. Select **Next**, then **Save**. New requests use the new settings immediately.

> **Checkpoint**
> The alias **Backend models** tab shows `gpt-6-luna` at priority `0` and `gpt-6.1-sol` at priority `1`.

<!-- track: cli | Azure CLI -->

### Update the priorities

`model-alias update` replaces the whole `backendModels` list, so pass both backend models.

```bash title="Bash"
# Prefer gpt-6-luna: it keeps priority 0, and the candidate moves to priority 1, both with weight 1
echo "🔖 Alias $ALIAS now routes to:"
az aigateway model-alias update -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" \
  --description "Prefer the current model" \
  --backend-model resource-id="$MODELS/$PRIMARY" priority=0 weight=1 \
  --backend-model resource-id="$MODELS/$CANDIDATE" priority=1 weight=1 \
  --only-show-errors --query properties.backendModels -o json |
  jq -r '.[] | "\(.resourceId | split("/") | last)  priority \(.priority)  weight \(.weight)"'
```

```powershell title="PowerShell"
# Prefer gpt-6-luna: it keeps priority 0, and the candidate moves to priority 1, both with weight 1
Write-Host "🔖 Alias $ALIAS now routes to:"
az aigateway model-alias update -g $RG --gateway-name $GATEWAY -n $ALIAS `
  --description "Prefer the current model" `
  --backend-model resource-id="$MODELS/$PRIMARY" priority=0 weight=1 `
  --backend-model resource-id="$MODELS/$CANDIDATE" priority=1 weight=1 `
  --only-show-errors --query properties.backendModels -o json |
  ConvertFrom-Json | ForEach-Object { '{0}  priority {1}  weight {2}' -f ($_.resourceId -split '/')[-1], $_.priority, $_.weight }
```

> **Checkpoint**
> The output shows `gpt-6-luna  priority 0  weight 1` and `gpt-6.1-sol  priority 1  weight 1`.

<!-- track: iac | Bicep + azd -->

### Provision the priority strategy

Set `ROUTING_STRATEGY` to `priority` and provision again. Only the alias changes: `gpt-6-luna` keeps priority `0`,
and `gpt-6.1-sol` gets priority `1`.

```bash title="Bash"
# Switch the template's routing strategy from the weighted split to priority
azd env set ROUTING_STRATEGY priority &&
  echo "📝 ROUTING_STRATEGY is priority"

# Provision again: only the alias changes
azd provision &&
  echo "🚀 The $ALIAS alias now prefers $PRIMARY"
```

```powershell title="PowerShell"
# Switch the template's routing strategy from the weighted split to priority
azd env set ROUTING_STRATEGY priority
if ($?) { Write-Host "📝 ROUTING_STRATEGY is priority" }

# Provision again: only the alias changes
azd provision
if ($?) { Write-Host "🚀 The $ALIAS alias now prefers $PRIMARY" }
```

To go back to the weighted split, run `azd env set ROUTING_STRATEGY weighted` and `azd provision`. Change
`ROUTING_CANDIDATE_WEIGHT` the same way to canary in steps.

> **Checkpoint**
> `azd provision` ended with `SUCCESS`. **Read the alias** in **Verify** shows `gpt-6-luna  priority 0  weight 1`
> and `gpt-6.1-sol  priority 1  weight 1`.

<!-- /tracks -->

## Verify

<!-- steps -->

### Read the alias

```bash title="Bash"
# Print the alias's backend models, with the priority and the weight of each one
echo "🔖 Alias $ALIAS routes to:"
az aigateway model-alias show -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" --query properties.backendModels -o json |
  jq -r '.[] | "\(.resourceId | split("/") | last)  priority \(.priority)  weight \(.weight)"'
```

```powershell title="PowerShell"
# Print the alias's backend models, with the priority and the weight of each one
Write-Host "🔖 Alias $ALIAS routes to:"
az aigateway model-alias show -g $RG --gateway-name $GATEWAY -n $ALIAS --query properties.backendModels -o json |
  ConvertFrom-Json | ForEach-Object { '{0}  priority {1}  weight {2}' -f ($_.resourceId -split '/')[-1], $_.priority, $_.weight }
```

### Count the requests again

```bash title="Bash"
# Send 10 requests to the alias and count which backend model answered each one
echo "📊 Counting the backend models that serve $ALIAS, one request every half second"
./infra/count-models.sh "$ALIAS" 10
```

```powershell title="PowerShell"
# Send 10 requests to the alias and count which backend model answered each one
Write-Host "📊 Counting the backend models that serve $ALIAS, one request every half second"
./infra/count-models.ps1 -Alias $ALIAS -Count 10
```

> **Checkpoint**
> All 10 requests show `gpt-6-luna-…`. `gpt-6.1-sol` stays in the alias at priority `1`.

### Promote the new model

To finish the rollout, swap the priorities: `gpt-6.1-sol` at `0`, `gpt-6-luna` at `1`. Use the portal, or run
the `az aigateway model-alias update` command from the previous section with `$PRIMARY` and `$CANDIDATE`
swapped. Run the count again: every request now shows `gpt-6.1-sol-…`. To roll back, swap them again. Clients
never change.

<!-- /steps -->

## Go further

- **Canary in steps.** Move the weights from `95`/`5` to `80`/`20` to `50`/`50` while you watch errors, latency,
  and cost per model in [Monitor usage, cost, and traces](../13-monitoring/README.md). Weights must be at least
  `1`, so to stop sending traffic to a model, give it a higher priority number or remove it from the alias.
- **Prefer provisioned throughput.** Put a provisioned deployment at priority `0` and a pay-as-you-go
  deployment of the same model at priority `1`, so purchased capacity is used first. Test what happens when the
  provisioned deployment is saturated before you depend on it.
- **Balance regions or providers.** Register the same model from two Foundry accounts, or from Foundry and a
  custom provider, and give them weights in proportion to their quota.
- **Limit each model and the alias.** A token limit on a backend model, as in
  [Throttle tokens per caller with token limits](../06-token-limits/README.md), applies to that model. A limit
  on the alias applies to every request that calls `chat`.

## Clean up

Keep the gateway, the runtime key, and `gpt-6-luna` from lab 02. Later labs use them. Remove what you added in
this lab: the alias first, then the backend model, then the Foundry deployment.

<!-- track: portal | Portal -->

### Remove the alias and the candidate model

Open `chat` in **Models** › **Aliases** and select **Delete**. Requests that use the alias fail immediately; the
backend models stay in the gateway. Then delete the `gpt-6.1-sol` model, and any alias that the import created for
it, from **Models**. Finally, delete the `gpt-6.1-sol` deployment from your Foundry account, for example with the
last command of the CLI track.

<!-- track: cli | Azure CLI -->

### Remove the alias and the candidate model

```bash title="Bash"
# Delete the alias first, so that nothing points to the candidate model: requests to the alias now fail
az aigateway model-alias delete -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" --yes &&
  echo "🚮 Alias $ALIAS is deleted"

# Delete the candidate backend model from the gateway's provider
az aigateway model delete -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$CANDIDATE" --yes &&
  echo "🚮 Model $CANDIDATE is deleted from $PROVIDER"

# Delete the candidate deployment from the Foundry account, and keep gpt-6-luna for later labs
az cognitiveservices account deployment delete -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --deployment-name "$CANDIDATE" &&
  echo "🚮 Model deployment $CANDIDATE is deleted from $FOUNDRY_ACCOUNT"
```

```powershell title="PowerShell"
# Delete the alias first, so that nothing points to the candidate model: requests to the alias now fail
az aigateway model-alias delete -g $RG --gateway-name $GATEWAY -n $ALIAS --yes
if ($?) { Write-Host "🚮 Alias $ALIAS is deleted" }

# Delete the candidate backend model from the gateway's provider
az aigateway model delete -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER -n $CANDIDATE --yes
if ($?) { Write-Host "🚮 Model $CANDIDATE is deleted from $PROVIDER" }

# Delete the candidate deployment from the Foundry account, and keep gpt-6-luna for later labs
az cognitiveservices account deployment delete -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --deployment-name $CANDIDATE
if ($?) { Write-Host "🚮 Model deployment $CANDIDATE is deleted from $FOUNDRY_ACCOUNT" }
```

If an alias that the portal import created still points to `gpt-6.1-sol`, delete that alias before the model.

<!-- track: iac | Bicep + azd -->

### Delete everything azd created

In the `aigateway/labs/22-model-routing` folder, delete the resource group with the gateway, the Foundry account and
its two deployments, and the `chat` alias. [`--purge`](../SETUP.md#delete-what-azd-created) also purges the
soft-deleted Foundry account. It takes about ten minutes.

```bash
# Delete everything that azd up created in this lab, purge the soft-deleted Foundry account, and skip the prompt
azd down --purge --force &&
  echo "🚮 Everything that azd up created is deleted"
```

<!-- /tracks -->

`azd down` doesn't touch the gateway, key, and `gpt-6-luna` from lab 02, because the Bicep + azd track created its
own gateway.

## Next steps

- [Monitor usage, cost, and traces](../13-monitoring/README.md)
- [Throttle tokens per caller with token limits](../06-token-limits/README.md)
- [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md)
- [October 16 release: priority and weighted model routing](https://ai.gateway.azure.com/docs/releases/2026-10-16)
