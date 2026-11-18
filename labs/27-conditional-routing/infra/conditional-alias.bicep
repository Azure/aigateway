// Routes one callable alias across two Foundry backend models with CEL expressions. main.bicep calls it after the
// quick start's template, and you can also deploy it on its own to a gateway you already have, such as the one from
// lab 02. Registers the research deployment under the existing Foundry provider, then publishes an alias that either
// sends requests with the header x-workload: research to the research model (conditions), or splits traffic between
// both models and keeps each session on one of them (affinity).
// The general backend model is only referenced, so its policies stay untouched.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Name of the existing Foundry model provider in the gateway, for example foundry-models from lab 02.')
param providerName string = 'foundry-models'

@description('Name of the existing backend model that serves everyday requests, for example gpt-5-mini.')
param generalModelName string = 'gpt-5-mini'

@description('Resource ID of the Foundry account that hosts the research deployment.')
param foundryAccountId string

@description('Name of the research deployment in that account, for example gpt-6.1-sol.')
param researchDeploymentName string = 'gpt-6.1-sol'

@description('Version of the research model, for example 2026-09-29. Optional.')
param researchModelVersion string = ''

@description('Callable alias that clients send in the request "model" field.')
param aliasName string = 'chat'

@description('conditions: requests that match the condition go to the research model, the rest to the general model. affinity: both models share the traffic, and each session stays on one of them.')
@allowed([
  'conditions'
  'affinity'
])
param routingMode string = 'conditions'

@description('Conditions mode: the CEL expression that includes the research model for a request. It must return a Boolean.')
param researchCondition string = '@cel(\'x-workload\' in request.headers && request.headers[\'x-workload\'][0] == \'research\')'

@description('Affinity mode: the CEL expression that returns the session key. An empty string means no affinity for the request.')
param sessionKey string = '@cel(\'session-id\' in request.headers ? request.headers[\'session-id\'][0] : \'\')'

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
resource general 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01' existing = {
  parent: provider
  name: generalModelName
}

#disable-next-line BCP081
resource research 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01' = {
  parent: provider
  name: researchDeploymentName
  properties: {
    displayName: researchDeploymentName
    description: 'Research model that the ${aliasName} alias routes to.'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: '${foundryAccountId}/deployments/${researchDeploymentName}'
      modelName: researchDeploymentName
      modelVersion: empty(researchModelVersion) ? null : researchModelVersion
    }
  }
}

// Conditions: the research model is preferred (priority 0) but only included when its condition is true, so every
// other request falls through to the general model at priority 1.
var conditionsProperties = {
  description: 'Sends x-workload: research requests to ${researchDeploymentName}, everything else to ${generalModelName}.'
  backendModels: [
    { resourceId: research.id, priority: 0, weight: 1, when: researchCondition }
    { resourceId: general.id, priority: 1, weight: 1 }
  ]
  selectionOrder: [
    'priority'
  ]
}

// Affinity: both models share priority 0, and the session key picks the backend before priority and weight do.
var affinityProperties = {
  description: 'Splits sessions between ${generalModelName} and ${researchDeploymentName}, and keeps each session on one of them.'
  backendModels: [
    { resourceId: general.id, priority: 0, weight: 1 }
    { resourceId: research.id, priority: 0, weight: 1 }
  ]
  selectionOrder: [
    'sessionBackendPreference'
    'priority'
  ]
  sessionBackendPreference: {
    key: sessionKey
  }
}

#disable-next-line BCP081
resource alias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01' = {
  parent: defaultWorkspace
  name: aliasName
  properties: routingMode == 'conditions' ? conditionsProperties : affinityProperties
}

output aliasName string = alias.name
output researchModelName string = research.name
output routingMode string = routingMode
output chatCompletionsUrl string = 'https://${aiGateway.properties.frontend.defaultHostname}/default/models/openai/v1/chat/completions'
