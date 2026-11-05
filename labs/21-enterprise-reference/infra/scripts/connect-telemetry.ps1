# Connects an AI Gateway to its Application Insights component over OpenTelemetry, in the order Azure needs:
#   1. Waits until the component reports its OTLP endpoints and its Data Collection Rule. Azure creates them a few
#      minutes after OTLP ingestion turns on, so they can still be empty when the deployment ends.
#   2. Grants the gateway's managed identity Monitoring Metrics Publisher on the rule. Bicep can't: the rule lives in a
#      managed resource group whose deny assignment blocks deployments.
#   3. Deletes an earlier exporter of the legacy applicationInsights kind, because an exporter's kind can't change.
#      Then deploys modules/telemetry.bicep, and retries while the role assignment propagates.
# Running it twice gives the same result.
#
# Usage:
#   $env:RG = "<gateway-resource-group>"; $env:GATEWAY = "<gateway-name>"
#   $env:APP_INSIGHTS_NAME = "<component-name>"   # optional, main.bicep names it <gateway>-insights
#   ./connect-telemetry.ps1
#
# Requires Azure CLI with the aigateway extension.
$ErrorActionPreference = 'Stop'
$template = Join-Path $PSScriptRoot '../modules/telemetry.bicep'
$exporter = 'appinsights'
if (-not $env:RG) { throw 'Set $env:RG to the gateway resource group' }
if (-not $env:GATEWAY) { throw 'Set $env:GATEWAY to the gateway name' }
$appInsightsName = if ($env:APP_INSIGHTS_NAME) { $env:APP_INSIGHTS_NAME } else { "$($env:GATEWAY)-insights" }
$appInsightsName = $appInsightsName.Substring(0, [Math]::Min(64, $appInsightsName.Length))

# The managed Azure Monitor workspace behind OTLP ingestion needs the Microsoft.Monitor resource provider
if ((az provider show -n Microsoft.Monitor --query registrationState -o tsv) -ne 'Registered') {
  Write-Host '📝 Registering the Microsoft.Monitor resource provider'
  az provider register -n Microsoft.Monitor --wait
}

# 1. Wait up to 10 minutes for the three OTLP endpoints and the Data Collection Rule
Write-Host "⏳ Waiting for the OTLP endpoints of $appInsightsName"
$ready = '(properties.OTLPMetricsEndpoint && properties.OTLPLogsEndpoint && properties.OTLPTracesEndpoint)'
for ($attempt = 1; ; $attempt++) {
  $dcrId = az resource show -g $env:RG -n $appInsightsName --resource-type Microsoft.Insights/components `
    --api-version 2020-02-02 --query "$ready && properties.DataCollectionRuleResourceId || ''" -o tsv 2>$null
  if ($dcrId) { break }
  if ($attempt -ge 60) { throw "$appInsightsName has no OTLP endpoints after 10 minutes" }
  Start-Sleep -Seconds 10
}
Write-Host "🆔 Data Collection Rule: $(Split-Path $dcrId -Leaf)"

# 2. Let the gateway's identity publish to the Data Collection Rule
$principalId = az aigateway show -g $env:RG -n $env:GATEWAY --query identity.principalId -o tsv
az role assignment create --assignee-object-id $principalId --assignee-principal-type ServicePrincipal `
  --role "Monitoring Metrics Publisher" --scope $dcrId -o none
if ($LASTEXITCODE -ne 0) { throw 'The Monitoring Metrics Publisher role assignment failed' }
Write-Host '🔐 The gateway can publish to the Data Collection Rule'

# 3. Replace a legacy applicationInsights exporter, then create or update the OpenTelemetry exporter, retrying for up
#    to 5 minutes while the role assignment propagates. Azure returns no properties.kind for a legacy exporter, and
#    OpenTelemetry for an OpenTelemetry exporter.
$legacy = az aigateway telemetry-exporter show -g $env:RG --gateway-name $env:GATEWAY -n $exporter `
  --query "properties.kind != 'OpenTelemetry'" -o tsv 2>$null
if ($legacy -eq 'true') {
  Write-Host "🧹 Deleting the applicationInsights exporter $exporter, because an exporter's kind can't change"
  az aigateway telemetry-exporter delete -g $env:RG --gateway-name $env:GATEWAY -n $exporter --yes -o none
}
for ($attempt = 1; $attempt -le 10; $attempt++) {
  az deployment group create -g $env:RG -n aigw-telemetry -f $template `
    -p gatewayName=$env:GATEWAY appInsightsName=$appInsightsName exporterName=$exporter -o none
  if ($LASTEXITCODE -eq 0) {
    Write-Host "📊 The gateway sends metrics, logs, and traces to $appInsightsName"
    exit 0
  }
  if ($attempt -lt 10) {
    Write-Host '⏳ The role assignment may still be propagating. Retrying in 30 seconds.'
    Start-Sleep -Seconds 30
  }
}
throw 'The telemetry exporter deployment failed. Run this script again in a few minutes.'
