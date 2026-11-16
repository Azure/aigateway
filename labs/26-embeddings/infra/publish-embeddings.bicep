// Publishes a Foundry embedding deployment through an existing AI Gateway. main.bicep calls it after the quick start's
// template, and you can also deploy it on its own to a gateway you already have, such as the one from lab 02.
// Registers the deployment under the existing Foundry provider with the embeddings endpoint and a per-caller token
// limit, then publishes an alias that clients send in the request "model" field.
// The gateway's managed identity needs the Foundry User role on the account, which lab 02 and the quick start grant.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Name of the existing Foundry model provider in the gateway, for example foundry-models from lab 02.')
param providerName string = 'foundry-models'

@description('Resource ID of the embedding deployment: <Foundry account ID>/deployments/<deployment name>.')
param deploymentId string

@description('Model name of the deployment, for example text-embedding-3-small.')
param deploymentModelName string = 'text-embedding-3-small'

@description('Version of the deployed model, for example 1. Optional.')
param modelVersion string = ''

@description('Name of the backend model registration under the provider.')
param modelName string = deploymentModelName

@description('Callable alias that clients send in the request "model" field.')
param aliasName string = modelName

@description('Tokens per minute that each caller identity can send to the embedding model.')
@minValue(1)
param tokensPerMinute int = 2000

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

// An embedding model supports only the embeddings endpoint, so chat calls to it fail with unsupported_endpoint.
#disable-next-line BCP081
resource model 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2026-11-01' = {
  parent: provider
  name: modelName
  properties: {
    displayName: modelName
    description: 'Foundry embedding deployment ${deploymentModelName} published through AI Gateway.'
    supportedEndpoints: [
      '/openai/v1/embeddings'
    ]
    deployment: {
      resourceId: deploymentId
      modelName: deploymentModelName
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
resource alias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01' = {
  parent: defaultWorkspace
  name: aliasName
  properties: {
    description: 'Embeddings for search and RAG'
    backendModels: [
      { resourceId: model.id }
    ]
  }
}

output modelName string = model.name
output aliasName string = alias.name
output embeddingsUrl string = 'https://${aiGateway.properties.frontend.defaultHostname}/default/models/openai/v1/embeddings'
