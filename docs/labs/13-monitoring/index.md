---
title: Monitor usage, cost, and traces
summary: Send the gateway's OpenTelemetry metrics, logs, and traces to Application Insights, then use the built-in Monitoring dashboard to see usage, estimated cost per model and API key, policy impact, and gateway-aware traces.
category: observability
level: Beginner
duration: 25
tracks: [portal, cli, iac]
order: 13
illustration: diagrams/observability.svg
tags: [OpenTelemetry, OTLP, Application Insights, traces, estimated cost, KQL, GenAI semantic conventions]
objectives:
  - Explain how the gateway exports metrics, logs, and traces independently over OTLP
  - Connect the gateway to Application Insights in the portal, with the Azure CLI, or with Bicep and azd
  - Read health, outcomes, policy impact, tokens, and estimated cost on the Monitoring dashboard
  - Follow one request through the trace waterfall, including its policy child spans
  - Query gateway telemetry in Log Analytics with KQL
prereqs:
  - 02-first-model-call
---

# Monitor usage, cost, and traces

Your gateway now serves several apps. Finance asks what the models cost per team, an app owner reports
intermittent failures, and nobody can tell whether a policy or the backend rejected those calls. In this lab you
send the gateway's OpenTelemetry signals to Application Insights and answer all three questions from the built-in
**Monitoring** dashboard, down to a single request's trace.

![AI Gateway exports metrics, logs, and traces to Application Insights or any OTLP endpoint](../assets/diagrams/observability.svg "The gateway exports each telemetry signal over OTLP. With Application Insights, the Monitoring page reads the same data back as a dashboard.")

<!-- widget: request-lifecycle -->

## Before you begin

<!-- setup: tools sign-in extension clone -->

> [!TIP]
> On the **Bicep + azd** track, `azd up` creates its own gateway, model, key, and Application Insights, so you can
> skip this section. You need only the one-time setup above, and permission to create role assignments, for example
> **Owner** on the subscription.

- Complete [Publish a Foundry model and make your first call](../02-first-model-call/README.md). You need a gateway,
  an imported model, a callable alias, and a runtime API key from **Access** › **Keys**.
- Permission to change the gateway, for example **Contributor** on its resource group, **and** permission to
  create role assignments, for example **Owner** or **Role Based Access Control Administrator**. Setup grants the
  gateway's managed identity a role on the telemetry destination. To reuse an existing Application Insights
  resource, you also need **Application Insights Contributor** on it.
- Run the scripts and samples from the lab's folder, `~/ai-gateway/labs/13-monitoring`.

Set these variables once. The tracks and the traffic script reuse them.

```bash title="Bash"
# Name your gateway from lab 02, and the alias that the traffic script calls
export RG="<resource-group>"
export GATEWAY="<gateway>"
export AI_GATEWAY_MODEL="<model-name>"     # a callable alias, for example the one you used in lab 02

# Read the gateway's runtime URL
export AI_GATEWAY_URL="https://$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
echo "🌐 Runtime URL: $AI_GATEWAY_URL"

# Paste the runtime key you created in Access › Keys, without showing it: don't commit it or write it to a file
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
echo "🔑 Key: in AI_GATEWAY_API_KEY (${#AI_GATEWAY_API_KEY} characters, not shown)"
```

```powershell title="PowerShell"
# Name your gateway from lab 02, and the alias that the traffic script calls
$RG      = "<resource-group>"
$GATEWAY = "<gateway>"
$env:AI_GATEWAY_MODEL = "<model-name>"     # a callable alias, for example the one you used in lab 02

# Read the gateway's runtime URL
$env:AI_GATEWAY_URL = "https://$(az aigateway show -g $RG -n $GATEWAY --query properties.frontend.defaultHostname -o tsv)"
Write-Host "🌐 Runtime URL: $env:AI_GATEWAY_URL"

# Paste the runtime key you created in Access › Keys, without showing it: don't commit it or write it to a file
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
Write-Host "🔑 Key: in AI_GATEWAY_API_KEY ($($env:AI_GATEWAY_API_KEY.Length) characters, not shown)"
```

> [!IMPORTANT]
> Did you configure monitoring before the 2026-08-28 release? Reconfigure it to get logs, traces, cost metrics, and
> policy spans: on the **Monitoring** page select **Settings**, disable monitoring, and configure it again. You can
> select the same Application Insights resource.

## How it works

The gateway emits three OpenTelemetry signals and exports each one **independently** over OTLP, to Azure Application
Insights or to any OTLP endpoint (for example Datadog, Splunk, Grafana Cloud, or your own collector). Configure only
the signals you need. Telemetry follows the OpenTelemetry GenAI and MCP semantic conventions, such as
`gen_ai.request.model`, `gen_ai.operation.name`, and `mcp.method.name`, and adds gateway attributes such as the API
key, alias, resolved model, and policy type.

