// Publishes an alias that prefers a primary Foundry deployment and, with failover on, fails over to a backup when the
// primary returns 429. main.bicep calls it after the quick start's template, and you can also deploy it on its own to
// a gateway you already have, such as the one from lab 02, once both deployments exist in your Foundry account.
// Registers both deployments as backend models under the existing Foundry provider, then publishes the alias.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Name of the existing Foundry model provider in the gateway, for example foundry-models from lab 02.')
param providerName string = 'foundry-models'

@description('Resource ID of the Foundry account that hosts both deployments.')
param foundryAccountId string

@description('Deployment that the alias prefers, at priority 0. The backend model uses the same name.')
param primaryDeploymentName string = 'gpt-5-mini-tiny'

@description('Version of the primary deployment\'s model. Optional.')
param primaryModelVersion string = '2025-08-07'

@description('Deployment that takes over, at priority 1. The backend model uses the same name.')
param backupDeploymentName string = 'gpt-6.1-sol'

@description('Version of the backup deployment\'s model. Optional.')
param backupModelVersion string = '2026-09-29'

@description('Callable alias that clients send in the request "model" field.')
param aliasName string = 'chat-failover'

@description('off: the alias only prefers the primary by priority, and errors go to the client. on: a failure rule switches to the backup on 429.')
@allowed([
  'off'
  'on'
])
param failover string = 'on'

@description('How long a throttled backend stays out of the alias, as an ISO 8601 duration up to P1D. Empty: only for the current request.')
param excludeFor string = 'PT30S'

@description('Cap on the extra sends of one request across all backend models. 3 allows up to four sends.')
@minValue(0)
@maxValue(25)
param maxRetryAttempts int = 3

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

// The gateway calls the Foundry deployment that deployment.modelName names, so it matches the deployment name.
#disable-next-line BCP081
resource primary 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01' = {
  parent: provider
  name: primaryDeploymentName
  properties: {
    displayName: primaryDeploymentName
    description: 'Primary deployment of the ${aliasName} alias.'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: '${foundryAccountId}/deployments/${primaryDeploymentName}'
      modelName: primaryDeploymentName
      modelVersion: empty(primaryModelVersion) ? null : primaryModelVersion
    }
  }
}

#disable-next-line BCP081
resource backup 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01' = {
  parent: provider
  name: backupDeploymentName
  properties: {
    displayName: backupDeploymentName
    description: 'Backup deployment of the ${aliasName} alias.'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: '${foundryAccountId}/deployments/${backupDeploymentName}'
      modelName: backupDeploymentName
      modelVersion: empty(backupModelVersion) ? null : backupModelVersion
    }
  }
}

// One rule: a 429 from a backend switches the request to the next backend model at once (no same-backend retries),
// and keeps the throttled backend out of the alias for excludeFor. Rules use CEL over the backend response.
var throttlingRule = union(
  { when: '@cel(response != null && response.status_code == 429)' },
  empty(excludeFor) ? {} : { excludeFor: excludeFor }
)

#disable-next-line BCP081
resource alias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01' = {
  parent: defaultWorkspace
  name: aliasName
  properties: {
    description: failover == 'on'
      ? 'Prefers ${primaryDeploymentName}, and fails over to ${backupDeploymentName} on 429.'
      : 'Prefers ${primaryDeploymentName}. ${backupDeploymentName} has a lower preference.'
    backendModels: [
      {
        resourceId: primary.id
        priority: 0
        weight: 1
      }
      {
        resourceId: backup.id
        priority: 1
        weight: 1
      }
    ]
    selectionOrder: [
      'priority'
    ]
    maxRetryAttempts: failover == 'on' ? maxRetryAttempts : null
    failures: failover == 'on' ? [throttlingRule] : null
  }
}

output aliasName string = alias.name
output primaryModelName string = primary.name
output backupModelName string = backup.name
output failures array = failover == 'on' ? [throttlingRule] : []
output chatCompletionsUrl string = 'https://${aiGateway.properties.frontend.defaultHostname}/default/models/openai/v1/chat/completions'
