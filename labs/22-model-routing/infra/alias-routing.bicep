// Routes one callable alias across two Foundry backend models. main.bicep calls it after the quick start's template,
// and you can also deploy it on its own to a gateway you already have, such as the one from lab 02.
// Registers a candidate deployment under the existing Foundry provider, then publishes an alias that either splits
// traffic between the primary and the candidate by weight, or prefers the primary by priority.
// The primary backend model is only referenced, so its policies stay untouched.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Name of the existing Foundry model provider in the gateway, for example foundry-models from lab 02.')
param providerName string = 'foundry-models'

@description('Name of the existing backend model that takes most of the traffic, for example gpt-5-mini.')
param primaryModelName string = 'gpt-5-mini'

@description('Resource ID of the Foundry account that hosts the candidate deployment.')
param foundryAccountId string

@description('Name of the candidate deployment in that account, for example gpt-6.1-sol.')
param candidateDeploymentName string = 'gpt-6.1-sol'

@description('Version of the candidate model, for example 2026-09-29. Optional.')
param candidateModelVersion string = ''

@description('Callable alias that clients send in the request "model" field.')
param aliasName string = 'chat'

@description('weighted: both backends share priority 0 and split traffic by weight. priority: the primary is preferred, and the candidate gets priority 1.')
@allowed([
  'weighted'
  'priority'
])
param strategy string = 'weighted'

@description('Weighted strategy only: the candidate weight. The primary gets 100 minus this value.')
@minValue(1)
@maxValue(99)
param candidateWeight int = 20

type route = {
  @description('Resource ID of the backend model.')
  resourceId: string

  @description('Lower numbers are preferred. 0 to 100.')
  @minValue(0)
  @maxValue(100)
  priority: int

  @description('Share of traffic among backends with the same priority. 1 to 100.')
  @minValue(1)
  @maxValue(100)
  weight: int
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
resource primary 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2025-09-01-preview' existing = {
  parent: provider
  name: primaryModelName
}

#disable-next-line BCP081
resource candidate 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2025-09-01-preview' = {
  parent: provider
  name: candidateDeploymentName
  properties: {
    displayName: candidateDeploymentName
    description: 'Candidate deployment that the ${aliasName} alias routes to.'
    apiFormat: 'OpenAIChatCompletions'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: '${foundryAccountId}/deployments/${candidateDeploymentName}'
      modelName: candidateDeploymentName
      modelVersion: empty(candidateModelVersion) ? null : candidateModelVersion
    }
  }
}

var routes route[] = strategy == 'weighted'
  ? [
      { resourceId: primary.id, priority: 0, weight: 100 - candidateWeight }
      { resourceId: candidate.id, priority: 0, weight: candidateWeight }
    ]
  : [
      { resourceId: primary.id, priority: 0, weight: 1 }
      { resourceId: candidate.id, priority: 1, weight: 1 }
    ]

#disable-next-line BCP081
resource alias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: aliasName
  properties: {
    description: strategy == 'weighted'
      ? 'Splits traffic ${100 - candidateWeight}/${candidateWeight} between ${primaryModelName} and ${candidateDeploymentName}.'
      : 'Prefers ${primaryModelName}. ${candidateDeploymentName} has a lower preference.'
    backendModels: [
      for r in routes: {
        resourceId: r.resourceId
        priority: r.priority
        weight: r.weight
      }
    ]
  }
}

output aliasName string = alias.name
output candidateModelName string = candidate.name
output routes array = [
  for r in routes: {
    model: last(split(r.resourceId, '/'))
    priority: r.priority
    weight: r.weight
  }
]
output chatCompletionsUrl string = 'https://${aiGateway.properties.frontend.defaultHostname}/default/models/openai/v1/chat/completions'
