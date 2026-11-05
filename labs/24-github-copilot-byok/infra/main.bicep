// Lab 24 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// account, and default model, then publishes gpt-6.1-sol for GitHub Copilot with its token limit and the
// github-copilot runtime API key, and registers the Microsoft Learn MCP server as learn. The key value is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Model to deploy and publish for Copilot. The deployment, the backend model, and the alias use this name. azd reads it from BYOK_MODEL.')
param byokModelName string = 'gpt-6.1-sol'

@description('Version of that model. azd reads it from BYOK_MODEL_VERSION.')
param byokModelVersion string = '2026-09-29'

@description('Deployment SKU. Use DataZoneStandard if your GlobalStandard quota for the model is used up. azd reads it from BYOK_MODEL_SKU.')
@allowed([
  'GlobalStandard'
  'DataZoneStandard'
])
param byokModelSku string = 'GlobalStandard'

@description('Deployment capacity in thousands of tokens per minute. azd reads it from BYOK_MODEL_CAPACITY.')
@minValue(1)
param byokModelCapacity int = 100

@description('Tokens per minute that each caller identity can use on the model through the gateway. azd reads it from BYOK_TOKENS_PER_MINUTE.')
@minValue(1000)
param tokensPerMinute int = 100000

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// The quick start's template: a gateway, a Foundry account with gpt-5-mini, the foundry-models provider, and a key.
module base '../../quickstart/infra/resources.bicep' = {
  name: 'aigw-base'
  scope: rg
  params: {
    location: location
    tags: tags
    gatewayName: 'aigw-${suffix}'
    foundryName: 'aigw${suffix}'
  }
}

// gpt-6.1-sol in the same Foundry account, under the same provider, with its token limit and the github-copilot key.
module copilot 'copilot-model.bicep' = {
  name: 'aigw-copilot-model'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    foundryAccountId: base.outputs.foundryId
    providerName: base.outputs.providerName
    modelName: byokModelName
    modelVersion: byokModelVersion
    skuName: byokModelSku
    capacity: byokModelCapacity
    tokensPerMinute: tokensPerMinute
    apiKeyName: 'github-copilot'
  }
}

// Lab 04's template: the public Microsoft Learn MCP server, published as learn.
module learn '../../04-federate-mcp-tools/infra/tool-server.bicep' = {
  name: 'aigw-learn-mcp'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    serverName: 'learn'
    namespace: 'learn'
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = byokModelName
output AI_GATEWAY_MODEL string = copilot.outputs.aliasName
output AI_GATEWAY_KEY_NAME string = copilot.outputs.apiKeyName
output AI_GATEWAY_MODEL_ENDPOINT string = copilot.outputs.modelEndpoint
output AI_GATEWAY_MCP_URL string = learn.outputs.mcpEndpoint
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
