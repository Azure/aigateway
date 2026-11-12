// Publishes the Claude deployments of a Microsoft Foundry account through an existing Azure AI Gateway, for Claude
// Code: grants the gateway's managed identity the Foundry User role on the account, creates a Foundry provider named
// after the account unless the gateway already has one, registers each deployment as an Anthropic Messages model
// under it, publishes the alias "<account>/<deployment>" for each one with a token limit per caller, adds a cost limit
// per caller to one alias, and creates a runtime API key for Claude Code. The aliases have the same names as the ones
// that the portal's import creates, so the Claude Code settings work with either track. Key values are never outputs.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Resource ID of the Foundry account that has the Claude deployments. It can be in another resource group or subscription.')
param foundryAccountId string

@description('Claude deployments to publish, each with the tokens per minute that each caller can use through its alias.')
param claudeModels array = [
  { name: 'claude-opus-5-5', tokensPerMinute: 100000 }
  { name: 'claude-sonnet-5-5', tokensPerMinute: 100000 }
  { name: 'claude-haiku-5-5', tokensPerMinute: 100000 }
]

@description('Deployment whose alias also gets a cost limit. Empty adds no cost limit.')
param budgetModel string = 'claude-opus-5-5'

@description('Budget for each caller, in US dollars. A string, so that it can hold decimals such as 0.05.')
param budgetAmount string = '5'

@description('Renewal period of the budget. Budgets renew in fixed calendar windows.')
@allowed([ 'hour', 'day', 'week', 'month', 'year' ])
param budgetPeriod string = 'day'

@description('ID of the cost limit. Keep it to keep the spend counted so far; change it to start a new count.')
param budgetId string = 'claude-code-budget'

@description('Grant the gateway\'s managed identity the Foundry User role on the account. Set it to false when the role is already assigned, for example by the portal\'s import.')
param grantFoundryUser bool = true

@description('Create the Foundry provider named after the account. Set it to false when the gateway already has it, for example from the portal\'s import, so that the template keeps its settings, such as its authentication.')
param createProvider bool = true

@description('Name of the runtime API key to create for Claude Code.')
param apiKeyName string = 'claude-code'

var foundryAccountName = last(split(foundryAccountId, '/'))
var foundrySubscriptionId = split(foundryAccountId, '/')[2]
var foundryResourceGroup = split(foundryAccountId, '/')[4]

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  name: foundryAccountName
}

// Read each deployment, so that the models record the model and version that Foundry serves.
resource deployments 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' existing = [for m in claudeModels: {
  parent: foundryAccount
  name: m.name
}]

var foundryEndpoint = foundryAccount.properties.endpoint
var roleAssignments = '${foundryAccountId}/providers/Microsoft.Authorization/roleAssignments'

module foundryUserRole '../../02-first-model-call/infra/foundry-user-role.bicep' = if (grantFoundryUser) {
  name: take('foundry-user-${uniqueString(gateway.id, foundryAccountId)}', 64)
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  params: {
    foundryAccountName: foundryAccountName
    gatewayPrincipalId: gateway.identity.principalId
    gatewayResourceId: gateway.id
  }
}

#disable-next-line BCP081
resource provider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2025-09-01-preview' = if (createProvider) {
  parent: workspace
  name: foundryAccountName
  dependsOn: [
    foundryUserRole
  ]
  properties: {
    kind: 'Foundry'
    displayName: foundryAccountName
    foundry: {
      endpoint: endsWith(foundryEndpoint, '/') ? foundryEndpoint : '${foundryEndpoint}/'
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

// The models go under the provider, whether the template created it or the gateway already had it.
#disable-next-line BCP081
resource accountProvider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2025-09-01-preview' existing = {
  parent: workspace
  name: foundryAccountName
}

// Claude deployments speak the Anthropic Messages API, so the gateway serves them on /default/models/anthropic.
#disable-next-line BCP081
resource models 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2025-09-01-preview' = [for (m, i) in claudeModels: {
  parent: accountProvider
  name: m.name
  dependsOn: [
    foundryUserRole
    provider
  ]
  properties: {
    displayName: m.name
    supportedEndpoints: [
      '/anthropic/v1/messages'
    ]
    deployment: {
      resourceId: deployments[i].id
      modelName: deployments[i].properties.model.name
      modelVersion: deployments[i].properties.model.version
    }
  }
}]

var budgetPolicy = {
  type: 'costLimit'
  id: budgetId
  amount: json(budgetAmount)
  period: budgetPeriod
  counterKey: [ 'identity' ]
}

// Each caller identity, a key or a Microsoft Entra identity, gets its own counters.
#disable-next-line BCP081
resource aliases 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' = [for (m, i) in claudeModels: {
  parent: workspace
  name: '${foundryAccountName}-${m.name}'
  properties: {
    aliasName: '${foundryAccountName}/${m.name}'
    backendModels: [
      { resourceId: models[i].id }
    ]
    policies: concat([
      {
        type: 'tokenLimit'
        count: m.tokensPerMinute
        period: 'minute'
        counterKey: [ 'identity' ]
      }
    ], m.name == budgetModel ? [ budgetPolicy ] : [])
  }
}]

#disable-next-line BCP081
resource apiKey 'Microsoft.ApiManagement/aigateways/apiKeys@2025-09-01-preview' = {
  parent: gateway
  name: apiKeyName
  properties: {
    displayName: apiKeyName
  }
}

output gatewayUrl string = 'https://${gateway.properties.frontend.defaultHostname}'
output anthropicBaseUrl string = 'https://${gateway.properties.frontend.defaultHostname}/default/models/anthropic'
output providerName string = accountProvider.name
output aliasNames array = [for (m, i) in claudeModels: '${foundryAccountName}/${m.name}']
output apiKeyName string = apiKey.name
output roleAssignmentId string = grantFoundryUser ? '${roleAssignments}/${foundryUserRole!.outputs.roleAssignmentName}' : ''
