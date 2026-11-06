// Enterprise reference deployment for Azure AI Gateway. One subscription-scope template creates two resource groups
// and composes small modules:
//
//   rg-<env>-<token>-foundrymodels   foundry.bicep         Foundry account (keyless) + model deployment
//   rg-<env>-<token>-gateway         monitoring.bicep      Log Analytics + Application Insights with OTLP ingestion
//                                    gateway.bicep         aigateways resource + Foundry User role for the gateway identity
//                                    models.bicep          Foundry provider + backend model (tokenLimit, contentSafety) + alias
//                                    tools.bicep           Microsoft Learn MCP server
//                                    keys.bicep            one runtime API key per app
//
// After deployment, scripts/connect-telemetry.sh (or .ps1) connects the gateway to Application Insights with
// telemetry.bicep, an OpenTelemetry exporter, once Azure has created the OTLP endpoints. Then
// scripts/apply-baselines.sh (or .ps1) applies the gateway-wide baseline policies.
targetScope = 'subscription'

import { principal } from './modules/types.bicep'

@minLength(1)
@maxLength(64)
@description('Environment name, for example aigw-dev or aigw-prod. Used in resource group names, tags, and the deterministic resource token.')
param environmentName string

@description('Region for the resource groups, the Foundry account, and the monitoring resources. The model and SKU must be available here.')
param location string = deployment().location

@description('Region for the gateway. Pick one where AI Gateway is available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
param aiGatewayLocation string = 'eastus2'

@description('Optional Microsoft Entra object ID of a developer. When set, the developer gets data-plane roles on the Foundry account, the alias, and the MCP server. Leave empty in production.')
param principalId string = ''

@description('Extra tags merged into the default tags on every resource group and resource.')
param tags object = {}

@description('Gateway name, max 24 characters. Defaults to aigw-<token>. Its first 10 characters start the runtime host name.')
param aiGatewayName string = ''

@description('Foundry model name to deploy.')
param modelName string = 'gpt-5-mini'

@description('Foundry model version to deploy.')
param modelVersion string = '2025-08-07'

@description('ARM-safe name of the Foundry deployment. It is also the backend model name in the gateway.')
param modelDeploymentName string = 'gpt-mini-latest'

@description('Model format for the Foundry deployment.')
param modelFormat string = 'OpenAI'

@description('Model deployment SKU name.')
param modelSkuName string = 'GlobalStandard'

@description('Deployment capacity, in thousands of tokens per minute for Global Standard.')
@minValue(1)
param modelCapacity int = 50

@description('Tokens per minute that each caller identity (API key or Microsoft Entra principal) can use on the backend model.')
@minValue(1)
param tokensPerMinutePerCaller int = 20000

@allowed([
  'None'
  'Low'
  'Medium'
  'High'
])
@description('Content safety threshold for every category on the backend model. The threshold is the lowest severity that is blocked: Low is strictest, None turns the category off.')
param contentSafetySeverity string = 'Medium'

@description('Client-facing alias that apps send in the request "model" field.')
param aliasName string = 'chat'

@description('Apps that get their own runtime API key. Each key is named after the app.')
param appNames string[] = [
  'web-chat'
  'batch-jobs'
]

@description('Microsoft Entra principals (usually groups) that get the AI Gateway Models User role on the alias.')
param modelUsers principal[] = []

@description('Microsoft Entra principals (usually groups) that get the AI Gateway Tools User role on the Microsoft Learn MCP server.')
param toolUsers principal[] = []

@description('Days to keep gateway telemetry in Log Analytics.')
@minValue(30)
@maxValue(730)
param logRetentionInDays int = 30

var resourceToken = take(toLower(uniqueString(subscription().id, environmentName, location)), 8)
var environmentLabel = toLower(environmentName)
var allTags = union({
  environment: environmentName
  workload: 'ai-gateway'
}, tags)
var gatewayResourceGroupName = 'rg-${environmentLabel}-${resourceToken}-gateway'
var foundryModelsResourceGroupName = 'rg-${environmentLabel}-${resourceToken}-foundrymodels'
var effectiveAiGatewayName = !empty(aiGatewayName) ? aiGatewayName : 'aigw-${resourceToken}'
var modelServicesName = 'aimodels-${resourceToken}'
var appInsightsName = take('${effectiveAiGatewayName}-insights', 64)
var logAnalyticsWorkspaceName = take('${effectiveAiGatewayName}-logs', 63)
var developer = empty(principalId) ? [] : [
  {
    principalId: principalId
    principalType: 'User'
  }
]
var gatewayModelDeployments = [
  {
    deploymentName: modelDeploymentName
    modelName: modelName
    modelFormat: modelFormat
    modelVersion: modelVersion
    skuName: modelSkuName
    capacity: modelCapacity
    description: 'Default chat model for every app behind the gateway.'
  }
]

resource gatewayRg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: gatewayResourceGroupName
  location: location
  tags: allTags
}