When the destination is Application Insights and all three signals are on, the **Monitoring** page turns that data
into a dashboard. Estimated cost is **observed tokens × public pricing**: use it to spot trends and compare callers,
then reconcile with provider billing or Azure Cost Management for financial reporting.

| Signal | What the gateway sends | Where it lands with Application Insights | Dashboard uses it for |
|---|---|---|---|
| Metrics | Token usage and estimated token cost, by model, token type, API key, and caller | Azure Monitor workspace (managed Prometheus) linked to Application Insights | Tokens and **Estimated model cost** |
| Traces | One root span per request, with child spans for each stage and each policy that ran | `OTelSpans` table in the Log Analytics workspace | Calls, outcomes, blocked traces, the trace waterfall |
| Logs | Request records with status, caller, model, and the token usage the backend reported | `OTelLogs` table in the Log Analytics workspace | Correlated logs and caller attribution |

## Connect Application Insights

Pick one track. Each ends with the gateway exporting all three signals to an Application Insights resource named
`<gateway>-insights`.

<!-- track: portal | Portal -->

### Start the setup

Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway from the gateway switcher. Select
**Monitoring**. If monitoring isn't configured yet, the page shows **Set up monitoring**. Select
**Configure telemetry**. The wizard has three steps: **Destination**, **Authentication**, and **Review and apply**.

### Choose a destination

On **Destination**, select **New Azure Application Insights resource** and keep the suggested name,
`<gateway>-insights`. Select **Next**.

> [!TIP]
> The other choices are **Existing Azure Application Insights resource**, for a component you already have, and
> **Custom OpenTelemetry destination**, which takes separate **Metrics endpoint**, **Logs endpoint**, and
> **Traces endpoint** URLs. Leave an endpoint empty to turn that signal off. The built-in dashboard only reads
> Application Insights, so with a custom destination you use your own platform's views.

### Review authentication

On **Authentication**, the gateway exports with its managed identity. If none is enabled, the wizard enables the
system-assigned identity for you. It also assigns the **Monitoring Metrics Publisher** role on the destination's
Data Collection Rule when you apply.

Leave **Include recommended token claims in telemetry** selected. It adds Microsoft Entra caller claims to the
telemetry, which [Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md) builds on. Select
**Next**.

### Apply the configuration

On **Review and apply**, select **Apply**. The wizard shows each step as it runs: **Register resource providers**,
**Resolve managed identity**, **Provision destination**, **Discover OTLP endpoints**,
**Assign Monitoring Metrics Publisher role**, and **Create telemetry exporter**. If a step fails, fix the cause
shown in the message and select **Retry**. If an Azure Policy assignment blocks a step, check the Activity Log for
the denied operation.

> **Checkpoint**
> The **Monitoring** page shows the **Overview**, **Models**, **Tools**, **Policies**, and **Traces** tabs, with
> **Open in Azure portal** and **Settings** in the header.

<!-- track: cli | Azure CLI -->

### Create the destination

Create what the wizard's **New Azure Application Insights resource** creates: a Log Analytics workspace and a
workspace-based Application Insights component, named after the gateway and in its region. `az monitor app-insights`
comes from the `application-insights` extension, which the Azure CLI offers to install the first time.

```bash title="Bash"
# Read the gateway's region, so that the destination lives next to it
LOCATION="$(az aigateway show -g "$RG" -n "$GATEWAY" --query location -o tsv)"
echo "📍 Region: $LOCATION"

# Create the Log Analytics workspace that stores the spans and logs, and keep its ID for the queries
export LAW_CUSTOMER_ID="$(az monitor log-analytics workspace create -g "$RG" -n "$GATEWAY-logs" -l "$LOCATION" \
  --query customerId -o tsv)" &&
  echo "📊 Log Analytics workspace $GATEWAY-logs is ready"

# Create the Application Insights component on that workspace
az monitor app-insights component create -g "$RG" -a "$GATEWAY-insights" -l "$LOCATION" --kind web \
  --application-type web --workspace "$GATEWAY-logs" -o none &&
  echo "📊 Application Insights $GATEWAY-insights is ready"
```

```powershell title="PowerShell"
# Read the gateway's region, so that the destination lives next to it
$LOCATION = az aigateway show -g $RG -n $GATEWAY --query location -o tsv
Write-Host "📍 Region: $LOCATION"

# Create the Log Analytics workspace that stores the spans and logs, and keep its ID for the queries
$LAW_CUSTOMER_ID = az monitor log-analytics workspace create -g $RG -n "$GATEWAY-logs" -l $LOCATION `
  --query customerId -o tsv
if ($?) { Write-Host "📊 Log Analytics workspace $GATEWAY-logs is ready" }

# Create the Application Insights component on that workspace
az monitor app-insights component create -g $RG -a "$GATEWAY-insights" -l $LOCATION --kind web `
  --application-type web --workspace "$GATEWAY-logs" -o none
if ($?) { Write-Host "📊 Application Insights $GATEWAY-insights is ready" }
```

### Turn on OTLP ingestion

