// Publishes gpt-6.1-sol through an existing AI Gateway so GitHub Copilot can use it as a bring-your-own-key model.
// main.bicep calls it after the quick start's template, and you can also deploy it on its own to a gateway you already
// have, such as the one from lab 02. It adds a gpt-6.1-sol deployment to the Foundry account the gateway already uses,
// registers it under the gateway's existing Foundry provider with a per-caller token limit, publishes the gpt-6.1-sol
// alias, and creates the github-copilot runtime API key. The key value is never an output.
// The gateway's identity already has the Foundry User role on the account (from lab 02 or the quick start), and that
// role covers the new deployment, so this template doesn't assign it again.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Resource ID of the Foundry (Azure AI Services) account that the gateway uses. It can be in another resource group.')
param foundryAccountId string

@description('Model to deploy and publish. The deployment and the alias both use this name.')
param modelName string = 'gpt-6.1-sol'

@description('Version of the model to deploy.')
param modelVersion string = '2026-09-29'

@description('Deployment SKU. Use DataZoneStandard if your GlobalStandard quota for the model is used up.')
@allowed([
  'GlobalStandard'
  'DataZoneStandard'
])
param skuName string = 'GlobalStandard'

@description('Deployment capacity in thousands of tokens per minute. Coding agents send large prompts, so give them room.')
@minValue(1)
param capacity int = 100

@description('Tokens per minute that each caller identity can use on the model through the gateway.')
@minValue(1000)
param tokensPerMinute int = 100000

@description('Name of the existing Foundry provider in the gateway, for example foundry-models from lab 02 or the quick start.')
param providerName string = 'foundry-models'

@description('Name of the runtime API key that GitHub Copilot uses.')
param apiKeyName string = 'github-copilot'

var foundrySubscriptionId = split(foundryAccountId, '/')[2]
var foundryResourceGroup = split(foundryAccountId, '/')[4]

module deployment 'deployment.bicep' = {
  name: take('deploy-${modelName}', 64)
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  params: {
    accountName: last(split(foundryAccountId, '/'))
    modelName: modelName
    modelVersion: modelVersion
    skuName: skuName
    capacity: capacity
  }
}

#disable-next-line BCP081
resource aiGateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource defaultWorkspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: aiGateway
  name: 'default'
}

#disable-next-line BCP081
resource provider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2025-09-01-preview' existing = {
  parent: defaultWorkspace
  name: providerName
}

#disable-next-line BCP081
resource model 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2025-09-01-preview' = {
  parent: provider
  name: modelName
  properties: {
    displayName: modelName
    description: 'Foundry deployment ${modelName} published through AI Gateway for GitHub Copilot.'
    apiFormat: 'OpenAIChatCompletions'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: '${foundryAccountId}/deployments/${deployment.outputs.deploymentName}'
      modelName: modelName
      modelVersion: modelVersion
    }
    policies: [
      {
        type: 'tokenLimit'
        period: 'minute'
        count: tokensPerMinute
        counterKey: [
          'identity'
        ]
      }
    ]
  }
}

#disable-next-line BCP081
resource alias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: modelName
  properties: {
    backendModels: [
      { resourceId: model.id }
    ]
  }
}

#disable-next-line BCP081
resource apiKey 'Microsoft.ApiManagement/aigateways/apiKeys@2025-09-01-preview' = {
  parent: aiGateway
  name: apiKeyName
  properties: {
    displayName: 'GitHub Copilot'
  }
}

output aliasName string = alias.name
output apiKeyName string = apiKey.name
output modelEndpoint string = 'https://${aiGateway.properties.frontend.defaultHostname}/default/models/openai/v1'
