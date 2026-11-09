// Publishes an alias with a content safety policy for an existing AI Gateway model. main.bicep calls it after the
// quick start's template, and you can also deploy it on its own to a gateway you already have. The alias points at
// the same backend model as your default alias, but screens every prompt and response it serves, so you can test
// thresholds without changing what other callers get.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('Name of the existing model provider in the gateway, for example foundry-models.')
param providerName string

@description('Name of the existing backend model registration under the provider.')
param modelName string

@description('Callable alias to create. Clients send this value in the request "model" field.')
param aliasName string = '${modelName}-safe'

// The lowest severity that gets blocked: Low (Strict), Medium (Balanced), High (Lenient), or None (Off).
@description('Threshold for the Hate category.')
@allowed([ 'Low', 'Medium', 'High', 'None' ])
param hateSeverity string = 'Medium'

@description('Threshold for the Self-harm category.')
@allowed([ 'Low', 'Medium', 'High', 'None' ])
param selfHarmSeverity string = 'Medium'

@description('Threshold for the Sexual category.')
@allowed([ 'Low', 'Medium', 'High', 'None' ])
param sexualSeverity string = 'Medium'

@description('Threshold for the Violence category.')
@allowed([ 'Low', 'Medium', 'High', 'None' ])
param violenceSeverity string = 'Low'

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
resource safeAlias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' = {
  parent: workspace
  name: aliasName
  properties: {
    aliasName: aliasName
    backendModels: [
      { resourceId: model.id }
    ]
    policies: [
      {
        type: 'contentSafety'
        hateSeverity: hateSeverity
        selfHarmSeverity: selfHarmSeverity
        sexualSeverity: sexualSeverity
        violenceSeverity: violenceSeverity
      }
    ]
  }
}

output aliasName string = safeAlias.name
output chatCompletionsUrl string = 'https://${gateway.properties.frontend.defaultHostname}/default/models/openai/v1/chat/completions'
