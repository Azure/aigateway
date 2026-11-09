// Publishes an alias with a cost limit for an existing AI Gateway model, creates the app-dev and support-bot runtime
// API keys, and gives support-bot, and optionally one Microsoft Entra identity, a budget of its own with overrides.
// main.bicep calls it after the quick start's template, and you can also deploy it on its own to a gateway you
// already have. The alias points at the same backend model as your default alias, so only callers that send the
// new alias name are budgeted. Key values are never outputs.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('Name of the existing model provider in the gateway, for example foundry-models.')
param providerName string

@description('Name of the existing backend model registration under the provider.')
param modelName string

@description('Callable alias to create. Clients send this value in the request "model" field.')
param aliasName string = '${modelName}-budget'

@description('Default budget for each caller, in US dollars. A string, so that it can hold decimals such as 0.01.')
param budgetAmount string = '5'

@description('Renewal period. Budgets renew in fixed calendar windows.')
@allowed([ 'hour', 'day', 'week', 'month', 'year' ])
param period string = 'day'

@description('Runtime API key that gets the default budget. The template creates it if it doesn\'t exist.')
param defaultKeyName string = 'app-dev'

@description('Runtime API key that gets its own budget. The template creates it if it doesn\'t exist.')
param overrideKeyName string = 'support-bot'

@description('Budget for the override key, in US dollars.')
param overrideAmount string = '50'

@description('Optional object ID of a Microsoft Entra user or service principal that gets its own budget. Empty adds no Entra override.')
param entraObjectId string = ''

@description('Budget for the Microsoft Entra identity, in US dollars.')
param entraAmount string = '20'

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

// Each key is a separate caller identity, so each one gets its own budget counter.
#disable-next-line BCP081
resource defaultKey 'Microsoft.ApiManagement/aigateways/apiKeys@2025-09-01-preview' = {
  parent: gateway
  name: defaultKeyName
  properties: {
    displayName: defaultKeyName
  }
}

#disable-next-line BCP081
resource overrideKey 'Microsoft.ApiManagement/aigateways/apiKeys@2025-09-01-preview' = {
  parent: gateway
  name: overrideKeyName
  properties: {
    displayName: overrideKeyName
  }
}

// Overrides are evaluated in order, and the first match wins. An API key override matches the key's resource ID.
// An Entra override matches validated token claims: here the tenant ID and the object ID of one identity.
var keyOverrides = [
  {
    apiKeyResourceId: overrideKey.id
    amount: json(overrideAmount)
  }
]
var entraOverrides = empty(entraObjectId) ? [] : [
  {
    claims: {
      tid: tenant().tenantId
      oid: entraObjectId
    }
    amount: json(entraAmount)
  }
]

#disable-next-line BCP081
resource budgetAlias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' = {
  parent: workspace
  name: aliasName
  dependsOn: [ defaultKey ]
  properties: {
    aliasName: aliasName
    backendModels: [
      { resourceId: model.id }
    ]
    policies: [
      {
        type: 'costLimit'
        // A stable ID: changing the amount on a later deployment keeps the spend accumulated so far.
        id: guid(gateway.id, aliasName, 'costLimit')
        amount: json(budgetAmount)
        period: period
        // Overrides need per-caller counters, so the template always counts by caller identity.
        counterKey: [ 'identity' ]
        overrides: concat(keyOverrides, entraOverrides)
      }
    ]
  }
}

output aliasName string = budgetAlias.name
output defaultKeyName string = defaultKey.name
output overrideKeyName string = overrideKey.name
output chatCompletionsUrl string = 'https://${gateway.properties.frontend.defaultHostname}/default/models/openai/v1/chat/completions'
