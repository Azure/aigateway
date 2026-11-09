// Publishes a token-limited alias for an existing AI Gateway model. main.bicep calls it after the quick start's
// template, and you can also deploy it on its own to a gateway you already have. The alias points at the same backend
// model as your default alias, but carries its own token limit, so a "batch" or "trial" audience gets a smaller
// allowance without touching the model.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('Name of the existing model provider in the gateway, for example foundry-models.')
param providerName string

@description('Name of the existing backend model registration under the provider.')
param modelName string

@description('Callable alias to create. Clients send this value in the request "model" field.')
param aliasName string = '${modelName}-limited'

@description('Tokens allowed per period for each caller.')
@minValue(1)
param allowedTokens int = 1000

@description('Token limit window.')
@allowed([ 'minute', 'hour', 'day' ])
param period string = 'minute'

@description('Who gets a token counter: identity (each API key or Entra principal), ipAddress (each client IP address), or both.')
@allowed([ 'identity', 'ipAddress' ])
param counterKey array = [ 'identity' ]

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

#disable-next-line BCP081
resource provider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2025-09-01-preview' existing = {
  parent: workspace
  name: providerName
}

#disable-next-line BCP081
resource model 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2025-09-01-preview' existing = {
  parent: provider
  name: modelName
}

#disable-next-line BCP081
resource limitedAlias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' = {
  parent: workspace
  name: aliasName
  properties: {
    backendModels: [
      { resourceId: model.id }
    ]
    policies: [
      {
        type: 'tokenLimit'
        count: allowedTokens
        period: period
        counterKey: counterKey
      }
    ]
  }
}

output aliasName string = limitedAlias.name
output chatCompletionsUrl string = 'https://${gateway.properties.frontend.defaultHostname}/default/models/openai/v1/chat/completions'