The component reports OTLP endpoints only after you turn on ingestion into an Azure Monitor workspace. Azure then
creates a managed resource group, `ai_<component>_<id>_managed`, with the Data Collection Rule and the Azure Monitor
workspace for the metrics. `az monitor app-insights` has no flag for this setting, so set the component's
`AzureMonitorWorkspaceIngestionMode` property with `az resource update`, then read the endpoints back. It takes about
ten seconds.

```bash title="Bash"
# Turn on OTLP ingestion, which creates the Data Collection Rule and the OTLP endpoints
COMPONENT_ID="$(az resource update -g "$RG" -n "$GATEWAY-insights" --resource-type Microsoft.Insights/components \
  --api-version 2020-02-02 --set properties.AzureMonitorWorkspaceIngestionMode=Enabled --query id -o tsv)" &&
  echo "📊 OTLP ingestion is on for $GATEWAY-insights"

# Read the Data Collection Rule and the OTLP endpoint of each signal from the component
otlp() { az resource show --ids "$COMPONENT_ID" --api-version 2020-02-02 --query "properties.$1" -o tsv; }
DCR_ID="$(otlp DataCollectionRuleResourceId)"
METRICS_URL="$(otlp OTLPMetricsEndpoint)"
LOGS_URL="$(otlp OTLPLogsEndpoint)"
TRACES_URL="$(otlp OTLPTracesEndpoint)"
echo "🆔 Data Collection Rule: ${DCR_ID##*/}"
echo "🌐 Metrics endpoint: ${METRICS_URL%%/dataCollectionRules/*}"
echo "🌐 Logs and traces endpoint: ${LOGS_URL%%/dataCollectionRules/*}"
```

```powershell title="PowerShell"
# Turn on OTLP ingestion, which creates the Data Collection Rule and the OTLP endpoints
$COMPONENT_ID = az resource update -g $RG -n "$GATEWAY-insights" --resource-type Microsoft.Insights/components `
  --api-version 2020-02-02 --set properties.AzureMonitorWorkspaceIngestionMode=Enabled --query id -o tsv
if ($?) { Write-Host "📊 OTLP ingestion is on for $GATEWAY-insights" }

# Read the Data Collection Rule and the OTLP endpoint of each signal from the component
function otlp($name) { az resource show --ids $COMPONENT_ID --api-version 2020-02-02 --query "properties.$name" -o tsv }
$DCR_ID      = otlp DataCollectionRuleResourceId
$METRICS_URL = otlp OTLPMetricsEndpoint
$LOGS_URL    = otlp OTLPLogsEndpoint
$TRACES_URL  = otlp OTLPTracesEndpoint
Write-Host "🆔 Data Collection Rule: $(Split-Path $DCR_ID -Leaf)"
Write-Host "🌐 Metrics endpoint: $(($METRICS_URL -split '/dataCollectionRules/')[0])"
Write-Host "🌐 Logs and traces endpoint: $(($LOGS_URL -split '/dataCollectionRules/')[0])"
```

### Let the gateway publish

The gateway exports with its system-assigned managed identity, which needs **Monitoring Metrics Publisher** on the
Data Collection Rule. The wizard's **Assign Monitoring Metrics Publisher role** step does the same.

```bash title="Bash"
# Read the gateway's managed identity, which signs the telemetry export
PRINCIPAL_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query identity.principalId -o tsv)"
echo "👤 Gateway identity: $PRINCIPAL_ID"

# Let the identity publish to the Data Collection Rule
az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
  --role "Monitoring Metrics Publisher" --scope "$DCR_ID" -o none &&
  echo "🔐 The gateway can publish to the Data Collection Rule"
```

```powershell title="PowerShell"
# Read the gateway's managed identity, which signs the telemetry export
$PRINCIPAL_ID = az aigateway show -g $RG -n $GATEWAY --query identity.principalId -o tsv
Write-Host "👤 Gateway identity: $PRINCIPAL_ID"

# Let the identity publish to the Data Collection Rule
az role assignment create --assignee-object-id $PRINCIPAL_ID --assignee-principal-type ServicePrincipal `
  --role "Monitoring Metrics Publisher" --scope $DCR_ID -o none
if ($?) { Write-Host "🔐 The gateway can publish to the Data Collection Rule" }
```

### Create the telemetry exporter

`az aigateway telemetry-exporter create` creates what the wizard's **Create telemetry exporter** step creates: an
exporter named `appinsights`, of kind `OpenTelemetry`, that sends each signal to its OTLP endpoint with the gateway's
managed identity. `--telemetry` adds the recommended token claims: `tid` and `oid` on every signal, and `appid` and
`azp` on logs and traces.