resource foundryModelsRg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: foundryModelsResourceGroupName
  location: location
  tags: allTags
}

module monitoring './modules/monitoring.bicep' = {
  name: 'monitoring-${resourceToken}'
  scope: gatewayRg
  params: {
    location: location
    tags: allTags
    logAnalyticsWorkspaceName: logAnalyticsWorkspaceName
    appInsightsName: appInsightsName
    retentionInDays: logRetentionInDays
  }
}

module foundry './modules/foundry.bicep' = {
  name: 'foundry-models-${resourceToken}'
  scope: foundryModelsRg
  params: {
    location: location
    tags: allTags
    aiServicesName: modelServicesName
    principalId: principalId
    modelDeployments: gatewayModelDeployments
  }
}

module gateway './modules/gateway.bicep' = {
  name: 'ai-gateway-${resourceToken}'
  scope: gatewayRg
  params: {
    location: aiGatewayLocation
    gatewayName: effectiveAiGatewayName
    tags: allTags
    foundryResourceIds: [
      foundry.outputs.aiServicesId
    ]
  }
}

// Every module below takes gateway.outputs.gatewayName, so it starts only after the gateway and the Foundry User
// role assignment exist.
module models './modules/models.bicep' = {
  name: 'ai-gateway-models-${resourceToken}'
  scope: gatewayRg
  params: {
    gatewayName: gateway.outputs.gatewayName
    providerName: 'foundry'
    providerDisplayName: 'Foundry'
    providerDescription: 'Managed-identity Foundry provider for the ${environmentName} environment.'
    foundryEndpoint: foundry.outputs.aiServicesEndpoint
    foundryResourceIds: [
      foundry.outputs.aiServicesId
    ]
    foundryModels: [for (deployment, i) in gatewayModelDeployments: {
      armName: deployment.deploymentName
      description: deployment.description
      resourceId: foundry.outputs.modelDeploymentIds[i]
      modelName: deployment.modelName
      modelVersion: deployment.modelVersion
      tokenLimit: tokensPerMinutePerCaller
      apiFormat: 'OpenAIChatCompletions'
      supportedEndpoints: [
        '/openai/v1/chat/completions'
        '/openai/v1/responses'
      ]
    }]
    contentSafetySeverity: contentSafetySeverity
    aliasName: aliasName
    aliasUsers: concat(developer, modelUsers)
  }
}

module tools './modules/tools.bicep' = {
  name: 'ai-gateway-tools-${resourceToken}'
  scope: gatewayRg
  params: {
    gatewayName: gateway.outputs.gatewayName
    toolUsers: concat(developer, toolUsers)
  }
}

module keys './modules/keys.bicep' = {
  name: 'ai-gateway-keys-${resourceToken}'
  scope: gatewayRg
  params: {
    gatewayName: gateway.outputs.gatewayName
    appNames: appNames
  }
}

output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AI_GATEWAY_NAME string = gateway.outputs.gatewayName
output AI_GATEWAY_LOCATION string = aiGatewayLocation
output AI_GATEWAY_RESOURCE_GROUP string = gatewayRg.name
output AI_GATEWAY_RESOURCE_ID string = gateway.outputs.gatewayId
output AI_GATEWAY_URL string = gateway.outputs.gatewayUrl
output AI_GATEWAY_PRINCIPAL_ID string = gateway.outputs.gatewayPrincipalId
output AI_GATEWAY_MODEL string = models.outputs.aliasName
output MCP_ENDPOINT string = tools.outputs.mcpEndpoint
output API_KEY_NAMES array = keys.outputs.apiKeyNames
output FOUNDRY_MODELS_RESOURCE_GROUP string = foundryModelsRg.name
output FOUNDRY_MODELS_NAME string = foundry.outputs.aiServicesName
output FOUNDRY_MODELS_RESOURCE_ID string = foundry.outputs.aiServicesId
output APPLICATION_INSIGHTS_NAME string = monitoring.outputs.appInsightsName
output LOG_ANALYTICS_WORKSPACE_ID string = monitoring.outputs.logAnalyticsWorkspaceId
