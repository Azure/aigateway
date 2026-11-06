// The building blocks of the quick start, the same ones that the portal and Azure CLI tracks create:
// a gateway, a Foundry model deployment, a model provider that signs in with the gateway's managed identity,
// an alias that apps send in the "model" field, and a runtime API key.
targetScope = 'resourceGroup'

param location string
param tags object = {}

@description('Gateway name. It becomes the first label of the runtime host name.')
@maxLength(24)
param gatewayName string

@description('Foundry account name, also its custom subdomain. It must be globally unique.')
param foundryName string

param modelName string = 'gpt-5-mini'
param modelVersion string = '2025-08-07'

@description('Deployment capacity in thousands of tokens per minute.')
param capacity int = 10

param providerName string = 'foundry-models'
param apiKeyName string = 'app-first-call'

var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

// 1. The gateway, with a system-assigned managed identity. It omits sku, so it gets the default SKU.
#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' = {
  name: gatewayName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

// 2. A Foundry account with one model deployment. Local auth is off: only Entra identities can call it.
resource foundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: foundryName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: foundryName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: foundry
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

// The gateway calls Foundry with its own identity, so it needs the Foundry User role on the account.
resource foundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: guid(foundry.id, gateway.id, foundryUserRoleId)
  properties: {
    principalId: gateway.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
  }
}

// 3. A model provider that points at the Foundry account and signs in with the managed identity.
#disable-next-line BCP081
resource provider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2025-09-01-preview' = {
  parent: workspace
  name: providerName
  dependsOn: [
    foundryUser
  ]
  properties: {
    kind: 'Foundry'
    foundry: {
      endpoint: 'https://${foundryName}.cognitiveservices.azure.com/'
      resourceIds: [
        foundry.id
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

// 4. The deployment as a backend model, and an alias that apps send in the "model" field.
#disable-next-line BCP081
resource model 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2025-09-01-preview' = {
  parent: provider
  name: modelName
  properties: {
    displayName: modelName
    apiFormat: 'OpenAIChatCompletions'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: deployment.id
      modelName: modelName
      modelVersion: modelVersion
    }
  }
}

#disable-next-line BCP081
resource alias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' = {
  parent: workspace
  name: modelName
  properties: {
    aliasName: modelName
    backendModels: [
      {
        resourceId: model.id
      }
    ]
  }
}

// 5. A runtime API key for your first app. Read its value with az aigateway api-key list-secrets; it's never a
//    deployment output.
#disable-next-line BCP081
resource apiKey 'Microsoft.ApiManagement/aigateways/apiKeys@2025-09-01-preview' = {
  parent: gateway
  name: apiKeyName
  properties: {}
}

output gatewayName string = gateway.name
output gatewayId string = gateway.id
output gatewayUrl string = 'https://${gateway.properties.frontend.defaultHostname}'
output aliasName string = alias.name
output foundryName string = foundry.name

// For the labs that build on this template: they call it as a module, then add their own resources.
output gatewayPrincipalId string = gateway.identity.principalId
output providerName string = provider.name
output modelName string = model.name
output modelId string = model.id
output foundryId string = foundry.id
output foundryEndpoint string = foundry.properties.endpoint
output apiKeyName string = apiKey.name