```bash title="Bash"
# Export metrics, logs, and traces to the component's OTLP endpoints, signed with the gateway's managed identity
az aigateway telemetry-exporter create -g "$RG" --gateway-name "$GATEWAY" -n appinsights --kind OpenTelemetry \
  --application-insights "{resourceId:'$COMPONENT_ID'}" --payload-capture false \
  --open-telemetry "{metricsEndpoint:'$METRICS_URL',logsEndpoint:'$LOGS_URL',tracesEndpoint:'$TRACES_URL',credentials:{managedIdentity:{resource:'https://monitor.azure.com'}}}" \
  --telemetry "{attributes:[{source:{kind:claims,value:tid},signals:[logs,traces,metrics]},{source:{kind:claims,value:oid},signals:[logs,traces,metrics]},{source:{kind:claims,value:appid},signals:[logs,traces]},{source:{kind:claims,value:azp},signals:[logs,traces]}]}" \
  -o none &&
  echo "📊 Telemetry exporter appinsights sends metrics, logs, and traces to $GATEWAY-insights"

# List the gateway's telemetry exporters, with the kind of each one
echo "📊 Telemetry exporters on $GATEWAY:"
az aigateway telemetry-exporter list -g "$RG" --gateway-name "$GATEWAY" --query "[].{name:name, kind:properties.kind}" -o table
```

```powershell title="PowerShell"
# Export metrics, logs, and traces to the component's OTLP endpoints, signed with the gateway's managed identity
az aigateway telemetry-exporter create -g $RG --gateway-name $GATEWAY -n appinsights --kind OpenTelemetry `
  --application-insights "{resourceId:'$COMPONENT_ID'}" --payload-capture false `
  --open-telemetry "{metricsEndpoint:'$METRICS_URL',logsEndpoint:'$LOGS_URL',tracesEndpoint:'$TRACES_URL',credentials:{managedIdentity:{resource:'https://monitor.azure.com'}}}" `
  --telemetry "{attributes:[{source:{kind:claims,value:tid},signals:[logs,traces,metrics]},{source:{kind:claims,value:oid},signals:[logs,traces,metrics]},{source:{kind:claims,value:appid},signals:[logs,traces]},{source:{kind:claims,value:azp},signals:[logs,traces]}]}" `
  -o none
if ($?) { Write-Host "📊 Telemetry exporter appinsights sends metrics, logs, and traces to $GATEWAY-insights" }

# List the gateway's telemetry exporters, with the kind of each one
Write-Host "📊 Telemetry exporters on ${GATEWAY}:"
az aigateway telemetry-exporter list -g $RG --gateway-name $GATEWAY --query "[].{name:name, kind:properties.kind}" -o table
```

To change the exporter later, such as to turn on `--payload-capture`, run `az aigateway telemetry-exporter update`
with the same name and only the settings that change.

> **Checkpoint**
> The list shows one exporter, `appinsights`, of kind `OpenTelemetry`. In the portal, the gateway's **Monitoring**
> page shows the **Overview**, **Models**, **Tools**, **Policies**, and **Traces** tabs.

<!-- track: iac | Bicep + azd -->

**What you need:** only the one-time setup from **Before you begin**. This track doesn't use your gateway from lab 02:
`azd up` creates a new one, so it works on its own.

### Choose what to declare

The templates declare what the portal's wizard sets up: a Log Analytics workspace, a workspace-based Application
Insights component with OTLP ingestion turned on, and a gateway telemetry exporter of kind `OpenTelemetry` that
sends metrics, logs, and traces to the component's OTLP endpoints with the recommended token claims. When OTLP
ingestion turns on, Azure creates a managed resource group, `ai_<component>_<id>_managed`, with the Data Collection
Rule and the Azure Monitor workspace for the metrics. The template reads the endpoints back from the component.

The gateway's managed identity also needs **Monitoring Metrics Publisher** on that Data Collection Rule. Azure locks
the managed resource group with a deny assignment that blocks deployments, so Bicep can't assign the role there.
Instead, `azure.yaml` assigns it with the Azure CLI in a `postprovision` hook, which azd runs after each deployment.

The sample's exporter kind, `applicationInsights`, is legacy: the portal flags it because it no longer activates the
OTLP signals the dashboard needs. `infra/monitoring.bicep` keeps it for reference, switched off by
`deployLegacyExporter`.

### Review the templates

`infra/main.bicep` creates the resource group `rg-<environment name>` and calls the quick start's
[resources.bicep](../quickstart/infra/resources.bicep) for the gateway, the Foundry model, its default alias, and the
`app-first-call` key. Then it calls `infra/monitoring.bicep` for the destination and `infra/otel-exporter.bicep` to
connect the gateway to it:

<!-- include: infra/main.bicep -->

`infra/monitoring.bicep` creates the Log Analytics workspace and the Application Insights component, and turns on
OTLP ingestion when `enableOtlpIngestion` is `true`. You can also deploy it on its own to your gateway's resource
group with `az deployment group create`, then connect it in the portal with **Existing Azure Application Insights
resource**:

<!-- include: infra/monitoring.bicep -->

`infra/otel-exporter.bicep` creates the exporter. The `claimAttributes` parameter lists the token claims to add to
the telemetry, and the signals that carry each one. Its default matches **Include recommended token claims in
telemetry**:

