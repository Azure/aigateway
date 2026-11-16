// Publishes an alias that lets Model Router pick a model for each prompt. main.bicep calls it after the quick start's
// template, and you can also deploy it on its own to a gateway you already have, such as the one from lab 02.
// Registers the gpt-5.5 deployment under the existing Foundry provider, then publishes the auto alias with gpt-5-mini
// and gpt-5.5 at the same priority, so auto model selection chooses between them.
// The gpt-5-mini backend model is only referenced, so its settings stay untouched.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Name of the existing Foundry model provider in the gateway, for example foundry-models from lab 02.')
param providerName string = 'foundry-models'

@description('Name of the existing lower-cost backend model, for example gpt-5-mini.')
param smallModelName string = 'gpt-5-mini'

@description('Model Router name of the lower-cost model: its unversioned model name.')
param smallSelectorModelName string = 'gpt-5-mini'

@description('Resource ID of the Foundry account that hosts the higher-quality deployment.')
param foundryAccountId string

@description('Name of the higher-quality deployment in that account.')
param largeDeploymentName string = 'gpt-5.5'

@description('Model of that deployment. It\'s also the model\'s Model Router name, which must be a supported selector model.')
param largeModelName string = 'gpt-5.5'

@description('Version of the higher-quality model.')
param largeModelVersion string = '2026-04-24'

@description('Name of the backend model to register. The portal\'s Foundry import names gpt-5.5 as gpt-5-5, so every track of the lab uses that name.')
param largeBackendModelName string = 'gpt-5-5'

@description('Callable alias that clients send in the request "model" field.')
param aliasName string = 'auto'

@description('What Model Router favors: Balanced for a balance of cost and quality, Cost for lower cost, Quality for quality.')
@allowed([
  'Balanced'
  'Cost'
  'Quality'
])
param objective string = 'Balanced'

@description('What callers may override in a request\'s auto_model_selection field: objective, model (narrow the model pool), both, or none. The two filter values turn on the portal\'s compatibility filters, which aren\'t caller fields.')
param allowedRequestOverrides ('model' | 'objective' | 'filterModelsForToolCompatibility' | 'filterModelsForParameterCompatibility')[] = []

#disable-next-line BCP081
resource aiGateway 'Microsoft.ApiManagement/aigateways@2026-11-01' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource defaultWorkspace 'Microsoft.ApiManagement/aigateways/workspaces@2026-11-01' existing = {
  parent: aiGateway
  name: 'default'
}

#disable-next-line BCP081
resource provider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01' existing = {
  parent: defaultWorkspace
  name: providerName
}

#disable-next-line BCP081
resource small 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01' existing = {
  parent: provider
  name: smallModelName
}

#disable-next-line BCP081
resource large 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01' = {
  parent: provider
  name: largeBackendModelName
  properties: {
    displayName: largeModelName
    description: 'Higher-quality model that the ${aliasName} alias can select.'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: '${foundryAccountId}/deployments/${largeDeploymentName}'
      modelName: largeModelName
      modelVersion: largeModelVersion
    }
  }
}

#disable-next-line BCP081
resource alias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01' = {
  parent: defaultWorkspace
  name: aliasName
  properties: {
    aliasName: aliasName
    description: 'Model Router picks ${smallSelectorModelName} or ${largeModelName} for each prompt'
    // Both models share priority 0, so priority keeps both, then auto model selection picks one by its selector name.
    backendModels: [
      {
        resourceId: small.id
        priority: 0
        weight: 1
        selectorModelName: smallSelectorModelName
      }
      {
        resourceId: large.id
        priority: 0
        weight: 1
        selectorModelName: largeModelName
      }
    ]
    selectionOrder: [
      'priority'
      'autoModelSelection'
    ]
    autoModelSelection: {
      objective: objective
      allowedRequestOverrides: allowedRequestOverrides
    }
  }
}

output aliasName string = alias.name
output largeBackendModelName string = large.name
output objective string = objective
output allowedRequestOverrides array = allowedRequestOverrides
output chatCompletionsUrl string = 'https://${aiGateway.properties.frontend.defaultHostname}/default/models/openai/v1/chat/completions'
