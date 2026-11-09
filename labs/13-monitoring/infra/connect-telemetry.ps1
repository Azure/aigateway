# Connects an AI Gateway to its Application Insights component over OpenTelemetry, in the order Azure needs:
#   1. Waits until the component reports its OTLP endpoints and its Data Collection Rule. Azure creates them a few
#      minutes after OTLP ingestion turns on, so they can still be empty when the deployment ends.
#   2. Grants the gateway's managed identity Monitoring Metrics Publisher on the rule. Bicep can't: the rule lives in a
#      managed resource group whose deny assignment blocks deployments.
#   3. Deploys the OpenTelemetry exporter from a .bicepparam file, and retries while the role assignment propagates.
# azd runs it after each deployment (see azure.yaml), with the deployment's outputs as environment variables. When
# "azd provision" finds no changes to deploy, it skips the hook: run "azd hooks run postprovision" instead. Running it
# again is harmless.
#
# Usage:
#   $env:AZURE_RESOURCE_GROUP = "<gateway-resource-group>"
#   $env:APP_INSIGHTS_ID = "<component-resource-id>"
#   $env:AI_GATEWAY_PRINCIPAL_ID = "<gateway-managed-identity-object-id>"
#   ./connect-telemetry.ps1 -ParametersFile <exporter.bicepparam>
#
# The .bicepparam file can read more environment variables, such as AI_GATEWAY_NAME and APP_INSIGHTS_NAME.
param(
  [Parameter(Mandatory = $true)][string]$ParametersFile
)
$ErrorActionPreference = 'Stop'
if (-not $env:AZURE_RESOURCE_GROUP) { throw 'Set $env:AZURE_RESOURCE_GROUP to the gateway''s resource group' }
if (-not $env:APP_INSIGHTS_ID) { throw 'Set $env:APP_INSIGHTS_ID to the resource ID of the Application Insights component' }
if (-not $env:AI_GATEWAY_PRINCIPAL_ID) { throw 'Set $env:AI_GATEWAY_PRINCIPAL_ID to the object ID of the gateway''s managed identity' }
$subscriptionId = ($env:APP_INSIGHTS_ID -split '/')[2]
$componentName = Split-Path $env:APP_INSIGHTS_ID -Leaf

# The managed Azure Monitor workspace behind OTLP ingestion needs the Microsoft.Monitor resource provider
if ((az provider show -n Microsoft.Monitor --subscription $subscriptionId --query registrationState -o tsv) -ne 'Registered') {
  Write-Host '📝 Registering the Microsoft.Monitor resource provider'
  az provider register -n Microsoft.Monitor --subscription $subscriptionId --wait
}

# 1. Wait up to 10 minutes for the three OTLP endpoints and the Data Collection Rule
Write-Host "⏳ Waiting for the OTLP endpoints of $componentName"
$ready = '(properties.OTLPMetricsEndpoint && properties.OTLPLogsEndpoint && properties.OTLPTracesEndpoint)'
for ($attempt = 1; ; $attempt++) {
  $dcrId = az resource show --ids $env:APP_INSIGHTS_ID --api-version 2020-02-02 `
    --query "$ready && properties.DataCollectionRuleResourceId || ''" -o tsv 2>$null
  if ($dcrId) { break }
  if ($attempt -ge 60) { throw "$componentName has no OTLP endpoints after 10 minutes" }
  Start-Sleep -Seconds 10
}
Write-Host "🆔 Data Collection Rule: $(Split-Path $dcrId -Leaf)"

# 2. Let the gateway's identity publish to the Data Collection Rule
az role assignment create --assignee-object-id $env:AI_GATEWAY_PRINCIPAL_ID --assignee-principal-type ServicePrincipal `
  --role "Monitoring Metrics Publisher" --scope $dcrId -o none
if ($LASTEXITCODE -ne 0) { throw 'The Monitoring Metrics Publisher role assignment failed' }
Write-Host '🔐 The gateway can publish to the Data Collection Rule'

# 3. Create or update the exporter, retrying for up to 5 minutes while the role assignment propagates
for ($attempt = 1; $attempt -le 10; $attempt++) {
  az deployment group create --subscription $subscriptionId -g $env:AZURE_RESOURCE_GROUP -n aigw-telemetry `
    -p $ParametersFile -o none
  if ($LASTEXITCODE -eq 0) {
    Write-Host "📊 The gateway sends metrics, logs, and traces to $componentName"
    exit 0
  }
  if ($attempt -lt 10) {
    Write-Host '⏳ The role assignment may still be propagating. Retrying in 30 seconds.'
    Start-Sleep -Seconds 30
  }
}
throw 'The telemetry exporter deployment failed. In a few minutes, run "azd hooks run postprovision" or this script again.'