<!-- include: infra/otel-exporter.bicep -->

`azure.yaml` holds the `postprovision` hook that grants the role:

<!-- include: azure.yaml -->

### Deploy with azd up

Move into the lab's folder, create an azd environment named `aigw-lab13` in your current subscription, then provision
everything. It takes about four minutes.

```bash title="Bash"
# Move into the lab's folder, which holds the azd project
cd ~/ai-gateway/labs/13-monitoring &&
  echo "📂 Lab folder: $(pwd)"

# Create an azd environment in your current subscription, so that azd doesn't prompt you
azd env new aigw-lab13 --location eastus2 --subscription "$(az account show --query id --output tsv)" &&
  echo "📝 azd environment aigw-lab13 deploys to eastus2"

# Provision the gateway, its model, alias, and key, and Application Insights, and connect the gateway to it
azd up &&
  echo "🚀 Gateway deployed: $(azd env get-value AI_GATEWAY_URL)"
```

```powershell title="PowerShell"
# Move into the lab's folder, which holds the azd project
Set-Location ~/ai-gateway/labs/13-monitoring
if ($?) { Write-Host "📂 Lab folder: $(Get-Location)" }

# Create an azd environment in your current subscription, so that azd doesn't prompt you
azd env new aigw-lab13 --location eastus2 --subscription (az account show --query id --output tsv)
if ($?) { Write-Host "📝 azd environment aigw-lab13 deploys to eastus2" }

# Provision the gateway, its model, alias, and key, and Application Insights, and connect the gateway to it
azd up
if ($?) { Write-Host "🚀 Gateway deployed: $(azd env get-value AI_GATEWAY_URL)" }
```

