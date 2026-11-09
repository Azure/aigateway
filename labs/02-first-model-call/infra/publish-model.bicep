// Publishes one Microsoft Foundry model deployment through an existing AI Gateway:
// grants the gateway's managed identity the Foundry User role on the account, creates a Foundry model
// provider that authenticates with that identity, registers the deployment as a backend model, publishes a
// callable alias for it, and creates a runtime API key for the first app.
// Mirrors the Foundry provider and model registration in infra/ai-gateway/main.bicep of the reference sample.
// The lab's main.bicep calls it with azd, and other labs call it as a module. You can also deploy it on its own
// to a gateway you already have with "az deployment group create".
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Resource ID of the Foundry (Azure AI Services) or Azure OpenAI account. It can be in another resource group or subscription.')
param foundryAccountId string

@description('Name of the model deployment in that account, for example gpt-5-mini.')
param deploymentName string

@description('Version of the deployed model, for example 2025-08-07. Optional.')
param modelVersion string = ''

@description('Name of the model provider to create in the gateway.')
param providerName string = 'foundry-models'

@description('Callable alias that clients send in the request "model" field.')
param aliasName string = deploymentName

@description('Name of the runtime API key to create for the first app.')
param apiKeyName string = 'app-first-call'

@description('Display name of the runtime API key.')
param apiKeyDisplayName string = 'First call app key'

@description('Tokens per minute that each caller identity can use on this model.')
@minValue(1)
param tokensPerMinute int = 10000

var foundryAccountName = last(split(foundryAccountId, '/'))
var foundrySubscriptionId = split(foundryAccountId, '/')[2]
var foundryResourceGroup = split(foundryAccountId, '/')[4]
var deploymentId = '${foundryAccountId}/deployments/${deploymentName}'

#disable-next-line BCP081
resource aiGateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource defaultWorkspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: aiGateway
  name: 'default'
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  name: foundryAccountName
}

var foundryEndpoint = foundryAccount.properties.endpoint
var normalizedFoundryEndpoint = endsWith(foundryEndpoint, '/') ? foundryEndpoint : '${foundryEndpoint}/'

module foundryUserRole './foundry-user-role.bicep' = {
  name: take('foundry-user-${uniqueString(aiGateway.id, foundryAccountId)}', 64)
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  params: {
    foundryAccountName: foundryAccountName
    gatewayPrincipalId: aiGateway.identity.principalId
    gatewayResourceId: aiGateway.id
  }
}

#disable-next-line BCP081
resource foundryProvider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: providerName
  dependsOn: [
    foundryUserRole
  ]
  properties: {
    kind: 'Foundry'
    displayName: 'Foundry models'
    description: 'Managed-identity Foundry provider created by the first-model-call lab.'
    foundry: {
      endpoint: normalizedFoundryEndpoint
      resourceIds: [
        foundryAccountId
      ]
      authentication: {
        kind: 'ManagedIdentity'
        managedIdentity: {
          resource: 'https://cognitiveservices.azure.com/'
        }
      }
    }
  }
}

#disable-next-line BCP081
resource model 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2025-09-01-preview' = {
  parent: foundryProvider
  name: deploymentName
  properties: {
    displayName: deploymentName
    description: 'Foundry deployment ${deploymentName} published through AI Gateway.'
    apiFormat: 'OpenAIChatCompletions'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: deploymentId
      modelName: deploymentName
      modelVersion: empty(modelVersion) ? null : modelVersion
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
  name: aliasName
  properties: {
    backendModels: [
      { resourceId: model.id }
    ]
  }
}

#disable-next-line BCP081
resource runtimeApiKey 'Microsoft.ApiManagement/aigateways/apiKeys@2025-09-01-preview' = {
  parent: aiGateway
  name: apiKeyName
  properties: {
    displayName: apiKeyDisplayName
  }
}

output providerName string = foundryProvider.name
output modelName string = model.name
output aliasName string = alias.name
output apiKeyName string = runtimeApiKey.name
output gatewayUrl string = 'https://${aiGateway.properties.frontend.defaultHostname}'
output modelEndpoint string = 'https://${aiGateway.properties.frontend.defaultHostname}/default/models/openai/v1'
output foundryUserRoleAssignmentName string = foundryUserRole.outputs.roleAssignmentName