For another region, pick one where AI Gateway and the `gpt-6-luna` model are available, as in [Find the available
regions](../SETUP.md#find-the-available-regions).

### Read the outputs and the key

Set the variables that the next sections and **Verify** use from azd's environment values, and read the key from
the gateway, so that it never shows on screen. The last command lists the gateway's telemetry exporters.

```bash title="Bash"
# Read the gateway's names, URLs, and alias, and the Log Analytics workspace ID, from azd's environment values
export RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
export GATEWAY="$(azd env get-value AI_GATEWAY_NAME)"
export AI_GATEWAY_MODEL="$(azd env get-value AI_GATEWAY_MODEL)"
export GATEWAY_ID="$(azd env get-value AI_GATEWAY_ID)"
export AI_GATEWAY_URL="$(azd env get-value AI_GATEWAY_URL)"
export LAW_CUSTOMER_ID="$(azd env get-value LOG_ANALYTICS_CUSTOMER_ID)"
echo "📝 Gateway $GATEWAY in $RG"
echo "🌐 Runtime URL: $AI_GATEWAY_URL"
echo "🔖 Model alias: $AI_GATEWAY_MODEL"
echo "🆔 Log Analytics workspace ID: $LAW_CUSTOMER_ID"

# Read the key from the gateway, so that it never shows on screen or lands in a file
export AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" \
  --query primaryKey --output tsv)"
echo "🔑 Key: in AI_GATEWAY_API_KEY (${#AI_GATEWAY_API_KEY} characters, not shown)"

# List the gateway's telemetry exporters, with the kind of each one
echo "📊 Telemetry exporters on $GATEWAY:"
az aigateway telemetry-exporter list -g "$RG" --gateway-name "$GATEWAY" --query "[].{name:name, kind:properties.kind}" -o table
```

```powershell title="PowerShell"
# Read the gateway's names, URLs, and alias, and the Log Analytics workspace ID, from azd's environment values
$RG                     = azd env get-value AZURE_RESOURCE_GROUP
$GATEWAY                = azd env get-value AI_GATEWAY_NAME
$env:AI_GATEWAY_MODEL   = azd env get-value AI_GATEWAY_MODEL
$GATEWAY_ID             = azd env get-value AI_GATEWAY_ID
$env:AI_GATEWAY_URL     = azd env get-value AI_GATEWAY_URL
$LAW_CUSTOMER_ID        = azd env get-value LOG_ANALYTICS_CUSTOMER_ID
Write-Host "📝 Gateway $GATEWAY in $RG"
Write-Host "🌐 Runtime URL: $env:AI_GATEWAY_URL"
Write-Host "🔖 Model alias: $env:AI_GATEWAY_MODEL"
Write-Host "🆔 Log Analytics workspace ID: $LAW_CUSTOMER_ID"

# Read the key from the gateway, so that it never shows on screen or lands in a file
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" `
  --query primaryKey --output tsv
Write-Host "🔑 Key: in AI_GATEWAY_API_KEY ($($env:AI_GATEWAY_API_KEY.Length) characters, not shown)"

# List the gateway's telemetry exporters, with the kind of each one
Write-Host "📊 Telemetry exporters on ${GATEWAY}:"
az aigateway telemetry-exporter list -g $RG --gateway-name $GATEWAY --query "[].{name:name, kind:properties.kind}" -o table
```

> **Checkpoint**
> `azd up` ended with `SUCCESS`, and the list shows one exporter, `appinsights`, of kind `OpenTelemetry`. In the
> portal, the gateway's **Monitoring** page shows the **Overview**, **Models**, **Tools**, **Policies**, and
> **Traces** tabs.

<!-- /tracks -->

## Generate traffic

The dashboard needs data. Send a few requests through the gateway so every view has something to show.

<!-- steps -->

### Run the traffic script

From the lab folder, run the script for your shell. It sends ten chat completions with an `x-correlation-id` header
on each, then one request for an alias that doesn't exist, so you also get a failure to investigate.

```bash title="Bash"
# Send ten chat completions, each with an x-correlation-id header, then one call to an alias that doesn't exist
echo "📊 Sending 10 requests to $AI_GATEWAY_MODEL, then one that fails on purpose:"
./infra/generate-traffic.sh "$AI_GATEWAY_MODEL" 10
```

```powershell title="PowerShell"
# Send ten chat completions, each with an x-correlation-id header, then one call to an alias that doesn't exist
Write-Host "📊 Sending 10 requests to $env:AI_GATEWAY_MODEL, then one that fails on purpose:"
./infra/generate-traffic.ps1 -Model $env:AI_GATEWAY_MODEL -Requests 10
```

On GitHub, open [generate-traffic.sh](infra/generate-traffic.sh) or
[generate-traffic.ps1](infra/generate-traffic.ps1).

Expected output: ten `200` rows and a final `error` row with a `4xx` status. Telemetry can take a few minutes to
reach the dashboard.

> [!TIP]
> Sending `x-correlation-id` from your apps makes application-level investigations easier. Never put personal data,
> secrets, prompts, or regulated identifiers in it.

<!-- /steps -->

## Tour the dashboard

Each tab answers a different question. Use the time range buttons (**1H**, **24H**, **7D**, **30D**) to match your
traffic.

<!-- steps -->

### Overview: is the gateway healthy, and what does it cost?

Select **Monitoring** › **Overview**. The cards summarize the range: **Estimated model cost**, **Model calls**,
**Tool calls**, **Trace failure rate**, and **Blocked traces**. Below them, **Model and tool calls over time**
stacks both kinds of traffic, **Top models** ranks models by estimated cost with their 4xx and 5xx error rates, and
**Top tool servers** ranks MCP servers by calls. **Recent traces requiring attention** and
**Top blocking policies** take you straight to problems.

![The Monitoring overview with estimated cost, calls, failure rate, and top models](../assets/screens/monitoring-overview.png "Overview: estimated model cost, model and tool calls, failure rate, blocked traces, and the top models and tool servers.")

### Models: who uses which model, and how many tokens?

Select **Models**. Each row is a responding model with its **Aliases**, **Calls**, **Input tokens**,
**Output tokens**, **Cached input tokens**, **Token share**, error counts, **Caller identities**, and
**Estimated cost**. **Model usage by caller identity** breaks usage and estimated cost down by API key or Entra
caller. That's your first view of cost by API key and model.

> [!NOTE]
> If you see "Model token and estimated cost data are incomplete until you add a Prometheus access token", follow
> the prompt: run `az account get-access-token --resource https://prometheus.monitor.azure.com --query accessToken -o tsv`
> and paste the value into **Prometheus access token**.

### Tools: which MCP tools are called?

Select **Tools**. You see **Total tool calls**, **Active tool servers**, **Usage by tool server**,
**Top tools within tool servers**, and **Tool usage by caller identity**. It stays empty until agents call tools
through the gateway, as in [Federate MCP tools behind one endpoint](../04-federate-mcp-tools/README.md).

### Policies: what did governance block?

Select **Policies**. The summary shows **Requests blocked**, **Caller identities blocked**, and
**Assets with blocked calls**. The table lists each **Policy type** with **Allowed requests**,
**Blocked requests**, and **Last executed**. After [Throttle tokens per caller](../06-token-limits/README.md), the
token limit's `429` responses show up here.

### Traces: find the failed request

Select **Traces**. Each row shows **Time**, **Assets**, **Outcome**, and **Applied policies**. Find the request
for `does-not-exist` from the script, or use **Search trace ID, asset, policy, or reason**.

<!-- /steps -->

> **Checkpoint**
> **Overview** shows the model calls you sent and a non-zero **Estimated model cost**, **Models** shows your API key
> as a caller identity, and **Traces** lists the failed request.

## Follow a request through the trace waterfall

A gateway-aware trace shows where time went and which policies ran, so you can tell a policy rejection from a
backend failure at a glance.

<!-- steps -->

### Open a successful trace

On **Traces**, select a successful model call. The header shows the **Trace ID**, the number of **Spans**, and the
**Duration**.

### Read the waterfall

**Trace waterfall** draws parent-first spans on one timeline. The root span is the model request, for example
`Model · <model-name>` on `POST /default/models/*`. Under it:

| Child span | What it measures |
|---|---|
| **inbound** | Work before the backend call. Each policy that ran is a child span, such as `policy costLimit` with its configuration. |
| **backend** | The call to the provider, for example `HTTP POST` on `/openai/v1/chat/completions`. |
| **outbound** | Work on the response before it returns to the client. |
| **response transfer** | Sending the response back to the client. |

![A trace waterfall with inbound, backend, outbound, and response transfer spans and a cost limit policy span](../assets/screens/monitoring-trace.png "The waterfall splits gateway time from backend time, and each policy that ran appears as its own span.")

### Read the correlated logs

Under **Correlated logs**, expand the request log and switch between **Code** and **Tree**. Look for:

- `gen_ai.operation.name` (for example `chat`), `gen_ai.request.model` (the alias you sent), and
  `gen_ai.response.model` (the versioned model that answered).
- `azure.ai_gateway.client.usage.prompt_tokens`, `...completion_tokens`, and `...total_tokens`: the usage the
  backend reported for this one call.

<!-- /steps -->

> **Checkpoint**
> You can point to the policy spans under **inbound**, compare **backend** time with total time, and read the
> token usage of one request in its correlated log.

## Query telemetry with KQL

The dashboard reads the `OTelSpans` and `OTelLogs` tables in the Log Analytics workspace behind Application Insights.
You can query them directly to build your own reports and alerts.

<!-- steps -->

### Open Logs

In the [Azure portal](https://portal.azure.com), open the Log Analytics workspace linked to your Application Insights
resource (`<gateway>-logs` if you used the Bicep + azd track) and select **Logs**. Switch the editor to **KQL mode**.

### Run the starter queries

Copy a query from [infra/queries.kql](infra/queries.kql) and run it. Start with query 2 (calls by alias, resolved
model, and API key) and query 3 (token usage per model and API key).

<!-- include: infra/queries.kql kusto -->

On GitHub, open [infra/queries.kql](infra/queries.kql).

To run a query from the command line instead, pass the workspace's customer ID to
`az monitor log-analytics query`. The command comes from the `log-analytics` extension, which the Azure CLI offers to
install the first time. On the Azure CLI and Bicep + azd tracks, `LAW_CUSTOMER_ID` already holds the ID. Otherwise, set it to the
**Workspace ID** on the workspace's **Overview** page. This short query counts the model calls of the last hour by
alias and status code:

```bash title="Bash"
# Count the model calls of the last hour by alias and status code, from the gateway's spans in Log Analytics
echo "📊 Model calls in the last hour, by alias and status code:"
az monitor log-analytics query -w "$LAW_CUSTOMER_ID" -o table --analytics-query \
  'OTelSpans | where TimeGenerated > ago(1h) | where Kind =~ "Server" and tostring(Attributes["http.route"]) contains "/models/" | summarize Calls = count() by Model = tostring(Attributes["gen_ai.request.model"]), Status = toint(Attributes["http.response.status_code"])'
```

```powershell title="PowerShell"
# Count the model calls of the last hour by alias and status code, from the gateway's spans in Log Analytics
Write-Host "📊 Model calls in the last hour, by alias and status code:"
az monitor log-analytics query -w $LAW_CUSTOMER_ID -o table --analytics-query `
  'OTelSpans | where TimeGenerated > ago(1h) | where Kind =~ "Server" and tostring(Attributes["http.route"]) contains "/models/" | summarize Calls = count() by Model = tostring(Attributes["gen_ai.request.model"]), Status = toint(Attributes["http.response.status_code"])'
```

These queries are starting points. Attribute names follow the OpenTelemetry GenAI conventions plus gateway
attributes. Run `OTelSpans | take 10` to see what your data carries, and adapt names before you build alerts on
them.

<!-- /steps -->

> **Checkpoint**
> Query 2 returns one row per alias and API key with your call count, and query 3 returns input and output token
> totals that match the order of magnitude on the **Models** tab.

## Verify

<!-- steps -->

### Match the dashboard to your traffic

Run the traffic script once more with five requests, wait a few minutes, and refresh **Monitoring** › **Overview**
with **1H** selected. **Model calls** grows by at least five.

### Confirm all signals are flowing

Open **Settings**. All three signals point at your Application Insights resource, and the dashboard doesn't show
"Enable all telemetry signals".

To check the exporter from the CLI, list the gateway's telemetry exporters:

```bash title="Bash"
# List the gateway's telemetry exporters, with the kind of each one
echo "📊 Telemetry exporters on $GATEWAY:"
az aigateway telemetry-exporter list -g "$RG" --gateway-name "$GATEWAY" --query "[].{name:name, kind:properties.kind}" -o table
```

```powershell title="PowerShell"
# List the gateway's telemetry exporters, with the kind of each one
Write-Host "📊 Telemetry exporters on ${GATEWAY}:"
az aigateway telemetry-exporter list -g $RG --gateway-name $GATEWAY --query "[].{name:name, kind:properties.kind}" -o table
```

The exporter that every track creates has kind `OpenTelemetry`. Kind `applicationInsights` is the legacy exporter
from [Troubleshooting](../TROUBLESHOOTING.md#lab-13-monitoring).

<!-- /steps -->

## Go further

- **Query the token metrics.** Token and cost metrics land in the Azure Monitor workspace linked to Application
  Insights as `azure.ai_gateway.client.token.usage` and `azure.ai_gateway.client.token.cost`, with labels such as
  `gen_ai.request.model` and `gen_ai.token.type`. Docs show PromQL in its underscore form, for example
  `sum by (gen_ai_request_model) (gen_ai_client_token_usage)`. Check which names your backend received before you
  build on them. [Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md) queries them.
- **Alert on what you can act on.** Start with token usage spikes, backend authentication failures, and telemetry
  export failures. Route each alert to an owner who can investigate the gateway, backend, policy, or destination.
- **Send telemetry somewhere else.** Use **Custom OpenTelemetry destination** to export to any OTLP endpoint. Store
  any credential headers as secrets.
- **Capture payloads carefully.** **Settings** › **Logging** has **Log request and response payloads**. It's off by
  default because prompts and responses can be sensitive and add volume.

## Clean up

Application Insights and Log Analytics bill for ingestion and retention. If you continue with
[Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md), keep everything.

<!-- track: portal | Portal -->

### Disable monitoring

On the **Monitoring** page, select **Settings** › **General** › **Disable monitoring**. This stops the export but
doesn't delete the destination.

### Delete the destination

In the [Azure portal](https://portal.azure.com), delete the `<gateway>-insights` Application Insights resource and its
Log Analytics workspace if nothing else uses them. Enabling OTLP can also create an Azure Monitor workspace and a
Data Collection Rule for the metrics. Check the resource group for them and delete them if they're unused.

<!-- track: cli | Azure CLI -->

### Delete the exporter and the destination

Delete the exporter first, so that the gateway stops exporting, then the component and the workspace. Azure deletes
the component's managed resource group, with the Data Collection Rule, along with the component.

```bash title="Bash"
# Stop the export by deleting the gateway's telemetry exporter
az aigateway telemetry-exporter delete -g "$RG" --gateway-name "$GATEWAY" -n appinsights --yes &&
  echo "🚮 Telemetry exporter appinsights is deleted"

# Delete the Application Insights component and the Log Analytics workspace, without a recovery period
az monitor app-insights component delete -g "$RG" -a "$GATEWAY-insights" &&
  echo "🚮 Application Insights $GATEWAY-insights is deleted"
az monitor log-analytics workspace delete -g "$RG" -n "$GATEWAY-logs" --force --yes &&
  echo "🚮 Log Analytics workspace $GATEWAY-logs is deleted"
```

```powershell title="PowerShell"
# Stop the export by deleting the gateway's telemetry exporter
az aigateway telemetry-exporter delete -g $RG --gateway-name $GATEWAY -n appinsights --yes
if ($?) { Write-Host "🚮 Telemetry exporter appinsights is deleted" }

# Delete the Application Insights component and the Log Analytics workspace, without a recovery period
az monitor app-insights component delete -g $RG -a "$GATEWAY-insights"
if ($?) { Write-Host "🚮 Application Insights $GATEWAY-insights is deleted" }
az monitor log-analytics workspace delete -g $RG -n "$GATEWAY-logs" --force --yes
if ($?) { Write-Host "🚮 Log Analytics workspace $GATEWAY-logs is deleted" }
```

<!-- track: iac | Bicep + azd -->

### Delete everything azd created

In the `ai-gateway/labs/13-monitoring` folder, delete the resource group with the gateway, the Foundry account, the
Application Insights component, and the Log Analytics workspace. Azure deletes the component's managed resource group
with it. [`--purge`](../SETUP.md#delete-what-azd-created) also purges the soft-deleted Foundry account. It takes about
ten minutes.

```bash
# Delete everything that azd up created, and purge the Foundry account
azd down --purge --force &&
  echo "🚮 Everything that azd up created is deleted"
```

The Bicep + azd track of [Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md) creates its
own gateway and destination, so you don't need to keep these for it.

<!-- /tracks -->

Keep the gateway, model, and key from lab 02: the next labs reuse them. `azd down` doesn't touch them, because the
Bicep + azd track created its own gateway.

## Next steps

- [Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md): build a chargeback report by tenant, app, and claim.
- [Throttle tokens per caller with token limits](../06-token-limits/README.md): act on what the dashboard shows.
- [Enforce cost budgets with per-caller overrides](../07-cost-budgets/README.md): turn estimated cost into a hard budget.
- Docs: [Observability in AI Gateway](https://ai.gateway.azure.com/docs/observability).
